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

MENU_TEXT = (
    "## 百万美金\n"
    "3～8 人桌游。所有按钮都等价于一条文本指令。\n\n"
    "百万美金 创建 / 加入 / 开始 / 状态 / 菜单\n"
    "百万美金 转账 / 退出 / 准备 / 取消准备\n"
    "百万美金 使用威胁牌 / 强制抢劫"
)

_KNOWN_SUBCOMMANDS = (
    "取消准备",
    "强制抢劫",
    "使用威胁牌",
    "威胁牌",
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


@register(PLUGIN_NAME, "Li-shi-ling", "《百万美金》桌游插件", "v1.5.0")
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

    @filter.command(COMMAND_NAME)
    async def million_dollars(self, event: AstrMessageEvent):
        """《百万美金》主指令。"""
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

        subcommand, argument = _parse_command(message_str)

        if subcommand in {"", "菜单", "帮助"}:
            return await service.menu(request)
        if subcommand == "创建":
            return await service.create(request)
        if subcommand == "加入":
            return await service.join(request)
        if subcommand == "开始":
            return await service.start(request)
        if subcommand == "状态":
            return await service.status(request)
        if subcommand == "转账":
            if argument:
                return await service.transfer_amounts(request, argument)
            return await service.transfer_menu(request)
        if subcommand == "退出":
            return await service.leave_menu(request)
        if subcommand == "准备":
            return await service.set_ready(request, True)
        if subcommand == "取消准备":
            return await service.set_ready(request, False)
        if subcommand == "强制抢劫":
            return await service.force_rob(request)
        if subcommand in {"使用威胁牌", "威胁牌"}:
            return await service.threat_card_menu(request)
        if subcommand == "操作":
            if not argument:
                return Reply("缺少操作令牌，请重新点击按钮。")
            return await service.handle_token(request, argument)

        return Reply(f"未知的子指令：{subcommand}\n\n{MENU_TEXT}")


def _parse_command(message_str: str) -> tuple[str, str]:
    """从消息中取出子指令与参数。

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

    for name in _KNOWN_SUBCOMMANDS:
        if text.startswith(name):
            return name, text[len(name) :].strip()

    head, _, tail = text.partition(" ")
    return head, tail.strip()
