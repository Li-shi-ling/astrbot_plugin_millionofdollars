"""纯规则测试（设计文档 11.2）。"""

from __future__ import annotations

import random

import pytest
from game import rules
from game.models import (
    CharacterSlot,
    GameSnapshot,
    LootCard,
    Phase,
    Player,
    Role,
    RuleError,
)

# ----------------------------------------------------------------------
# 构造辅助
# ----------------------------------------------------------------------


def make_snapshot(
    roles: dict[str, list[Role]],
    *,
    cash: int = 5,
    amount: int = 8,
    ante: int = 1,
    bonus_role: Role | None = None,
    phase: Phase = Phase.NEGOTIATION,
) -> GameSnapshot:
    snapshot = GameSnapshot(
        game_uuid="game-1",
        platform_id="platform",
        group_openid="group",
        phase=phase,
    )
    for index, (name, player_roles) in enumerate(roles.items()):
        player = Player(
            member_openid=name,
            display_name=name,
            join_order=index,
            cash=cash,
        )
        player.slots = [
            CharacterSlot(slot_id=f"{name}:{slot_index}", role=role)
            for slot_index, role in enumerate(player_roles)
        ]
        snapshot.players.append(player)
    snapshot.loot_deck = [
        LootCard(card_id=f"c{index}", amount=amount, ante=ante, bonus_role=bonus_role)
        for index in range(8)
    ]
    snapshot.current_loot_index = 0
    counts: dict[str, int] = {}
    for slot in snapshot.all_slots():
        if slot.role is not None:
            counts[slot.role.value] = counts.get(slot.role.value, 0) + 1
    snapshot.public_role_counts = counts
    return snapshot


def rng() -> random.Random:
    return random.Random(20260914)


# ----------------------------------------------------------------------
# 角色集合
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("player_count", "expected"),
    [
        (3, {Role.DRIVER, Role.BRUTE, Role.CROOK, Role.SNITCH, Role.MASTERMIND}),
        (4, {Role.DRIVER, Role.BRUTE, Role.CROOK}),
        (5, {Role.DRIVER, Role.BRUTE, Role.CROOK, Role.SNITCH}),
        (6, {Role.DRIVER, Role.BRUTE, Role.CROOK, Role.SNITCH}),
        (7, {Role.DRIVER, Role.BRUTE, Role.CROOK, Role.SNITCH, Role.MASTERMIND}),
        (8, {Role.DRIVER, Role.BRUTE, Role.CROOK, Role.SNITCH, Role.MASTERMIND}),
    ],
)
def test_roles_for_player_count(player_count: int, expected: set[Role]) -> None:
    assert set(rules.roles_for_player_count(player_count)) == expected


@pytest.mark.parametrize("player_count", [2, 9, 0])
def test_roles_for_player_count_rejects_invalid(player_count: int) -> None:
    with pytest.raises(RuleError):
        rules.roles_for_player_count(player_count)


def test_three_players_use_two_slots_and_must_differ() -> None:
    assert rules.slots_per_player(3) == 2
    assert rules.slots_per_player(4) == 1
    rules.validate_role_selection(3, [Role.DRIVER, Role.BRUTE])
    with pytest.raises(RuleError):
        rules.validate_role_selection(3, [Role.DRIVER, Role.DRIVER])
    with pytest.raises(RuleError):
        rules.validate_role_selection(3, [Role.DRIVER])


def test_four_players_cannot_choose_snitch_or_mastermind() -> None:
    with pytest.raises(RuleError):
        rules.validate_role_selection(4, [Role.SNITCH])
    with pytest.raises(RuleError):
        rules.validate_role_selection(4, [])


# ----------------------------------------------------------------------
# 保证金
# ----------------------------------------------------------------------


def test_collect_ante_uses_reserve_when_cash_is_not_enough() -> None:
    snapshot = make_snapshot({"a": [Role.DRIVER]}, cash=1, ante=2)
    card = snapshot.loot_deck[0]

    events = rules.collect_antes(snapshot, card)

    player = snapshot.players[0]
    slot = player.slots[0]
    assert player.cash == 0
    assert slot.ante_total == 2
    assert slot.player_paid == 1
    assert slot.reserve_paid == 1
    assert events and "储备区" in events[0]


def test_refund_ante_returns_the_full_ante_once() -> None:
    """设计文档 5.2：退还保证金时退回完整保证金，且不得重复退款。"""
    snapshot = make_snapshot({"a": [Role.DRIVER]}, cash=1, ante=2)
    card = snapshot.loot_deck[0]
    rules.collect_antes(snapshot, card)
    player = snapshot.players[0]
    slot = player.slots[0]

    rules.refund_ante(player, slot)
    rules.refund_ante(player, slot)  # 重复调用必须幂等

    assert player.cash == 2
    assert slot.ante_returned is True


# ----------------------------------------------------------------------
# 公开角色
# ----------------------------------------------------------------------


