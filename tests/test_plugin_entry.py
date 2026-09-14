"""插件入口与指令契约测试（设计文档第 9 节）。"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("astrbot", reason="需要在 AstrBot 的 uv 环境中运行")

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def load_main():
    spec = importlib.util.spec_from_file_location(
        "millionofdollars_main",
        PLUGIN_ROOT / "main.py",
        submodule_search_locations=[str(PLUGIN_ROOT)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def main_module():
    return load_main()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("百万美金", ("", "")),
        ("/百万美金", ("", "")),
        ("百万美金 创建", ("创建", "")),
        ("/百万美金 创建", ("创建", "")),
        ("百万美金创建", ("创建", "")),
        ("百万美金 开始", ("开始", "")),
        ("百万美金 状态", ("状态", "")),
        ("百万美金 菜单", ("菜单", "")),
        ("百万美金 加入", ("加入", "")),
        ("百万美金 准备", ("准备", "")),
        ("百万美金 取消准备", ("取消准备", "")),
        ("百万美金 退出", ("退出", "")),
        ("百万美金 强制抢劫", ("强制抢劫", "")),
        ("百万美金 使用威胁牌", ("使用威胁牌", "")),
        ("百万美金 转账", ("转账", "")),
        ("百万美金 转账 user-b", ("转账", "user-b")),
        ("百万美金 操作 abcdef", ("操作", "abcdef")),
    ],
)
def test_parse_command_contract(main_module, message, expected) -> None:
    assert main_module._parse_command(message) == expected


def test_plugin_metadata_and_registration(main_module) -> None:
    from astrbot.api.star import Star
    from astrbot.core.star.star import star_map

    assert main_module.PLUGIN_NAME == "astrbot_plugin_millionofdollars"
    plugin_cls = main_module.MillionsOfDollarsPlugin
    assert issubclass(plugin_cls, Star)
    metadata = star_map.get(plugin_cls.__module__)
    assert metadata is not None
    assert metadata.name == main_module.PLUGIN_NAME
    # 实例化必须可用于 LogManager，且不依赖已初始化的 StarTools
    plugin = plugin_cls(SimpleNamespace())
    assert plugin._service is None


def test_plugin_initialize_creates_data_dir_and_secret(
    main_module, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        main_module.StarTools,
        "get_data_dir",
        classmethod(lambda cls, name=None: tmp_path / (name or "plugin")),
    )
    plugin = main_module.MillionsOfDollarsPlugin(SimpleNamespace())

    import asyncio

    asyncio.run(plugin.initialize())

    data_dir = tmp_path / main_module.PLUGIN_NAME
    assert (data_dir / main_module.DB_FILENAME).exists()
    secret = data_dir / main_module.SECRET_FILENAME
    assert secret.exists()
    assert len(secret.read_bytes()) == 32


def test_plugin_can_start_a_game_with_the_verified_deck(
    main_module, monkeypatch, tmp_path
) -> None:
    """走 main.py 的真实路由：创建 → 加入 → 开始，验证已核验牌组可以开局。"""
    import asyncio

    monkeypatch.setattr(
        main_module.StarTools,
        "get_data_dir",
        classmethod(lambda cls, name=None: tmp_path / (name or "plugin")),
    )
    plugin = main_module.MillionsOfDollarsPlugin(SimpleNamespace(get_config=lambda: None))
    asyncio.run(plugin.initialize())

    def request(member: str, message_id: str) -> object:
        return main_module.RequestContext(
            platform_id="qq_official_instance",
            group_openid="group-1",
            member_openid=member,
            display_name=member,
            message_id=message_id,
        )

    async def play() -> tuple:
        created = await plugin._dispatch("百万美金 创建", request("a", "m1"))
        for index, member in enumerate(["b", "c", "d"], start=1):
            await plugin._dispatch("百万美金 加入", request(member, f"m-join-{index}"))
        started = await plugin._dispatch("百万美金 开始", request("a", "m-start"))
        status = await plugin._dispatch("百万美金 状态", request("a", "m-status"))
        return created, started, status

    created, started, status = asyncio.run(play())

    assert "已创建房间" in created.text
    assert "游戏开始" in started.text
    assert len(started.extra) == 4  # 每位玩家一条秘密选角消息
    assert "阶段：role_selection" in status.text
    assert re.search(r"赃物：(8|9|10|12) 百万美元", status.text)
