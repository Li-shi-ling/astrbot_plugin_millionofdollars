"""房间服务集成测试（设计文档 11.1、11.3、11.4）。"""

from __future__ import annotations

import random

import pytest
from game import loot
from game.models import Phase, RuleError
from game.repository import GameRepository
from game.service import ACTION_COMMAND_PREFIX, GameService, Reply, RequestContext
from game.tokens import TokenSigner

pytestmark = pytest.mark.asyncio

SECRET = bytes(range(32))


class Clock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def make_deck():
    """测试用牌组：10 张牌面完全一致，保证断言不受抽牌顺序影响。"""
    entries = [
        {
            "card_id": f"card-{index}",
            "amount": 8,
            "ante": 1,
            "bonus_role": None,
        }
        for index in range(loot.DECK_SIZE)
    ]
    return loot.validate_deck(entries)


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def service(tmp_path, clock) -> GameService:
    repository = GameRepository(tmp_path / "data" / "game.sqlite3")
    repository.initialize()
    return GameService(
        repository,
        TokenSigner(SECRET),
        deck_factory=make_deck,
        now=clock,
        rng=random.Random(7),
    )


def ctx(member: str, message_id: str, name: str = "") -> RequestContext:
    return RequestContext(
        platform_id="qq_official_instance",
        group_openid="group-1",
        member_openid=member,
        display_name=name or member,
        message_id=message_id,
    )


def token_from(reply: Reply) -> str:
    data = reply.buttons[0].data
    assert data.startswith(ACTION_COMMAND_PREFIX)
    return data[len(ACTION_COMMAND_PREFIX) :]


def button_token(button) -> str:
    assert button.data.startswith(ACTION_COMMAND_PREFIX)
    return button.data[len(ACTION_COMMAND_PREFIX) :]


def selection_message(reply: Reply, member: str) -> Reply:
    for item in reply.extra:
        if member in item.text:
            return item
    raise AssertionError(f"没有给 {member} 的选择消息")


async def make_lobby(service: GameService, players: list[str]) -> None:
    await service.create(ctx(players[0], "m-create"))
    for index, member in enumerate(players[1:], start=1):
        await service.join(ctx(member, f"m-join-{index}"))


async def start_game(service: GameService, players: list[str]) -> Reply:
    await make_lobby(service, players)
    return await service.start(ctx(players[0], "m-start"))


async def choose(service: GameService, member: str, reply: Reply, index: int = 0) -> Reply:
    token = button_token(selection_message(reply, member).buttons[index])
    return await service.handle_token(ctx(member, f"m-role-{member}-{index}"), token)


# ----------------------------------------------------------------------
# 大厅
# ----------------------------------------------------------------------


async def test_lobby_flow_and_rejections(service: GameService) -> None:
    reply = await service.create(ctx("a", "m1", "小明"))
    assert "首领" in reply.text

    # 幂等：同一条消息重复处理返回同一结果
    again = await service.create(ctx("a", "m1", "小明"))
    assert again.text == reply.text

    # 新消息重复创建会被拒绝
    duplicate = await service.create(ctx("a", "m2", "小明"))
    assert "已经有一局" in duplicate.text

    # 重复加入被拒绝
    await service.join(ctx("b", "m3", "小红"))
    assert "已经在房间" in (await service.join(ctx("b", "m4", "小红"))).text

    # 非首领不能开始
    assert "只有首领" in (await service.start(ctx("b", "m5"))).text

    # 人数不足不能开始
    assert "3～8" in (await service.start(ctx("a", "m6", "小明"))).text


async def test_status_reports_phase_without_leaking_hidden_roles(
    service: GameService,
) -> None:
    await start_game(service, ["a", "b", "c", "d"])

    status = await service.status(ctx("a", "m-status"))

    assert "阶段" in status.text
    assert "回合" in status.text
    assert "a" in status.text
    assert "隐藏" not in status.text


# ----------------------------------------------------------------------
# 选角
# ----------------------------------------------------------------------


async def test_start_deals_eight_cards_and_private_buttons(service: GameService) -> None:
    reply = await start_game(service, ["a", "b", "c", "d"])

    snapshot = service._repo.load("qq_official_instance", "group-1")
    assert snapshot is not None
    assert len(snapshot.loot_deck) == 8
    assert snapshot.phase is Phase.ROLE_SELECTION
    assert len(reply.extra) == 4
    for item in reply.extra:
        assert len(item.buttons) == 3  # 4 人局只有司机、暴徒、恶棍
        assert item.buttons[0].only_for is not None
        assert item.buttons[0].data.startswith(ACTION_COMMAND_PREFIX)


