"""规则卡与角色卡图片注册表。

设计依据：``docs/game-implementation-design.md`` 第 7、9 节与产品要求：

* ``百万美金 帮助`` 输出规则卡图片；
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
"""角色卡卡背（牌面印有帮派名），用于需要展示暗置卡面的场景。"""

REVEAL_ORDER: tuple[Role, ...] = (
    Role.SNITCH,
    Role.BRUTE,
    Role.DRIVER,
    Role.CROOK,
    Role.MASTERMIND,
)
"""身份揭露的公开顺序，与抢劫结算顺序一致。"""

HELP_TEXT = """## 百万美金 · 规则速览

**阶段**：筹划（选角 + 交保证金）→ 谈判 → 抢劫 → 分赃。

**抢劫结算顺序**：告密人 → 暴徒 → 司机 → 恶棍 → 谋士 → 告密人指定角色。

- 同一角色出现 2 个及以上：全员淘汰；只有暴徒无论为何被淘汰都能收回保证金。
- 唯一暴徒额外获得 1 张威胁牌。
- 唯一告密人指定一种已公开角色，该角色全员淘汰。

**分赃顺序**：谋士在场则赃款 +200 万 → 按活动人物槽位均分（向下取整）→
每个分得份额的槽位向唯一司机付 100 万 → 唯一恶棍从唯一暴徒处夺取 200 万 →
赃物牌奖励角色额外获得 100 万。

**胜利**：分赃后现金达到 2000 万立即获胜；否则第 8 回合结束时现金最多者获胜，并列共同获胜。
"""


def resolve(relative_path: str) -> Path:
    """把相对插件根目录的路径解析成绝对路径。"""
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return PLUGIN_ROOT / path


def rules_card_path() -> Path:
    return resolve(RULES_CARD.relative_path)


def role_card_path(role: Role | str) -> Path | None:
    try:
        key = Role(role)
    except ValueError:
        return None
    relative = ROLE_CARD_PATHS.get(key)
    if relative is None:
        return None
    return resolve(relative)


def _is_role(role: Role | str) -> bool:
    try:
        Role(role)
    except ValueError:
        return False
    return True


def reveal_roles(roles: list[Role] | tuple[Role, ...]) -> list[str]:
    """返回身份揭露要去重展示的角色键。

    返回值只保证内容与去重，**不保证顺序**：展示顺序由 QQ 适配层随机打乱，
    避免固定顺序暗示玩家与角色的对应关系。
    """
    unique = {Role(role) for role in roles if _is_role(role)}
    return [role.value for role in REVEAL_ORDER if role in unique]


def reveal_images(roles: list[Role] | tuple[Role, ...]) -> list[str]:
    """按角色键返回对应的角色卡相对路径（用于测试与调试）。"""
    return [ROLE_CARD_PATHS[Role(role)] for role in reveal_roles(roles)]
