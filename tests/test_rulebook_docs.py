from __future__ import annotations

import hashlib
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PLUGIN_ROOT / "docs"

RULEBOOKS = {
    "millions-of-dollars-2016-rulebook-en.pdf": (
        1_641_996,
        "1b819919de0a8420bee3e9d7faa0be2520e44bc7c0583e1ba6a5f6964b795fcd",
    ),
    "millions-of-dollars-2024-rulebook-en.pdf": (
        1_217_481,
        "bef46367091fbb93e304baf763139b5119ace68a43effea556cb32714faaf5d3",
    ),
}


def test_rulebook_pdfs_are_complete_downloads() -> None:
    sources_dir = DOCS_DIR / "sources"

    for filename, (expected_size, expected_sha256) in RULEBOOKS.items():
        content = (sources_dir / filename).read_bytes()

        assert len(content) == expected_size
        assert content.startswith(b"%PDF-")
        assert content.rstrip().endswith(b"%%EOF")
        assert hashlib.sha256(content).hexdigest() == expected_sha256


def test_chinese_rulebook_covers_the_complete_2016_structure() -> None:
    content = (DOCS_DIR / "million-of-dollars-rules-zh.md").read_text(
        encoding="utf-8"
    )

    required_sections = (
        "## 1. 游戏目标",
        "## 2. 游戏配件",
        "## 3. 游戏准备",
        "### 4.1 筹划阶段",
        "### 4.2 谈判阶段",
        "### 4.3 抢劫阶段",
        "### 4.4 分赃阶段",
        "## 5. 回合结束与胜利条件",
        "## 6. 可选规则：不会再上同一个当",
        "## 7. 3 人局规则",
        "## 9. 原始资料与版权说明",
    )

    for section in required_sections:
        assert section in content

    assert "2000 万美元" in content
    assert "第 8 轮" in content
    assert "2024 二版改为 5 轮、5000 万美元获胜" in content


def test_implementation_design_records_the_frozen_qq_flow() -> None:
    content = (DOCS_DIR / "game-implementation-design.md").read_text(
        encoding="utf-8"
    )

    required_sections = (
        "## 3. 模块边界",
        "## 5. 状态机",
        "### 5.3 QQ 群谈判",
        "## 6. HMAC 动作协议",
        "## 7. 威胁牌的特殊按钮",
        "## 8. 持久化与事务",
        "## 11. 测试验收矩阵",
    )
    for section in required_sections:
        assert section in content

    assert "转账不会导致退出，退出不会附带转账" in content
    assert "插件不提供报价对象、报价金额、接受或拒绝状态" in content
    assert "action.data" in content
    assert "不具备 HMAC 选角按钮的服务端密码学保密" in content
    assert "不使用 C2C" in content


def test_qqofficial_guide_links_to_the_game_design_and_marks_threat_exception() -> None:
    content = (DOCS_DIR / "qqofficial-bot-development.md").read_text(
        encoding="utf-8"
    )

    assert "./game-implementation-design.md" in content
    assert "秘密动作令牌" in content
    assert "威胁牌按钮例外" in content
    assert 'visited_label": "已提交"' in content