async def test_role_selection_moves_to_negotiation_and_collects_ante(
    service: GameService,
) -> None:
    players = ["a", "b", "c", "d"]
    start_reply = await start_game(service, players)
    roles = {
        "a": "driver",
        "b": "brute",
        "c": "crook",
        "d": "driver",
    }

    for member in players:
        selection = selection_message(start_reply, member)
        index = [button.label for button in selection.buttons].index(
            {"driver": "司机", "brute": "暴徒", "crook": "恶棍"}[roles[member]]
        )
        token = button_token(selection.buttons[index])
        await service.handle_token(ctx(member, f"role-{member}"), token)

    snapshot = service._repo.load("qq_official_instance", "group-1")
    assert snapshot is not None
    assert snapshot.phase is Phase.NEGOTIATION
    assert snapshot.negotiation_started_at == 1000.0
    assert all(slot.ante_total > 0 for slot in snapshot.all_slots())
    assert sum(snapshot.public_role_counts.values()) == 3  # 4 个槽位隐藏 1 个


async def test_three_players_choose_two_different_roles(service: GameService) -> None:
    players = ["a", "b", "c"]
    start_reply = await start_game(service, players)
    selection = selection_message(start_reply, "a")
    assert len(selection.buttons) == 5

    first_token = button_token(selection.buttons[0])
    first_reply = await service.handle_token(ctx("a", "r-a-1"), first_token)

    # 第二次选角只发给本人，且排除已选角色
    second = selection_message(first_reply, "a")
    labels = [button.label for button in second.buttons]
    assert len(labels) == 4
    assert selection.buttons[0].label not in labels

    # 旧令牌在代次递增后失效
    replay = await service.handle_token(ctx("a", "r-a-1-replay"), first_token)
    assert "失效" in replay.text


async def test_token_replay_is_rejected(service: GameService) -> None:
    players = ["a", "b", "c", "d"]
    start_reply = await start_game(service, players)
    token = button_token(selection_message(start_reply, "a").buttons[0])

    first = await service.handle_token(ctx("a", "replay-1"), token)
    assert "已提交" in first.text

    second = await service.handle_token(ctx("a", "replay-2"), token)
    assert "失效" in second.text


async def test_other_player_cannot_use_someone_elses_button(
    service: GameService,
) -> None:
    players = ["a", "b", "c", "d"]
    start_reply = await start_game(service, players)
    token = button_token(selection_message(start_reply, "a").buttons[0])

    stolen = await service.handle_token(ctx("b", "steal"), token)

    assert "失效" in stolen.text


# ----------------------------------------------------------------------
# 谈判期操作
# ----------------------------------------------------------------------


async def enter_negotiation(service: GameService, roles: dict[str, str]) -> None:
    players = list(roles)
    start_reply = await start_game(service, players)
    labels = {"driver": "司机", "brute": "暴徒", "crook": "恶棍"}
    for member in players:
        selection = selection_message(start_reply, member)
        index = [button.label for button in selection.buttons].index(labels[roles[member]])
        await service.handle_token(
            ctx(member, f"role-{member}"), button_token(selection.buttons[index])
        )


async def test_transfer_moves_money_without_leaving(service: GameService) -> None:
    await enter_negotiation(
        service,
        {"a": "driver", "b": "brute", "c": "crook", "d": "driver"},
    )

    menu = await service.transfer_menu(ctx("a", "t-menu"))
    assert {button.label for button in menu.buttons} == {"b", "c", "d"}

    amounts = await service.transfer_amounts(ctx("a", "t-amounts"), "b")
    button = next(item for item in amounts.buttons if item.label == "2 百万")
    await service.handle_token(ctx("a", "t-confirm"), button_token(button))

    snapshot = service._repo.load("qq_official_instance", "group-1")
    assert snapshot is not None
    assert snapshot.players[0].cash == 2
    assert snapshot.players[1].cash == 6
    assert all(slot.active for slot in snapshot.all_slots())
    assert all(player.ready is False for player in snapshot.players)


async def test_leave_refunds_ante_and_blocks_further_actions(
    service: GameService,
) -> None:
    await enter_negotiation(
        service,
        {"a": "driver", "b": "brute", "c": "crook", "d": "driver"},
    )

    menu = await service.leave_menu(ctx("c", "l-menu"))
    await service.handle_token(ctx("c", "l-confirm"), token_from(menu))

    snapshot = service._repo.load("qq_official_instance", "group-1")
    assert snapshot is not None
    assert snapshot.players[2].slots[0].active is False
    assert snapshot.players[2].cash == 5

    # 已退出的玩家不能继续转账（由 main 捕获后回复文本）
    with pytest.raises(RuleError):
        await service.transfer_menu(ctx("c", "l-transfer"))


async def test_ready_requires_all_participants(service: GameService) -> None:
    await enter_negotiation(
        service,
        {"a": "driver", "b": "brute", "c": "crook", "d": "driver"},
    )

    first = await service.set_ready(ctx("a", "ready-a"), True)
    assert first.text.startswith("a 已准备")

    await service.set_ready(ctx("b", "ready-b"), True)
    await service.set_ready(ctx("c", "ready-c"), True)
    last = await service.set_ready(ctx("d", "ready-d"), True)

    assert "立即结算" in last.text
    snapshot = service._repo.load("qq_official_instance", "group-1")
    assert snapshot is not None
    assert snapshot.phase in {Phase.ROLE_SELECTION, Phase.GAME_OVER}


