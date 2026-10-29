"""Generate documentation images for the tutorial.

Run after capturing the raw GUI screenshots:
    python docs/make_images.py
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
IMAGES = HERE / "images"

FONT_UI = r"C:\Windows\Fonts\msyh.ttc"
FONT_UI_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_MONO = r"C:\Windows\Fonts\consola.ttf"

ACCENT = (31, 111, 235)
INK = (22, 50, 79)
MUTED = (102, 112, 133)
LIGHT = (243, 245, 248)
BORDER = (214, 222, 233)
WHITE = (255, 255, 255)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def rounded(draw: ImageDraw.ImageDraw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def annotate_overview() -> None:
    raw = IMAGES / "01_overview_raw.png"
    if not raw.exists():
        print(f"skip (missing): {raw}")
        return

    src = Image.open(raw).convert("RGB")
    gutter = 58
    canvas = Image.new("RGB", (src.width + gutter, src.height), LIGHT)
    canvas.paste(src, (gutter, 0))

    draw = ImageDraw.Draw(canvas)
    draw.line([(gutter - 1, 0), (gutter - 1, src.height)], fill=(217, 224, 234), width=1)

    rows = [
        (207, "1"),
        (250, "2"),
        (292, "3"),
        (333, "4"),
        (373, "5"),
        (462, "6"),
        (750, "7"),
    ]
    for y, label in rows:
        r = 15
        draw.ellipse((gutter // 2 - r + 1, y - r, gutter // 2 + r + 1, y + r), fill=ACCENT)
        draw.text(
            (gutter // 2 + 1, y),
            label,
            font=font(FONT_UI_BOLD, 16),
            fill=WHITE,
            anchor="mm",
        )

    canvas.save(IMAGES / "01_overview.png", optimize=True)
    print("written 01_overview.png")


def make_workflow() -> None:
    width, height = 1600, 580
    image = Image.new("RGB", (width, height), (245, 248, 252))
    draw = ImageDraw.Draw(image)

    draw.text(
        (80, 46),
        "从构建产物到 Source Insight 文件清单",
        font=font(FONT_UI_BOLD, 40),
        fill=INK,
    )
    draw.text(
        (82, 104),
        "只收录真实参与编译的源文件和头文件，避免把整个目录树都索引进去",
        font=font(FONT_UI, 21),
        fill=MUTED,
    )

    cards = [
        (
            120,
            "1",
            "构建产物",
            ["Debug/**/subdir.mk", "Debug/**/*.d"],
            "先完整编译一次工程",
            (31, 111, 235),
            (232, 241, 255),
        ),
        (
            470,
            "2",
            "解析与过滤",
            ["源文件 + 头文件", "去重 / 存在性校验"],
            "自动跳过无效路径",
            (13, 148, 136),
            (228, 247, 244),
        ),
        (
            820,
            "3",
            "生成清单",
            ["SI_xxx_filelist.txt", "相对路径 / UTF-8 BOM"],
            "可直接导入 Source Insight",
            (46, 125, 50),
            (235, 247, 235),
        ),
        (
            1170,
            "4",
            "导入 SI",
            ["Add from list…", "Project Source Root"],
            "完成工程索引",
            (196, 106, 20),
            (255, 243, 228),
        ),
    ]

    card_y, card_w, card_h = 170, 310, 270
    for x, number, title, lines, note, color, tint in cards:
        draw.rounded_rectangle(
            (x + 5, card_y + 8, x + card_w + 5, card_y + card_h + 8),
            radius=22,
            fill=(229, 235, 243),
        )
        draw.rounded_rectangle(
            (x, card_y, x + card_w, card_y + card_h),
            radius=22,
            fill=WHITE,
            outline=BORDER,
            width=2,
        )
        draw.ellipse((x + 28, card_y + 28, x + 80, card_y + 80), fill=color)
        draw.text(
            (x + 54, card_y + 53),
            number,
            font=font(FONT_UI_BOLD, 26),
            fill=WHITE,
            anchor="mm",
        )
        draw.text(
            (x + 96, card_y + 32),
            title,
            font=font(FONT_UI_BOLD, 27),
            fill=INK,
        )
        text_y = card_y + 112
        for line in lines:
            line_font = (
                font(FONT_UI, 20)
                if any(ord(char) > 127 for char in line)
                else font(FONT_MONO, 19)
            )
            draw.text((x + 30, text_y), line, font=line_font, fill=(52, 64, 84))
            text_y += 34
        draw.rounded_rectangle(
            (x + 24, card_y + card_h - 66, x + card_w - 24, card_y + card_h - 20),
            radius=12,
            fill=tint,
        )
        draw.text(
            (x + card_w // 2, card_y + card_h - 43),
            note,
            font=font(FONT_UI, 18),
            fill=color,
            anchor="mm",
        )

    arrow_y = card_y + 115
    for x in (430, 780, 1130):
        draw.line((x + 6, arrow_y, x + 32, arrow_y), fill=(138, 164, 192), width=5)
        draw.polygon(
            [(x + 32, arrow_y - 9), (x + 46, arrow_y), (x + 32, arrow_y + 9)],
            fill=(138, 164, 192),
        )

    draw.rounded_rectangle((120, 482, 1480, 542), radius=14, fill=(236, 242, 250))
    draw.text(
        (800, 512),
        "清单之外的文件（例如 BSP 头文件）单独写入 SI_xxx_outside_root.txt，便于核对",
        font=font(FONT_UI, 20),
        fill=(52, 80, 112),
        anchor="mm",
    )

    image.save(IMAGES / "00_workflow.png", optimize=True)
    print("written 00_workflow.png")


def make_filelist_preview() -> None:
    width, height = 1440, 820
    image = Image.new("RGB", (width, height), (245, 248, 252))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((48, 54, 1408, 774), radius=24, fill=(221, 228, 238))
    draw.rounded_rectangle((40, 40, 1400, 760), radius=24, fill=(13, 23, 38))

    draw.rounded_rectangle((40, 40, 1400, 104), radius=24, fill=(22, 50, 79))
    draw.rectangle((40, 80, 1400, 104), fill=(22, 50, 79))

    for cx, color in ((72, (255, 95, 86)), (102, (255, 189, 46)), (132, (39, 201, 63))):
        draw.ellipse((cx - 8, 64, cx + 8, 80), fill=color)

    draw.text(
        (166, 72),
        "SI_Demo_filelist.txt",
        font=font(FONT_UI, 22),
        fill=(215, 227, 242),
        anchor="lm",
    )
    draw.rounded_rectangle((1240, 60, 1368, 92), radius=10, fill=(30, 64, 96))
    draw.text(
        (1304, 76),
        "UTF-8 BOM",
        font=font(FONT_UI, 15),
        fill=(185, 205, 226),
        anchor="mm",
    )

    lines = [
        ("; Source Insight Project File List", "comment"),
        ("; Project Name: SI_Demo", "comment"),
        ("; Xilinx Project: Prj_Demo", "comment"),
        ("; Build Config: Debug", "comment"),
        (r"; Source Root: C:\Users\Public\SI_Demo\trunk\CtrlSW", "comment"),
        ("; Generated by Source Insight 文件清单生成器 1.0.0", "comment"),
        ("; Version=4.00.0150", "comment"),
        (";", "comment"),
        (r"inc\app.h", "path"),
        (r"inc\config.h", "path"),
        (r"inc\uart.h", "path"),
        (r"src\app_task.c", "path"),
        (r"src\driver_uart.c", "path"),
        (r"src\main.c", "path"),
        (r"src\utils.c", "path"),
    ]

    line_h = 35
    top = 150
    draw.rounded_rectangle(
        (60, top - 8, 1380, top + len(lines) * line_h + 2),
        radius=12,
        fill=(16, 29, 47),
    )

    number_font = font(FONT_MONO, 19)
    mono_font = font(FONT_MONO, 21)
    cn_font = font(FONT_UI, 20)

    for index, (text, kind) in enumerate(lines):
        y = top + index * line_h
        draw.text(
            (108, y),
            str(index + 1),
            font=number_font,
            fill=(86, 101, 124),
            anchor="ra",
        )
        if "文件清单生成器" in text:
            use_font = cn_font
        else:
            use_font = mono_font
        color = (125, 140, 163) if kind == "comment" else (121, 192, 255)
        draw.text((128, y), text, font=use_font, fill=color)

    draw.rounded_rectangle((1224, 660, 1374, 704), radius=12, fill=(24, 63, 54))
    draw.text(
        (1299, 682),
        "7 个有效条目",
        font=font(FONT_UI_BOLD, 17),
        fill=(61, 220, 151),
        anchor="mm",
    )

    draw.text(
        (60, 722),
        "路径相对于 Project Source Root；分号开头为注释行。",
        font=font(FONT_UI, 18),
        fill=(125, 140, 163),
    )

    image.save(IMAGES / "03_filelist.png", optimize=True)
    print("written 03_filelist.png")


def copy_result() -> None:
    raw = IMAGES / "02_result_raw.png"
    if raw.exists():
        Image.open(raw).convert("RGB").save(IMAGES / "02_result.png", optimize=True)
        print("written 02_result.png")


if __name__ == "__main__":
    os.makedirs(IMAGES, exist_ok=True)
    annotate_overview()
    copy_result()
    make_workflow()
    make_filelist_preview()
