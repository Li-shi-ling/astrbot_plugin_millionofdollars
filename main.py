"""《百万美金》AstrBot 插件入口。

设计依据：``docs/game-implementation-design.md`` 第 3、9 节。

本文件只做两件事：注册插件、把 AstrBot 命令路由到
:class:`~game.service.GameService`，并把回复交给
:class:`~game.qqofficial` 发送。规则逻辑不得写在这里。
"""

from __future__ import annotations

import sys
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

try:  # AstrBot 以包形式加载插件时走相对导入
    from .game import loot as loot_module
    from .game import qqofficial
    from .game.models import RuleError
    from .game.repository import GameRepository
    from .game.service import GameService, Reply, RequestContext
    from .game.tokens import TokenSigner
except ImportError:  # pragma: no cover - 兼容以顶层模块加载
    plugin_dir = Path(__file__).resolve().parent
    if str(plugin_dir) not in sys.path:
        sys.path.insert(0, str(plugin_dir))
    from game import loot as loot_module
    from game import qqofficial
    from game.models import RuleError
    from game.repository import GameRepository
    from game.service import GameService, Reply, RequestContext
    from game.tokens import TokenSigner

PLUGIN_NAME = "astrbot_plugin_millionofdollars"
COMMAND_NAME = "百万美金"
DB_FILENAME = "millionofdollars.sqlite3"
SECRET_FILENAME = "hmac_secret.bin"

_KNOWN_ACTIONS = (
    # 长指令必须排在短指令之前，否则 "退出房间" 会被 "退出" 抢先匹配
    "取消准备",
    "强制抢劫",
    "使用威胁牌",
    "退出房间",
    "关闭房间",
    "关闭",
    "结束",
    "解散",
    "威胁牌",
    "规则卡",
    "规则",
    "选角",
    "创建",
    "加入",
    "开始",
    "状态",
    "菜单",
    "帮助",
    "转账",
    "退出",
    "准备",
    "操作",
)

REGISTERED_COMMANDS = (
    "百万美金",
    "百万美金菜单",
    "百万美金帮助",
    "百万美金创建",
    "百万美金加入",
    "百万美金退出房间",
    "百万美金关闭",
    "百万美金开始",
    "百万美金状态",
    "百万美金选角",
    "百万美金转账",
    "百万美金退出",
    "百万美金准备",
    "百万美金取消准备",
    "百万美金强制抢劫",
    "百万美金使用威胁牌",
    "百万美金操作",
)
"""AstrBot 指令列表中公开显示的完整命令。"""


