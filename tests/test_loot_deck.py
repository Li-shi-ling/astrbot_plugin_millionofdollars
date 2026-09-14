"""赃物牌组逐张核验测试（设计文档 4.3 与 11.2）。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from game import loot
from game.models import Role

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SOURCE_JSON = PLUGIN_ROOT / "docs" / "sources" / "loot-cards" / "cards.json"

# 逐张核验的期望牌面：实物牌正面的赃款/保证金 + 角色符号颜色
EXPECTED_CARDS: tuple[tuple[str, int, int, Role | None], ...] = (
    ("loot-01", 10, 2, Role.BRUTE),  # 拉斯维加斯赌场，红色符号
    ("loot-02", 10, 2, Role.SNITCH),  # 皇家赌场，米黄色符号
    ("loot-03", 9, 1, Role.CROOK),  # 国家银行，蓝色符号
    ("loot-04", 9, 1, Role.BRUTE),  # 州际银行，红色符号
    ("loot-05", 9, 1, Role.DRIVER),  # 中央银行，绿色符号
    ("loot-06", 8, 1, Role.SNITCH),  # 城市银行，米黄色符号
    ("loot-07", 8, 1, Role.CROOK),  # 县级银行，蓝色符号
    ("loot-08", 8, 1, Role.DRIVER),  # 农村信用社，绿色符号
    ("loot-09", 12, 2, None),  # 诺克斯堡金库，无角色符号
    ("loot-10", 8, 1, Role.BRUTE),  # 第一银行，红色符号
)

ROLE_BY_EN_NAME = {
    "Brute": Role.BRUTE,
    "Driver": Role.DRIVER,
    "Crook": Role.CROOK,
    "Snitch": Role.SNITCH,
    None: None,
}


def test_deck_is_verified_and_buildable() -> None:
    assert loot.LOOT_DECK_VERIFIED is True

    deck = loot.build_deck()

    assert len(deck) == loot.DECK_SIZE
    assert len({card.card_id for card in deck}) == loot.DECK_SIZE


def test_deck_faces_match_verified_card_images() -> None:
    """逐张核验：10 张牌的赃款、保证金与奖励角色必须与实物牌一致。"""
    deck = loot.build_deck()

    actual = tuple(
        (card.card_id, card.amount, card.ante, card.bonus_role) for card in deck
    )
    assert actual == EXPECTED_CARDS


def test_deck_matches_archived_reference_json() -> None:
    """loot.py 的常量必须与归档的牌面识别结果一致。"""
    reference = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))

    assert reference["grid"]["columns"] * reference["grid"]["rows"] >= 12
    assert len(reference["cards"]) == loot.DECK_SIZE

    cards = {
        f"loot-{item['id']:02d}": (
            item["loot_million"],
            item["ante_million"],
            ROLE_BY_EN_NAME[item["bonus_role"]],
        )
        for item in reference["cards"]
    }
    built = {
        card.card_id: (card.amount, card.ante, card.bonus_role)
        for card in loot.build_deck()
    }

    assert built == cards


def test_source_index_covers_every_card_and_files_exist() -> None:
    assert len(loot.LOOT_DECK_SOURCE_INDEX) == loot.DECK_SIZE

    indexed = {}
    for entry in loot.LOOT_DECK_SOURCE_INDEX:
        card_id, _, path = entry.partition(":")
        indexed[card_id.strip()] = path.strip()

    assert set(indexed) == {card.card_id for card in loot.build_deck()}
    for card_id, path in indexed.items():
        target = PLUGIN_ROOT / path
        assert target.is_file(), f"{card_id} 的来源截图不存在：{path}"
        assert target.stat().st_size > 0


def test_every_builtin_card_has_display_name_and_sendable_image() -> None:
    for card in loot.build_deck():
        assert loot.card_name(card) != card.card_id
        relative = loot.card_image_path(card)
        assert relative is not None
        assert (PLUGIN_ROOT / relative).is_file()


def test_deck_distribution_matches_2016_reference() -> None:
    deck = loot.build_deck()

    assert Counter(card.amount for card in deck) == {8: 4, 9: 3, 10: 2, 12: 1}
    assert Counter(card.ante for card in deck) == {1: 7, 2: 3}
    assert Counter(card.bonus_role for card in deck) == {
        Role.BRUTE: 3,
        Role.SNITCH: 2,
        Role.CROOK: 2,
        Role.DRIVER: 2,
        None: 1,
    }


def test_draw_never_repeats_a_card() -> None:
    for seed in range(5):
        import random

        drawn = loot.draw_loot(loot.build_deck(), rng=random.Random(seed))
        assert len(drawn) == loot.DRAWN_SIZE
        assert len({card.card_id for card in drawn}) == loot.DRAWN_SIZE
        assert set(drawn) <= set(loot.build_deck())


def test_validate_deck_rejects_unverified_shapes() -> None:
    with pytest.raises(ValueError):
        loot.validate_deck(loot.LOOT_CARD_DATA[:-1])
