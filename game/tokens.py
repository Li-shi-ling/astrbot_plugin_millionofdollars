"""HMAC 动作令牌。

设计依据：``docs/game-implementation-design.md`` 第 6 节。

令牌只携带 ``nonce + mac``，不携带可解析的动作；服务端按真实发送者与当前
状态枚举合法动作，用 :func:`hmac.compare_digest` 匹配。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TOKEN_VERSION = 1
SECRET_BYTES = 32
NONCE_BYTES = 16
MAC_BYTES = 16
TOKEN_LENGTH = 43
"""16 字节 nonce + 16 字节 mac 的 base64url 无填充长度。"""

LOG_PREFIX_LENGTH = 6


class TokenError(ValueError):
    """令牌格式非法。"""


@dataclass(frozen=True)
class TokenAction:
    """一个候选动作。"""

    action: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "params": dict(self.params)}


@dataclass(frozen=True)
class TokenContext:
    """令牌绑定的房间与玩家状态。"""

    game_uuid: str
    group_openid: str
    round_number: int
    phase: str
    generation: int
    actor_openid: str


def canonical_payload(context: TokenContext, action: TokenAction, nonce: bytes) -> bytes:
    """生成规范载荷：固定字段名、固定顺序、无多余空格。"""
    payload = {
        "v": TOKEN_VERSION,
        "game": context.game_uuid,
        "group": context.group_openid,
        "round": context.round_number,
        "phase": context.phase,
        "generation": context.generation,
        "actor": context.actor_openid,
        "action": action.action,
        "params": action.params,
        "nonce": _b64url_encode(nonce),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def build_mac(secret: bytes, context: TokenContext, action: TokenAction, nonce: bytes) -> bytes:
    return hmac.new(
        secret,
        canonical_payload(context, action, nonce),
        hashlib.sha256,
    ).digest()[:MAC_BYTES]


class TokenSigner:
    """签发与匹配 HMAC 动作令牌。"""

    def __init__(self, secret: bytes) -> None:
        if len(secret) != SECRET_BYTES:
            raise TokenError(f"密钥必须为 {SECRET_BYTES} 字节。")
        self._secret = secret

    # ---- 密钥管理 ----

    @classmethod
    def load_or_create(cls, path: Path) -> TokenSigner:
        """读取密钥文件，不存在时生成并写入仅当前账户可读的文件。"""
        path = Path(path)
        if path.exists():
            secret = path.read_bytes()
            if len(secret) != SECRET_BYTES:
                raise TokenError(f"密钥文件损坏：{path}")
            return cls(secret)

        path.parent.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_bytes(SECRET_BYTES)
        tmp_path = path.with_name(path.name + ".tmp")
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(secret)
        finally:
            os.replace(tmp_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:  # pragma: no cover - 某些平台不支持
            pass
        return cls(secret)

    # ---- 令牌 ----

    def issue(self, context: TokenContext, action: TokenAction) -> str:
        nonce = secrets.token_bytes(NONCE_BYTES)
        mac = build_mac(self._secret, context, action, nonce)
        return _b64url_encode(nonce + mac)

    def match(
        self,
        token: str,
        context: TokenContext,
        candidates: list[TokenAction],
    ) -> TokenAction | None:
        """在候选动作中匹配令牌，无唯一匹配时返回 ``None``。"""
        nonce = parse_token_nonce(token)
        if nonce is None:
            return None
        matched: TokenAction | None = None
        for candidate in candidates:
            expected = build_mac(self._secret, context, candidate, nonce)
            if hmac.compare_digest(token_mac(token), expected):
                if matched is not None:
                    return None
                matched = candidate
        return matched


def parse_token_nonce(token: str) -> bytes | None:
    """从令牌中取出 nonce；格式非法时返回 ``None``。"""
    raw = _b64url_decode(token)
    if raw is None or len(raw) != NONCE_BYTES + MAC_BYTES:
        return None
    return raw[:NONCE_BYTES]


def token_mac(token: str) -> bytes:
    """取出令牌中的 mac；调用前必须确认 :func:`parse_token_nonce` 已通过。"""
    raw = _b64url_decode(token)
    if raw is None:
        raise TokenError("令牌不是合法的 base64url。")
    return raw[NONCE_BYTES:]


def token_log_prefix(token: str) -> str:
    """日志中只允许记录令牌前 6 个字符。"""
    return token[:LOG_PREFIX_LENGTH]


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes | None:
    if not isinstance(text, str) or len(text) != TOKEN_LENGTH:
        return None
    if any(char not in _B64URL_ALPHABET for char in text):
        return None
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + padding)
    except (ValueError, TypeError):
        return None


_B64URL_ALPHABET = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)
