"""规则卡与角色卡图片注册表。

设计依据：``docs/game-implementation-design.md`` 第 7、9 节与产品要求：

* ``百万美金帮助`` 输出规则卡图片；
* 身份揭露（抢劫阶段公开人物牌）时输出对应角色卡图片。

图片路径统一使用**相对插件根目录**的 POSIX 形式，便于进入幂等缓存与快照；
QQ 适配层负责解析成绝对路径后再发送。本模块不导入 AstrBot 或 botpy。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import Role

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
"""插件根目录，用于把相对路径解析成绝对路径。"""


@dataclass(frozen=True)
class HelpCard:
    """帮助接口可输出的图片。"""

    key: str
    title: str
    relative_path: str
    description: str = ""


RULES_CARD = HelpCard(
    key="rules",
    title="规则卡",
    relative_path="docs/sources/rule-cards/rule-card.jpg",
    description="《百万美金》2016 初版规则速览",
)

ROLE_CARD_PATHS: dict[str, str] = {
    Role.DRIVER: "docs/sources/role-cards/01_driver.jpg",
    Role.CROOK: "docs/sources/role-cards/02_crook.jpg",
    Role.BRUTE: "docs/sources/role-cards/03_brute.jpg",
    Role.MASTERMIND: "docs/sources/role-cards/04_mastermind.jpg",
    Role.SNITCH: "docs/sources/role-cards/05_snitch.jpg",
}
"""身份揭露时使用的角色卡。钥匙为 :class:`~game.models.Role` 的字符串值。"""

CARD_BACK_PATH = "docs/sources/role-cards/card-back.jpg"
"""角色卡卡背（牌面印有帮派名），用于展示暗置的角色卡。"""

CARD_BACK_KEY = "card_back"
"""身份揭露时代表"被隐藏的那张角色牌"的键。"""

def resolve(relative_path: str) -> Path:
    """把相对插件根目录的路径解析成绝对路径。"""
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return PLUGIN_ROOT / path


def rules_card_path() -> Path:
    return resolve(RULES_CARD.relative_path)


def role_card_path(role: Role | str) -> Path | None:
    """角色卡的绝对路径；未知角色返回 ``None``。"""
    return card_path(role)


def card_path(key: Role | str) -> Path | None:
    """把角色键或卡背键解析成图片路径；未知键返回 ``None``。"""
    if key == CARD_BACK_KEY:
        return resolve(CARD_BACK_PATH)
    try:
        role = Role(key)
    except ValueError:
        return None
    relative = ROLE_CARD_PATHS.get(role)
    if relative is None:
        return None
    return resolve(relative)


def card_paths(keys: list[Role | str] | tuple[Role | str, ...]) -> list[Path]:
    """按给定顺序把卡片键解析成图片路径，跳过未知键。"""
    paths: list[Path] = []
    for key in keys:
        path = card_path(key)
        if path is not None:
            paths.append(path)
    return paths
