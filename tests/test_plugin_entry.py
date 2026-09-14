"""插件入口与指令契约测试（设计文档第 9 节）。"""

from __future__ import annotations

import importlib.util
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
