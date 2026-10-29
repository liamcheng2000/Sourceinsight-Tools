"""生成应用图标 app.ico（仅构建时使用）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 512
OUT = Path(__file__).with_name("app.ico")
PREVIEW = Path(__file__).with_name("app_preview.png")


def lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def main() -> None:
    top = (35, 111, 235)
    bottom = (13, 42, 71)

    gradient = Image.new("RGB", (SIZE, SIZE))
    pixels = gradient.load()
    for y in range(SIZE):
        t = y / (SIZE - 1)
        color = tuple(lerp(top[i], bottom[i], t) for i in range(3))
        for x in range(SIZE):
            pixels[x, y] = color

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=96, fill=255)

    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(gradient, (0, 0), mask)

    draw = ImageDraw.Draw(icon)

    # 文档阴影
    draw.rounded_rectangle((128, 96, 404, 448), radius=30, fill=(0, 0, 0, 55))
    # 文档主体
    draw.rounded_rectangle((116, 80, 392, 432), radius=30, fill="white")

    # 折角
    draw.polygon([(312, 80), (392, 160), (312, 160)], fill=(205, 226, 252))
    draw.line([(312, 80), (312, 160), (392, 160)], fill=(160, 195, 235), width=4)

    # SI 字样
    font = None
    for name in ("arialbd.ttf", "segoeuib.ttf", "calibrib.ttf"):
        try:
            font = ImageFont.truetype(name, 146)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 146)
    draw.text((254, 238), "SI", font=font, fill=(20, 50, 79), anchor="mm")

    # 列表线条
    line_color = (150, 190, 232)
    draw.rounded_rectangle((160, 330, 348, 344), radius=7, fill=line_color)
    draw.rounded_rectangle((160, 366, 320, 380), radius=7, fill=line_color)
    draw.rounded_rectangle((160, 402, 300, 416), radius=7, fill=line_color)

    # 外边框
    draw.rounded_rectangle(
        (8, 8, SIZE - 8, SIZE - 8), radius=96, outline=(10, 32, 55), width=5
    )

    icon.save(OUT, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(PREVIEW)
    print(f"written: {OUT}")
    print(f"preview: {PREVIEW}")


if __name__ == "__main__":
    main()
