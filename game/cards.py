"""卡图合成。

身份揭露时把本轮参与抢劫的角色卡合并成**一张**图片发送；卡片顺序由调用方
打乱，避免固定顺序暗示任何玩家与角色的对应关系。

本模块不导入 AstrBot 或 botpy：输出目录与随机源都由调用方提供。
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from pathlib import Path

CARD_HEIGHT = 402
GAP = 10
MARGIN = 14
BACKGROUND = (24, 26, 32)
LABEL_HEIGHT = 46
LABEL_BACKGROUND = (24, 26, 32)
LABEL_COLOR = (240, 240, 240)

CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)


class CardImageError(RuntimeError):
    """卡图合成失败。"""


def shuffled(paths: Sequence[Path], rng: secrets.SystemRandom | None = None) -> list[Path]:
    """用系统熵源打乱卡片顺序。"""
    result = list(paths)
    (rng or secrets.SystemRandom()).shuffle(result)
    return result


def compose_strip(
    image_paths: Sequence[Path],
    output_path: Path,
    *,
    labels: Sequence[str] | None = None,
    card_height: int = CARD_HEIGHT,
) -> Path:
    """把多张卡图横向拼成一张图片。

    Args:
        image_paths: 卡片图片路径，顺序即为最终顺序。
        output_path: 输出文件路径，父目录必须已存在。
        labels: 可选的卡片标题；只有系统存在中文字体时才绘制。
        card_height: 统一缩放后的卡片高度。

    Returns:
        输出文件路径。
    """
    from PIL import Image  # 延迟导入：纯逻辑测试不依赖 Pillow

    if not image_paths:
        raise CardImageError("没有可合成的卡图。")

    cards = []
    for path in image_paths:
        if not path.is_file():
            raise CardImageError(f"卡图不存在：{path}")
        image = Image.open(path).convert("RGB")
        ratio = card_height / image.height
        cards.append(image.resize((max(1, round(image.width * ratio)), card_height)))

    font = _label_font(round(card_height * 0.075))
    draw_labels = labels is not None and font is not None
    label_height = LABEL_HEIGHT if draw_labels else 0

    width = MARGIN * 2 + sum(card.width for card in cards) + GAP * (len(cards) - 1)
    height = MARGIN * 2 + card_height + label_height
    canvas = Image.new("RGB", (width, height), BACKGROUND)

    x = MARGIN
    for index, card in enumerate(cards):
        canvas.paste(card, (x, MARGIN))
        if draw_labels:
            _draw_label(
                canvas,
                font,
                str(labels[index]) if index < len(labels) else "",
                x,
                MARGIN + card_height,
                card.width,
                label_height,
            )
        x += card.width + GAP

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="JPEG", quality=88)
    return output_path


def _draw_label(canvas, font, text: str, x: int, y: int, width: int, height: int) -> None:
    from PIL import ImageDraw

    draw = ImageDraw.Draw(canvas)
    draw.rectangle([x, y, x + width, y + height], fill=LABEL_BACKGROUND)
    if not text:
        return
    box = draw.textbbox((0, 0), text, font=font)
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    draw.text(
        (x + (width - text_width) / 2 - box[0], y + (height - text_height) / 2 - box[1]),
        text,
        font=font,
        fill=LABEL_COLOR,
    )


def _label_font(size: int):
    """系统存在中文字体时返回字体对象，否则返回 ``None``（不绘制文字）。"""
    from PIL import ImageFont

    for candidate in CJK_FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:  # pragma: no cover - 字体损坏时跳过
                continue
    return None
