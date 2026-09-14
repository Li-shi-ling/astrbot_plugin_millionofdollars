"""QQOfficial 平台适配层。

设计依据：``docs/qqofficial-bot-development.md`` 与
``docs/game-implementation-design.md`` 第 2、7 节。

本模块负责：

* 判断事件是否为 QQOfficial 群消息；
* 从原始事件的可信字段提取 ``platform_id`` / ``group_openid`` /
  ``member_openid`` / ``message_id``；
* 把与平台无关的 :class:`~game.service.Reply` 转成 Markdown + keyboard 并发送。

本模块不得直接修改游戏快照。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import botpy.message as botpy_message

from astrbot.api import logger

from .service import ButtonSpec, Reply

QQOFFICIAL_PLATFORMS = {"qq_official", "qq_official_webhook"}
QQOFFICIAL_MESSAGE_EVENT_NAMES = {
    "QQOfficialMessageEvent",
    "QQOfficialWebhookMessageEvent",
}
QQOFFICIAL_MESSAGE_EVENT_MODULE_PREFIXES = (
    "astrbot.core.platform.sources.qqofficial.",
    "astrbot.core.platform.sources.qqofficial_webhook.",
)

MAX_BUTTONS = 25
BUTTONS_PER_ROW = 5
UNSUPPORT_TIPS = "当前客户端不支持该按钮"


@dataclass(frozen=True)
class QQOfficialContext:
    """一次 QQOfficial 群消息的可信上下文。"""

    platform_id: str
    group_openid: str
    member_openid: str
    display_name: str
    message_id: str
    msg_seq: int | None = None


def is_qqofficial_message_event(event: Any) -> bool:
    event_type = type(event)
    module_name = event_type.__module__.lower()
    return event_type.__name__ in QQOFFICIAL_MESSAGE_EVENT_NAMES and (
        module_name.startswith(QQOFFICIAL_MESSAGE_EVENT_MODULE_PREFIXES)
    )


def extract_context(event: Any) -> QQOfficialContext | None:
    """从原始事件读取可信身份字段，禁止从按钮文本或用户输入取得身份。"""
    raw_message = getattr(getattr(event, "message_obj", None), "raw_message", None)
    author = getattr(raw_message, "author", None)

    group_openid = _first_non_empty_str(
        getattr(raw_message, "group_openid", None),
        _safe_call(event, "get_group_id"),
    )
    member_openid = _first_non_empty_str(
        getattr(author, "member_openid", None),
        getattr(raw_message, "group_member_openid", None),
        _safe_call(event, "get_sender_id"),
    )
    if not group_openid or not member_openid:
        return None

    message_id = _first_non_empty_str(
        getattr(raw_message, "id", None),
        getattr(getattr(event, "message_obj", None), "message_id", None),
    )
    display_name = _first_non_empty_str(
        _safe_call(event, "get_sender_name"),
        getattr(author, "username", None),
        member_openid[:8],
    )
    return QQOfficialContext(
        platform_id=str(_safe_call(event, "get_platform_id") or ""),
        group_openid=group_openid,
        member_openid=member_openid,
        display_name=display_name or member_openid[:8],
        message_id=message_id or "",
        msg_seq=_as_int(getattr(raw_message, "msg_seq", None)),
    )


def build_button(spec: ButtonSpec) -> dict[str, Any]:
    permission: dict[str, Any]
    if spec.only_for:
        permission = {"type": 0, "specify_user_ids": [spec.only_for]}
    else:
        permission = {"type": 2}
    return {
        "id": spec.button_id,
        "render_data": {
            "label": spec.label,
            "visited_label": spec.visited_label,
            "style": 1,
        },
        "action": {
            "type": 2,
            "permission": permission,
            "data": spec.data,
            "reply": True,
            "enter": False,
            "unsupport_tips": UNSUPPORT_TIPS,
        },
    }


def build_keyboard(buttons: list[ButtonSpec]) -> dict[str, Any] | None:
    if not buttons:
        return None
    limited = buttons[:MAX_BUTTONS]
    rows = [
        {"buttons": [build_button(item) for item in limited[index : index + BUTTONS_PER_ROW]]}
        for index in range(0, len(limited), BUTTONS_PER_ROW)
    ]
    return {"content": {"rows": rows}}


def build_payload(reply: Reply) -> dict[str, Any]:
    keyboard = build_keyboard(reply.buttons)
    if keyboard is None:
        return {"content": reply.text, "msg_type": 0, "markdown": None, "keyboard": None}
    return {
        "content": reply.text,
        "msg_type": 2,
        "markdown": {"content": reply.text},
        "keyboard": keyboard,
    }


def add_passive_reply_context(
    payload: dict[str, Any],
    *,
    msg_id: str | None = None,
    event_id: str | None = None,
    msg_seq: int | None = None,
) -> dict[str, Any]:
    if msg_id:
        payload["msg_id"] = msg_id
    elif event_id:
        payload["event_id"] = event_id
    if payload.get("msg_id") or payload.get("event_id"):
        payload["msg_seq"] = msg_seq if msg_seq is not None else random.randint(1, 10000)
    return payload


async def send_reply(event: Any, context: QQOfficialContext, reply: Reply) -> bool:
    """发送一条回复及其附带消息。

    返回是否全部发送成功。附带消息（秘密按钮）发送失败时必须提示重试，不得
    降级为明文角色指令。
    """
    ok = True
    for index, item in enumerate([reply, *reply.extra]):
        sent = await _send_single(event, context, item, extra=index > 0)
        ok = ok and sent
    return ok


async def _send_single(
    event: Any,
    context: QQOfficialContext,
    reply: Reply,
    *,
    extra: bool,
) -> bool:
    payload = build_payload(reply)
    add_passive_reply_context(
        payload,
        msg_id=context.message_id,
        msg_seq=context.msg_seq,
    )
    raw_message = getattr(getattr(event, "message_obj", None), "raw_message", None)
    logger.info(
        "[百万美金] 发送消息: group=%s, extra=%s, buttons=%d",
        context.group_openid,
        extra,
        len(reply.buttons),
    )
    try:
        if isinstance(raw_message, botpy_message.GroupMessage):
            await event.bot.api.post_group_message(
                group_openid=context.group_openid,
                **payload,
            )
            return True
        await event.send(event.plain_result(reply.text))
        return True
    except Exception as exc:  # noqa: BLE001 - 外部 API 异常需要兜底
        logger.warning("[百万美金] 发送失败: %s", exc)
        if reply.buttons:
            try:
                await event.send(
                    event.plain_result(
                        "按钮发送失败，请重新发送指令重试（秘密按钮不会以明文形式重发）。"
                    )
                )
            except Exception:  # noqa: BLE001
                logger.debug("[百万美金] 发送失败提示也未能送达。")
        return False


def _first_non_empty_str(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text:
            return text
    return None


def _safe_call(target: Any, name: str) -> Any:
    method = getattr(target, name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:  # noqa: BLE001 - 平台字段缺失时不应影响主流程
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