async def test_force_rob_is_leader_only_and_delayed(service: GameService, clock: Clock) -> None:
    await enter_negotiation(
        service,
        {"a": "driver", "b": "brute", "c": "crook", "d": "driver"},
    )

    assert "只有当前首领" in (await service.force_rob(ctx("b", "fr-b"))).text

    early = await service.force_rob(ctx("a", "fr-a"))
    assert "秒" in early.text

    clock.value += 61
    forced = await service.force_rob(ctx("a", "fr-a-late"))
    assert "强制结束谈判" in forced.text

    # 强制抢劫后本轮谈判立即结束
    snapshot = service._repo.load("qq_official_instance", "group-1")
    assert snapshot is not None
    assert snapshot.phase is not Phase.NEGOTIATION


async def test_threat_card_buttons_are_private_and_plaintext(
    service: GameService,
) -> None:
    await enter_negotiation(
        service,
        {"a": "brute", "b": "driver", "c": "crook", "d": "driver"},
    )
    snapshot = service._repo.load("qq_official_instance", "group-1")
    assert snapshot is not None
    # 给 a 手工补一张威胁牌用于测试
    snapshot.players[0].threat_cards = 1
    service._repo.save(snapshot)

    reply = await service.threat_card_menu(ctx("a", "threat"))

    assert reply.buttons
    for button in reply.buttons:
        assert button.only_for == "a"
        assert button.data.startswith("查看结果：")
        assert button.visited_label == "已查看"


async def test_action_token_requires_current_phase(service: GameService) -> None:
    players = ["a", "b", "c", "d"]
    start_reply = await start_game(service, players)
    token = button_token(selection_message(start_reply, "a").buttons[0])

    # 换一个房间使用同一令牌必须失败
    with pytest.raises(RuleError):
        await service.handle_token(
            RequestContext(
                platform_id="qq_official_instance",
                group_openid="group-2",
                member_openid="a",
                display_name="a",
                message_id="cross-room",
            ),
            token,
        )


# ----------------------------------------------------------------------
# 端到端一局
# ----------------------------------------------------------------------


async def test_full_round_reaches_resolution_and_next_round(
    service: GameService,
) -> None:
    """4 人一局：选角 → 转账 → 一个人退出 → 全员准备 → 结算并进入下一轮。"""
    players = ["a", "b", "c", "d"]
    start_reply = await start_game(service, players)
    labels = {"driver": "司机", "brute": "暴徒", "crook": "恶棍"}
    chosen = {"a": "driver", "b": "brute", "c": "crook", "d": "driver"}

    for member in players:
        selection = selection_message(start_reply, member)
        index = [button.label for button in selection.buttons].index(labels[chosen[member]])
        await service.handle_token(
            ctx(member, f"e2e-role-{member}"), button_token(selection.buttons[index])
        )

    # 转账：a 给 b 1 百万
    amounts = await service.transfer_amounts(ctx("a", "e2e-transfer-menu"), "b")
    one = next(button for button in amounts.buttons if button.label == "1 百万")
    await service.handle_token(ctx("a", "e2e-transfer"), button_token(one))

    # d 退出本轮
    leave = await service.leave_menu(ctx("d", "e2e-leave"))
    await service.handle_token(ctx("d", "e2e-leave-confirm"), button_token(leave.buttons[0]))

    # 剩下 a、b、c 准备
    for member in ["a", "b", "c"]:
        await service.set_ready(ctx(member, f"e2e-ready-{member}"), True)

    snapshot = service._repo.load("qq_official_instance", "group-1")
    assert snapshot is not None
    # d 退出后只剩 a（司机）、b（暴徒）、c（恶棍）三个活动槽位
    # 每个玩家：5 - 1 保证金（结算后退回）= 5
    # 再叠加：b 威胁牌 1 张；赃款 8 / 3 = 每份 2；每个分赃槽位向司机 a 付 1；
    #         恶棍 c 从暴徒 b 处夺取 2。
    cash = {player.member_openid: player.cash for player in snapshot.players}
    assert cash["a"] == 5 - 1 + 2 + 2  # 自己那份付给自己净额为 0，只收 b/c 各 1
    assert cash["b"] == 5 + 1 + 2 - 1 - 2
    assert cash["c"] == 5 + 2 - 1 + 2
    assert cash["d"] == 5  # 退出者收回完整保证金
    assert snapshot.players[1].threat_cards == 1  # 唯一暴徒保留威胁牌到下一轮
    assert snapshot.round_number == 2
    assert snapshot.phase is Phase.ROLE_SELECTION
