"""HMAC 令牌与赃物牌组测试（设计文档 11.1 与 4.3）。"""

from __future__ import annotations

import os

import pytest
from game import loot, tokens
from game.models import LootCard, Role
from game.tokens import TokenAction, TokenContext, TokenSigner

SECRET = bytes(range(32))


def context(**overrides) -> TokenContext:
    base = {
        "game_uuid": "game-1",
        "group_openid": "group-1",
        "round_number": 1,
        "phase": "role_selection",
        "generation": 3,
        "actor_openid": "user-a",
    }
    base.update(overrides)
    return TokenContext(**base)


# ----------------------------------------------------------------------
# 令牌
# ----------------------------------------------------------------------


def test_token_length_and_no_plaintext_leak() -> None:
    signer = TokenSigner(SECRET)
    token = signer.issue(context(), TokenAction("choose_role", {"role": "driver"}))

    assert len(token) == tokens.TOKEN_LENGTH
    assert token == token.rstrip("=")
    assert "driver" not in token
    assert tokens.token_log_prefix(token) == token[:6]


def test_same_action_issues_different_tokens() -> None:
    signer = TokenSigner(SECRET)
    action = TokenAction("choose_role", {"role": "driver"})

    first = signer.issue(context(), action)
    second = signer.issue(context(), action)

    assert first != second


def test_matching_accepts_only_the_correct_actor_action() -> None:
    signer = TokenSigner(SECRET)
    action = TokenAction("choose_role", {"role": "driver"})
    token = signer.issue(context(), action)

    matched = signer.match(
        token,
        context(),
        [action, TokenAction("choose_role", {"role": "brute"})],
    )

    assert matched == action
    # 换玩家、换游戏、换回合、换阶段、换代次、换参数都不能匹配
    assert signer.match(token, context(actor_openid="user-b"), [action]) is None
    assert signer.match(token, context(game_uuid="game-2"), [action]) is None
    assert signer.match(token, context(round_number=2), [action]) is None
    assert signer.match(token, context(phase="negotiation"), [action]) is None
    assert signer.match(token, context(generation=4), [action]) is None
    assert signer.match(token, context(group_openid="group-2"), [action]) is None
    assert (
        signer.match(token, context(), [TokenAction("choose_role", {"role": "brute"})])
        is None
    )


def test_tampered_or_malformed_tokens_are_rejected() -> None:
    signer = TokenSigner(SECRET)
    action = TokenAction("choose_role", {"role": "driver"})
    token = signer.issue(context(), action)

    tampered = ("A" if token[0] != "A" else "B") + token[1:]
    assert signer.match(tampered, context(), [action]) is None
    assert signer.match("", context(), [action]) is None
    assert signer.match("not-a-token", context(), [action]) is None
    assert signer.match(token[:-1], context(), [action]) is None


def test_replay_fails_after_generation_bump() -> None:
    """重放：成功动作后代次递增，旧按钮立即失效。"""
    signer = TokenSigner(SECRET)
    action = TokenAction("ready")
    token = signer.issue(context(), action)

    assert signer.match(token, context(), [action]) == action
    # 服务端成功后 action_generation += 1
    assert signer.match(token, context(generation=4), [action]) is None


def test_secret_is_reused_across_restarts(tmp_path) -> None:
    path = tmp_path / "hmac_secret.bin"

    first = TokenSigner.load_or_create(path)
    second = TokenSigner.load_or_create(path)
    token = first.issue(context(), TokenAction("ready"))

    assert path.read_bytes() == path.read_bytes()
    assert len(path.read_bytes()) == tokens.SECRET_BYTES
    assert second.match(token, context(), [TokenAction("ready")]) == TokenAction("ready")


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows 的 st_mode 不表达 POSIX 组/其他用户权限位",
)
def test_secret_file_is_not_world_readable(tmp_path) -> None:
    path = tmp_path / "nested" / "hmac_secret.bin"
    TokenSigner.load_or_create(path)

    mode = path.stat().st_mode & 0o777
    assert mode & 0o077 == 0


def test_signer_rejects_wrong_secret_size() -> None:
    with pytest.raises(tokens.TokenError):
        TokenSigner(b"short")


# ----------------------------------------------------------------------
# 赃物牌组
# ----------------------------------------------------------------------


def valid_entries() -> list[dict[str, object]]:
    return [
        {
            "card_id": f"card-{index}",
            "amount": 8 + index % 5,
            "ante": 1 + index % 2,
            "bonus_role": None if index % 3 else Role.DRIVER.value,
        }
        for index in range(loot.DECK_SIZE)
    ]


def test_validate_deck_accepts_a_complete_verified_deck() -> None:
    cards = loot.validate_deck(valid_entries())

    assert len(cards) == loot.DECK_SIZE
    assert all(isinstance(card, LootCard) for card in cards)
    assert all(loot.MIN_AMOUNT <= card.amount <= loot.MAX_AMOUNT for card in cards)
    assert {card.ante for card in cards} <= set(loot.ALLOWED_ANTES)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda entries: entries[:-1],
        lambda entries: entries + [entries[0]],
        lambda entries: [{**entries[0], "amount": 99}, *entries[1:]],
        lambda entries: [{**entries[0], "ante": 3}, *entries[1:]],
        lambda entries: [{**entries[0], "bonus_role": "wizard"}, *entries[1:]],
        lambda entries: [{**entries[0], "card_id": ""}, *entries[1:]],
    ],
)
def test_validate_deck_rejects_invalid_data(mutate) -> None:
    with pytest.raises(ValueError):
        loot.validate_deck(mutate(valid_entries()))


def test_unverified_deck_is_rejected(monkeypatch) -> None:
    """牌面尚未逐张核验时不得开局。"""
    monkeypatch.setattr(loot, "LOOT_DECK_VERIFIED", False)
    with pytest.raises(loot.DeckNotVerifiedError):
        loot.build_deck()
    with pytest.raises(loot.DeckNotVerifiedError):
        loot.draw_loot()


def test_source_index_mismatch_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(loot, "LOOT_DECK_SOURCE_INDEX", ())
    with pytest.raises(loot.DeckNotVerifiedError):
        loot.build_deck()


def test_draw_loot_takes_eight_unique_cards() -> None:
    deck = loot.validate_deck(valid_entries())

    drawn = loot.draw_loot(deck, rng=loot.secure_rng())

    assert len(drawn) == loot.DRAWN_SIZE
    assert len({card.card_id for card in drawn}) == loot.DRAWN_SIZE
