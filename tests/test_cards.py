"""身份揭露卡图合成测试。"""

from __future__ import annotations

import random

import pytest
from game import cards, help
from PIL import Image


def role_paths(*roles: str):
    return [help.role_card_path(role) for role in roles]


def test_role_card_registry_covers_all_five_roles() -> None:
    for role in ["driver", "brute", "crook", "snitch", "mastermind"]:
        path = help.role_card_path(role)
        assert path is not None
        assert path.is_file(), f"缺少角色卡：{path}"


def test_rules_card_exists() -> None:
    assert help.rules_card_path().is_file()


def test_role_card_back_exists() -> None:
    """角色卡卡背已归档（不是角色卡）。"""
    back = help.resolve(help.CARD_BACK_PATH)
    assert back.is_file()
    assert back.name == "card-back.jpg"


def test_shuffled_is_a_permutation_and_not_always_the_input_order() -> None:
    paths = role_paths("driver", "brute", "crook", "snitch", "mastermind")

    orders = set()
    for seed in range(12):
        result = cards.shuffled(paths, random.Random(seed))
        assert sorted(p.name for p in result) == sorted(p.name for p in paths)
        orders.add(tuple(p.name for p in result))

    assert len(orders) > 1, "打乱后不应永远保持同一顺序"


def test_compose_strip_merges_cards_into_one_image(tmp_path) -> None:
    paths = role_paths("driver", "brute", "crook")

    output = cards.compose_strip(paths, tmp_path / "reveal.jpg")

    assert output.is_file()
    image = Image.open(output)
    assert image.format == "JPEG"
    # 三张卡横向排列：宽度大于单卡，高度接近单卡高度
    assert image.width > image.height
    single = Image.open(paths[0])
    assert image.height >= single.height
    assert image.width >= single.width * 3


def test_compose_strip_accepts_a_single_card(tmp_path) -> None:
    output = cards.compose_strip(role_paths("snitch"), tmp_path / "one.jpg")

    assert output.is_file()


def test_compose_strip_rejects_missing_card(tmp_path) -> None:
    with pytest.raises(cards.CardImageError):
        cards.compose_strip([tmp_path / "nope.jpg"], tmp_path / "out.jpg")


def test_compose_strip_rejects_empty_input(tmp_path) -> None:
    with pytest.raises(cards.CardImageError):
        cards.compose_strip([], tmp_path / "out.jpg")


def test_reveal_roles_dedupes_and_stays_within_known_roles() -> None:
    roles = help.reveal_roles(["driver", "brute", "driver", "snitch"])

    assert sorted(roles) == ["brute", "driver", "snitch"]
    assert all(role in help.ROLE_CARD_PATHS for role in roles)