def test_publish_roles_hides_exactly_one_slot_and_only_publishes_counts() -> None:
    snapshot = make_snapshot(
        {
            "a": [Role.DRIVER],
            "b": [Role.BRUTE],
            "c": [Role.CROOK],
            "d": [Role.MASTERMIND],
        },
        phase=Phase.ROLE_SELECTION,
    )

    rules.publish_roles(snapshot, rng=rng())

    assert snapshot.hidden_slot_id is not None
    hidden = snapshot.find_slot(snapshot.hidden_slot_id)
    assert hidden is not None and hidden.revealed is False
    total = sum(snapshot.public_role_counts.values())
    assert total == 3
    assert all(count == 1 for count in snapshot.public_role_counts.values())


# ----------------------------------------------------------------------
# 抢劫结算
# ----------------------------------------------------------------------


def test_heist_collision_eliminates_all_but_brute_refunds() -> None:
    snapshot = make_snapshot(
        {
            "a": [Role.BRUTE],
            "b": [Role.BRUTE],
            "c": [Role.DRIVER],
        }
    )
    card = snapshot.loot_deck[0]
    rules.collect_antes(snapshot, card)

    events = rules.resolve_heist_roles(snapshot)

    brutes = [slot for player in snapshot.players[:2] for slot in player.slots]
    assert all(slot.eliminated for slot in brutes)
    assert all(slot.ante_returned for slot in brutes)
    assert all(player.cash == 5 for player in snapshot.players[:2])
    assert any("暴徒" in event for event in events)


def test_unique_brute_gets_intimidation_card_and_snitch_is_selected() -> None:
    snapshot = make_snapshot(
        {
            "a": [Role.BRUTE],
            "b": [Role.SNITCH],
            "c": [Role.DRIVER],
            "d": [Role.CROOK],
        }
    )
    rules.collect_antes(snapshot, snapshot.loot_deck[0])

    rules.resolve_heist_roles(snapshot)

    assert snapshot.players[0].threat_cards == 1
    assert snapshot.phase is Phase.SNITCH_SELECTION
    selection = snapshot.snitch_selection
    assert selection is not None
    assert selection.actor_openid == "b"
    assert set(selection.targets) == set(rules.public_roles(snapshot))


def test_snitch_designation_eliminates_that_role_and_brute_keeps_ante() -> None:
    snapshot = make_snapshot(
        {
            "a": [Role.BRUTE],
            "b": [Role.SNITCH],
            "c": [Role.DRIVER],
            "d": [Role.CROOK],
        }
    )
    rules.collect_antes(snapshot, snapshot.loot_deck[0])
    rules.resolve_heist_roles(snapshot)

    rules.resolve_snitch_designation(snapshot, Role.BRUTE)

    brute_slot = snapshot.players[0].slots[0]
    assert brute_slot.eliminated
    assert brute_slot.ante_returned
    assert snapshot.players[0].cash == 5


def test_only_snitch_left_loses_three_million_and_skips_sharing() -> None:
    snapshot = make_snapshot(
        {
            "a": [Role.SNITCH],
            "b": [Role.DRIVER],
            "c": [Role.DRIVER],
        },
        cash=2,
        ante=1,
    )
    rules.collect_antes(snapshot, snapshot.loot_deck[0])
    rules.resolve_heist_roles(snapshot)
    assert snapshot.phase is Phase.SNITCH_SELECTION
    # 两名司机已经撞车淘汰，告密人指定司机不会再有新的淘汰
    rules.resolve_snitch_designation(snapshot, Role.DRIVER)
    assert snapshot.phase is Phase.RESOLVING

    events = rules.finish_resolving(snapshot)

    # 现金不得降到零以下，实际扣除上限为现有现金
    assert snapshot.players[0].cash == 0
    assert snapshot.phase is Phase.ROUND_END
    assert any("跳过分赃" in event for event in events)
    assert snapshot.players[0].slots[0].eliminated


# ----------------------------------------------------------------------
# 分赃
# ----------------------------------------------------------------------


def test_sharing_applies_mastermind_driver_crook_and_bonus_in_order() -> None:
    snapshot = make_snapshot(
        {
            "a": [Role.MASTERMIND],
            "b": [Role.DRIVER],
            "c": [Role.CROOK],
            "d": [Role.BRUTE],
        },
        cash=5,
        amount=10,
        ante=1,
        bonus_role=Role.BRUTE,
    )
    rules.collect_antes(snapshot, snapshot.loot_deck[0])
    rules.resolve_heist_roles(snapshot)
    snapshot.phase = Phase.RESOLVING

    rules.finish_resolving(snapshot)

    cash = {player.member_openid: player.cash for player in snapshot.players}
    # 1) 收保证金后每人 4，唯一角色结算后各退回保证金 => 5
    # 2) 10 + 2（谋士）= 12，按 4 个槽位平均，每份 3 => 8
    # 3) 每个分得赃款的槽位向司机支付 1：司机 8-1+4=11，其他 8-1=7
    # 4) 恶棍从暴徒处夺取 2：恶棍 9，暴徒 5
    # 5) 赃物牌奖励暴徒 1：暴徒 6
    assert cash["a"] == 7
    assert cash["b"] == 11
    assert cash["c"] == 9
    assert cash["d"] == 6
    assert sum(cash.values()) == 33


