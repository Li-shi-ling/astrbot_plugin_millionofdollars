"""赃物牌组。

设计依据：``docs/game-implementation-design.md`` 第 4.3 节。

原版包含 10 张赃物牌，开局无放回抽取 8 张。规则正文只公开了金额区间
（800 万～1200 万）与保证金取值（100 万或 200 万），没有逐张牌面；
归档的 2016 英文规则书 PDF 只有 4 页且只含组件示意图。

牌面数据来自实物牌逐张截图（``docs/sources/loot-cards/``），核验方式：

* 金额与保证金：对每张卡的大号数字区域逐位放大比对；
* 奖励角色：读取牌面角色符号区的色相（红=暴徒、绿=司机、蓝=恶棍、米黄=告密者）。

逐张核验结果由 ``tests/test_loot_deck.py`` 固定，参考实现见
``docs/loot-deck-verification.md``。
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


LOOT_DECK_VERIFIED = True
"""牌面是否已逐张核验。核验完成后必须置为 ``True``。"""

# 逐张核验的 10 张牌面：card_id 为稳定编号，注释里保留原版银行名便于对账。
# 金额/保证金来自实物牌正面大号数字，bonus_role 来自牌面角色符号颜色。
LOOT_CARD_DATA: tuple[dict[str, object], ...] = (
    # 01 拉斯维加斯赌场 LAS VEGAS CASINO
    {"card_id": "loot-01", "amount": 10, "ante": 2, "bonus_role": Role.BRUTE},
    # 02 皇家赌场 ROYAL CASINO
    {"card_id": "loot-02", "amount": 10, "ante": 2, "bonus_role": Role.SNITCH},
    # 03 国家银行 NATIONAL BANK
    {"card_id": "loot-03", "amount": 9, "ante": 1, "bonus_role": Role.CROOK},
    # 04 州际银行 GENERAL STATE BANK
    {"card_id": "loot-04", "amount": 9, "ante": 1, "bonus_role": Role.BRUTE},
    # 05 中央银行 CENTRAL BANK
    {"card_id": "loot-05", "amount": 9, "ante": 1, "bonus_role": Role.DRIVER},
    # 06 城市银行 BANK OF THE CITY
    {"card_id": "loot-06", "amount": 8, "ante": 1, "bonus_role": Role.SNITCH},
    # 07 县级银行 BANK OF THE COUNTY
    {"card_id": "loot-07", "amount": 8, "ante": 1, "bonus_role": Role.CROOK},
    # 08 农村信用社 RURAL DISTRICT BANK
    {"card_id": "loot-08", "amount": 8, "ante": 1, "bonus_role": Role.DRIVER},
    # 09 诺克斯堡金库 FORT KNOX（牌面无角色符号）
    {"card_id": "loot-09", "amount": 12, "ante": 2, "bonus_role": None},
    # 10 第一银行 FIRST BANK
    {"card_id": "loot-10", "amount": 8, "ante": 1, "bonus_role": Role.BRUTE},
)

LOOT_DECK_SOURCE_INDEX: tuple[str, ...] = (
    "loot-01: docs/sources/loot-cards/cards/01_las_vegas_casino.jpg",
    "loot-02: docs/sources/loot-cards/cards/02_royal_casino.jpg",
    "loot-03: docs/sources/loot-cards/cards/03_national_bank.jpg",
    "loot-04: docs/sources/loot-cards/cards/04_general_state_bank.jpg",
    "loot-05: docs/sources/loot-cards/cards/05_central_bank.jpg",
    "loot-06: docs/sources/loot-cards/cards/06_bank_of_the_city.jpg",
    "loot-07: docs/sources/loot-cards/cards/07_bank_of_the_county.jpg",
    "loot-08: docs/sources/loot-cards/cards/08_rural_district_bank.jpg",
    "loot-09: docs/sources/loot-cards/cards/09_fort_knox.jpg",
    "loot-10: docs/sources/loot-cards/cards/10_first_bank.jpg",
)

LOOT_CARD_NAMES: dict[str, str] = {
    "loot-01": "拉斯维加斯赌场",
    "loot-02": "皇家赌场",
    "loot-03": "国家银行",
    "loot-04": "州际银行",
    "loot-05": "中央银行",
    "loot-06": "城市银行",
    "loot-07": "县级银行",
    "loot-08": "农村信用社",
    "loot-09": "诺克斯堡金库",
    "loot-10": "第一银行",
}

LOOT_CARD_IMAGE_PATHS: dict[str, str] = {
    card_id.strip(): path.strip()
    for entry in LOOT_DECK_SOURCE_INDEX
    for card_id, separator, path in (entry.partition(":"),)
    if separator
}


def card_name(card: LootCard | str) -> str:
    """返回赃物牌的中文名；自定义牌组没有名称时回退到编号。"""
    card_id = card.card_id if isinstance(card, LootCard) else str(card)
    return LOOT_CARD_NAMES.get(card_id, card_id)


def card_image_path(card: LootCard | str) -> str | None:
    """返回内置赃物牌图片的插件相对路径。"""
    card_id = card.card_id if isinstance(card, LootCard) else str(card)
    return LOOT_CARD_IMAGE_PATHS.get(card_id)


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
