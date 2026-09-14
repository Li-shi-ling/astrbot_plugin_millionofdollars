"""赃物牌组。

设计依据：``docs/game-implementation-design.md`` 第 4.3 节。

原版包含 10 张赃物牌，开局无放回抽取 8 张。规则正文只公开了金额区间
（800 万～1200 万）与保证金取值（100 万或 200 万），**没有逐张牌面**；归档的
2016 英文规则书 PDF 只包含组件示意图，不含牌面数值。

因此本模块遵守设计约束：

* 不凭区间臆造牌面；
* 牌组必须逐张核验后才能启用，未核验时 ``build_deck`` 抛
  :class:`DeckNotVerifiedError`；
* 录入牌面时必须同时补 :data:`LOOT_DECK_SOURCE_INDEX` 的来源索引。

替换步骤见 ``README.md`` 的"赃物牌组核验"一节。
"""

from __future__ import annotations

import random
import secrets
from collections.abc import Sequence

from .models import LootCard, Role

DECK_SIZE = 10
DRAWN_SIZE = 8

MIN_AMOUNT = 8
MAX_AMOUNT = 12
ALLOWED_ANTES = (1, 2)
BONUS_ROLES = tuple(Role)


class DeckNotVerifiedError(RuntimeError):
    """牌组尚未逐张核验，不能开局。"""


LOOT_DECK_VERIFIED = False
"""牌面是否已逐张核验。核验完成后必须置为 ``True``。"""

LOOT_DECK_SOURCE_INDEX: tuple[str, ...] = ()
"""逐张牌面的来源索引（截图名/页码/实物编号），长度必须等于牌组长度。"""

LOOT_CARD_DATA: tuple[dict[str, object], ...] = ()
"""牌面常量。每项形如 ``{"card_id": ..., "amount": ..., "ante": ..., "bonus_role": ...}``。"""


def validate_deck(entries: Sequence[dict[str, object]]) -> tuple[LootCard, ...]:
    """校验并转换牌组常量，任意一项不合法即抛错。"""
    if len(entries) != DECK_SIZE:
        raise ValueError(f"赃物牌必须是 {DECK_SIZE} 张，收到 {len(entries)} 张。")

    cards: list[LootCard] = []
    seen_ids: set[str] = set()
    for raw in entries:
        card_id = str(raw.get("card_id") or "")
        if not card_id:
            raise ValueError("赃物牌缺少 card_id。")
        if card_id in seen_ids:
            raise ValueError(f"赃物牌 card_id 重复：{card_id}")
        seen_ids.add(card_id)

        amount = raw.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise ValueError(f"{card_id}: amount 必须是整数。")
        if not MIN_AMOUNT <= amount <= MAX_AMOUNT:
            raise ValueError(
                f"{card_id}: amount 必须在 {MIN_AMOUNT}～{MAX_AMOUNT} 之间，收到 {amount}。"
            )

        ante = raw.get("ante")
        if ante not in ALLOWED_ANTES:
            raise ValueError(f"{card_id}: ante 只能是 {ALLOWED_ANTES}，收到 {ante!r}。")

        bonus_raw = raw.get("bonus_role")
        bonus: Role | None = None
        if bonus_raw is not None:
            try:
                bonus = Role(bonus_raw)
            except ValueError as exc:
                raise ValueError(f"{card_id}: 未知奖励角色 {bonus_raw!r}。") from exc

        cards.append(
            LootCard(
                card_id=card_id,
                amount=int(amount),
                ante=int(ante),
                bonus_role=bonus,
            )
        )

    return tuple(cards)


def build_deck() -> tuple[LootCard, ...]:
    """返回已核验的 10 张赃物牌常量。

    Raises:
        DeckNotVerifiedError: 牌面尚未核验（当前默认状态）。
    """
    if not LOOT_DECK_VERIFIED:
        raise DeckNotVerifiedError(
            "赃物牌组尚未逐张核验，无法开局。"
            "请在 game/loot.py 录入 10 张牌面并补齐来源索引后，"
            "将 LOOT_DECK_VERIFIED 置为 True。"
        )
    if len(LOOT_DECK_SOURCE_INDEX) != len(LOOT_CARD_DATA):
        raise DeckNotVerifiedError(
            "赃物牌来源索引数量与牌面数量不一致，拒绝开局。"
        )
    return validate_deck(LOOT_CARD_DATA)


def draw_loot(
    deck: Sequence[LootCard] | None = None,
    *,
    rng: random.Random | None = None,
) -> list[LootCard]:
    """无放回抽取 8 张赃物牌。

    Raises:
        DeckNotVerifiedError: 未传入牌组且内置牌组未核验。
    """
    cards = tuple(deck) if deck is not None else build_deck()
    if len(cards) < DRAWN_SIZE:
        raise ValueError(f"赃物牌不足 {DRAWN_SIZE} 张，无法开局。")
    chooser = rng or random.SystemRandom()
    return chooser.sample(list(cards), DRAWN_SIZE)


def secure_rng() -> random.Random:
    """返回一个使用系统熵源的随机数发生器。"""
    return random.Random(secrets.randbits(128))