def test_sharing_payments_never_make_cash_negative() -> None:
    snapshot = make_snapshot(
        {
            "a": [Role.MASTERMIND],
            "b": [Role.DRIVER],
            "c": [Role.CROOK],
            "d": [Role.BRUTE],
        },
        cash=0,
        amount=8,
        ante=0,
        bonus_role=None,
    )
    snapshot.phase = Phase.RESOLVING

    rules.finish_resolving(snapshot)

    assert all(player.cash >= 0 for player in snapshot.players)


def test_victory_at_twenty_is_instant_and_ties_share() -> None:
    snapshot = make_snapshot(
        {"a": [Role.DRIVER], "b": [Role.BRUTE], "c": [Role.CROOK]}
    )
    snapshot.players[0].cash = 21
    snapshot.players[1].cash = 21
    snapshot.players[2].cash = 19

    assert set(rules.evaluate_victory(snapshot)) == {"a", "b"}


def test_sharing_can_trigger_instant_victory() -> None:
    snapshot = make_snapshot(
        {
            "a": [Role.DRIVER],
            "b": [Role.BRUTE],
            "c": [Role.MASTERMIND],
        },
        cash=19,
        amount=12,
    )
    snapshot.phase = Phase.RESOLVING

    rules.finish_resolving(snapshot)

    winners = rules.evaluate_victory(snapshot)
    assert winners == [snapshot.players[0].member_openid]


def test_last_round_ends_the_game_with_the_richest_player() -> None:
    snapshot = make_snapshot({"a": [Role.DRIVER], "b": [Role.BRUTE]})
    snapshot.current_loot_index = 7
    snapshot.players[0].cash = 3
    snapshot.players[1].cash = 9

    winners = rules.evaluate_victory(snapshot)

    assert winners == ["b"]


def test_next_round_rotates_leader_and_clears_state() -> None:
    snapshot = make_snapshot({"a": [Role.DRIVER], "b": [Role.BRUTE], "c": [Role.CROOK]})
    snapshot.phase = Phase.ROUND_END
    snapshot.current_loot_index = 0
    for player in snapshot.players:
        player.ready = True

    rules.start_next_round(snapshot)

    assert snapshot.round_number == 2
    assert snapshot.current_loot_index == 1
    assert snapshot.leader_index == 1
    assert snapshot.phase is Phase.ROLE_SELECTION
    assert all(player.ready is False for player in snapshot.players)
    assert all(slot.role is None for slot in snapshot.all_slots())


# ----------------------------------------------------------------------
# 谈判期的独立操作
# ----------------------------------------------------------------------


def test_transfer_only_moves_cash_and_clears_ready() -> None:
    snapshot = make_snapshot({"a": [Role.DRIVER], "b": [Role.BRUTE]})
    snapshot.players[0].ready = True
    snapshot.players[1].ready = True

    rules.transfer(snapshot, sender_openid="a", recipient_openid="b", amount=2)

    assert snapshot.players[0].cash == 3
    assert snapshot.players[1].cash == 7
    assert all(player.ready is False for player in snapshot.players)
    assert all(slot.active for slot in snapshot.all_slots())


def test_transfer_rejects_self_overdraft_and_bad_amounts() -> None:
    snapshot = make_snapshot({"a": [Role.DRIVER], "b": [Role.BRUTE]})

    with pytest.raises(RuleError):
        rules.transfer(snapshot, sender_openid="a", recipient_openid="a", amount=1)
    with pytest.raises(RuleError):
        rules.transfer(snapshot, sender_openid="a", recipient_openid="b", amount=6)
    with pytest.raises(RuleError):
        rules.transfer(snapshot, sender_openid="a", recipient_openid="b", amount=0)


def test_leave_only_deactivates_the_slot_and_refunds() -> None:
    snapshot = make_snapshot({"a": [Role.DRIVER], "b": [Role.BRUTE]})
    rules.collect_antes(snapshot, snapshot.loot_deck[0])
    snapshot.players[0].ready = True

    rules.leave_slot(snapshot, actor_openid="a", slot_id="a:0")

    slot = snapshot.players[0].slots[0]
    assert slot.active is False
    assert snapshot.players[0].cash == 5
    assert snapshot.players[1].cash == 4
    assert snapshot.players[0].ready is False
    with pytest.raises(RuleError):
        rules.leave_slot(snapshot, actor_openid="a", slot_id="a:0")


def test_three_player_leave_is_per_slot() -> None:
    snapshot = make_snapshot(
        {
            "a": [Role.DRIVER, Role.BRUTE],
            "b": [Role.CROOK, Role.SNITCH],
            "c": [Role.MASTERMIND, Role.DRIVER],
        }
    )
    rules.collect_antes(snapshot, snapshot.loot_deck[0])

    rules.leave_slot(snapshot, actor_openid="a", slot_id="a:0")

    assert snapshot.players[0].slots[0].active is False
    assert snapshot.players[0].slots[1].active is True
    assert snapshot.players[0].has_active_slot() is True