@register(PLUGIN_NAME, "Li-shi-ling", "《百万美金》桌游插件", "v1.7.5")
class MillionsOfDollarsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._service: GameService | None = None

    async def initialize(self) -> None:
        data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        repository = GameRepository(data_dir / DB_FILENAME)
        repository.initialize()
        signer = TokenSigner.load_or_create(data_dir / SECRET_FILENAME)
        self._service = GameService(repository, signer)
        logger.info("[百万美金] 插件初始化完成，数据目录：%s", data_dir)

    async def terminate(self) -> None:
        self._service = None
        logger.info("[百万美金] 插件已卸载。")

    # ------------------------------------------------------------------
    # 命令
    # ------------------------------------------------------------------

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金")
    async def million_dollars(self, event: AstrMessageEvent):
        """打开《百万美金》快捷操作菜单。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金菜单")
    async def million_dollars_menu(self, event: AstrMessageEvent):
        """打开《百万美金》快捷操作菜单。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金帮助", alias={"百万美金规则", "百万美金规则卡"})
    async def million_dollars_help(self, event: AstrMessageEvent):
        """查看《百万美金》玩法说明和规则卡。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金创建")
    async def million_dollars_create(self, event: AstrMessageEvent):
        """在当前群创建房间并成为首领。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金加入")
    async def million_dollars_join(self, event: AstrMessageEvent):
        """加入当前群等待开始的房间。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金退出房间")
    async def million_dollars_leave_room(self, event: AstrMessageEvent):
        """在游戏开始前退出当前房间。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command(
        "百万美金关闭",
        alias={"百万美金关闭房间", "百万美金结束", "百万美金解散"},
    )
    async def million_dollars_close(self, event: AstrMessageEvent):
        """由首领或管理员关闭当前房间。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金开始")
    async def million_dollars_start(self, event: AstrMessageEvent):
        """由首领开始当前群的游戏。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金状态")
    async def million_dollars_status(self, event: AstrMessageEvent):
        """查看当前房间和游戏状态。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金选角")
    async def million_dollars_roles(self, event: AstrMessageEvent):
        """重新获取自己的秘密选角按钮。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金转账")
    async def million_dollars_transfer(self, event: AstrMessageEvent):
        """选择收款玩家和转账金额。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金退出")
    async def million_dollars_leave_round(self, event: AstrMessageEvent):
        """退出当前回合并收回对应保证金。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金准备")
    async def million_dollars_ready(self, event: AstrMessageEvent):
        """在谈判阶段标记自己已经准备。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金取消准备")
    async def million_dollars_unready(self, event: AstrMessageEvent):
        """取消自己的谈判准备状态。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金强制抢劫")
    async def million_dollars_force_rob(self, event: AstrMessageEvent):
        """谈判超时后由首领强制开始抢劫。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金使用威胁牌", alias={"百万美金威胁牌"})
    async def million_dollars_threat(self, event: AstrMessageEvent):
        """使用一张威胁牌查看其他人物身份。"""
        async for result in self._handle_registered_command(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("百万美金操作")
    async def million_dollars_action(self, event: AstrMessageEvent):
        """处理由秘密按钮生成的一次性操作令牌。"""
        async for result in self._handle_registered_command(event):
            yield result

    async def _handle_registered_command(self, event: AstrMessageEvent):
        """让每个完整注册指令共用身份提取、异常处理与 QQ 回复流程。"""
        try:
            if not qqofficial.is_qqofficial_message_event(event):
                yield event.plain_result("《百万美金》目前仅支持 QQ 官方机器人群聊。")
                return

            context = qqofficial.extract_context(event)
            if context is None:
                yield event.plain_result("无法从消息中识别群或玩家身份，请稍后重试。")
                return

            if self._service is None:
                yield event.plain_result("插件尚未初始化完成，请稍后重试。")
                return

            request = RequestContext(
                platform_id=context.platform_id,
                group_openid=context.group_openid,
                member_openid=context.member_openid,
                display_name=context.display_name,
                message_id=context.message_id,
                is_admin=_is_admin(event),
            )
            try:
                reply = await self._dispatch(event.get_message_str(), request)
            except RuleError as exc:
                reply = Reply(str(exc))
            except loot_module.DeckNotVerifiedError as exc:
                reply = Reply(f"暂时无法开局：{exc}")
            except Exception as exc:  # noqa: BLE001 - 兜底，避免插件异常中断
                logger.exception("[百万美金] 处理指令失败：%s", exc)
                reply = Reply("处理指令时出错，请稍后重试或联系管理员查看日志。")
            if reply is None:
                return

            await qqofficial.send_reply(event, context, reply)
        finally:
            _stop_llm(event)

    # ------------------------------------------------------------------
    # 路由
    # ------------------------------------------------------------------

    async def _dispatch(
        self,
        message_str: str,
        request: RequestContext,
    ) -> Reply | None:
        service = self._service
        if service is None:
            return Reply("插件尚未初始化完成，请稍后重试。")

        action, argument = _parse_command(message_str)

        if action in {"", "菜单"}:
            return await service.menu(request)
        if action in {"帮助", "规则", "规则卡", "help"}:
            return await service.help(request)
        if action == "选角":
            return await service.role_menu(request)
        if action == "创建":
            return await service.create(request)
        if action == "加入":
            return await service.join(request)
        if action == "开始":
            return await service.start(request)
        if action == "状态":
            return await service.status(request)
        if action == "转账":
            if argument:
                return await service.transfer_amounts(request, argument)
            return await service.transfer_menu(request)
        if action == "退出房间":
            return await service.leave_room(request)
        if action in {"关闭", "关闭房间", "结束", "解散"}:
            return await service.close_room(request)
        if action == "退出":
            return await service.leave_menu(request)
        if action == "准备":
            return await service.set_ready(request, True)
        if action == "取消准备":
            return await service.set_ready(request, False)
        if action == "强制抢劫":
            return await service.force_rob(request)
        if action in {"使用威胁牌", "威胁牌"}:
            return await service.threat_card_menu(request)
        if action == "操作":
            if not argument:
                return Reply("缺少操作令牌，请重新点击按钮。")
            return await service.handle_token(request, argument)

        return Reply(
            f"没有「{action}」这个操作。\n"
            "请打开菜单查看当前可用操作，或通过帮助按钮查看规则卡。"
        )


def _stop_llm(event: AstrMessageEvent) -> None:
    """阻止本次消息继续进入 AstrBot 默认 LLM 链路。

    AstrBot 只有在「插件调用过 ``event.send``」或「事件被 stop」时才不会调用
    默认 LLM；本插件用 ``post_group_message`` 直发，因此必须显式 stop。
    """
    should_call_llm = getattr(event, "should_call_llm", None)
    if callable(should_call_llm):
        try:
            # 语义：该事件自行处理，跳过默认 LLM 请求
            should_call_llm(True)
        except Exception:  # noqa: BLE001 - AstrBot 版本差异时忽略
            pass
    event.stop_event()


def _is_admin(event: AstrMessageEvent) -> bool:
    """判断发送者是否为 AstrBot 管理员（用于关闭房间）。"""
    if getattr(event, "role", "") == "admin":
        return True
    for attr in ("is_admin", "is_group_admin", "is_group_owner"):
        checker = getattr(event, attr, None)
        if callable(checker):
            try:
                if checker():
                    return True
            except TypeError:  # pragma: no cover - 某些平台需要参数
                continue
        elif checker:
            return True
    return False


def _parse_command(message_str: str) -> tuple[str, str]:
    """从完整注册指令中取出游戏动作与参数。

    兼容 ``百万美金 创建``、``/百万美金 创建`` 与 ``百万美金创建`` 三种写法。
    """
    text = (message_str or "").strip()
    while text.startswith(("/", "／")):
        text = text[1:].strip()
    if text.startswith(COMMAND_NAME):
        text = text[len(COMMAND_NAME) :]
    text = text.strip()
    if not text:
        return "", ""

    for name in _KNOWN_ACTIONS:
        if text.startswith(name):
            return name, text[len(name) :].strip()

    head, _, tail = text.partition(" ")
    return head, tail.strip()
