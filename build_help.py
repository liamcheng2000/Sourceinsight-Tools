"""Build the self-contained help page from the Markdown tutorial.

The generated help.html is bundled into the exe. 使用教程.html is the same
content with a share-friendly name. All images are embedded as data URIs, so
the page works offline and does not depend on the docs folder.
"""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "使用教程.md"
OUTPUTS = (ROOT / "使用教程.html", ROOT / "help.html")

CSS = """
:root {
  --ink: #1f2937;
  --navy: #16324f;
  --accent: #1f6feb;
  --muted: #667085;
  --line: #e3e9f2;
  --bg: #eef2f7;
  --code-bg: #0d1726;
  --code-fg: #d7e3f2;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", system-ui, sans-serif;
  font-size: 16px;
  line-height: 1.8;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

.hero {
  background: linear-gradient(135deg, #10263d 0%, #16324f 48%, #1d4f7d 100%);
  color: #fff;
  padding: 58px 24px 66px;
}
.hero-inner { max-width: 1000px; margin: 0 auto; }
.eyebrow {
  font-size: 12px;
  letter-spacing: 2.4px;
  text-transform: uppercase;
  color: #8fb3d6;
  margin-bottom: 14px;
}
.hero h1 {
  margin: 0 0 12px;
  font-size: 38px;
  line-height: 1.3;
  letter-spacing: 0.5px;
}
.hero p {
  margin: 0 0 18px;
  font-size: 17px;
  color: #c9d9e8;
}
.meta { display: flex; flex-wrap: wrap; gap: 10px; }
.meta span {
  font-size: 13px;
  color: #dbe8f5;
  background: rgba(255, 255, 255, .1);
  border: 1px solid rgba(255, 255, 255, .18);
  border-radius: 999px;
  padding: 4px 12px;
}

main {
  max-width: 1000px;
  margin: -34px auto 46px;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 18px 50px rgba(16, 38, 61, .12);
  padding: 46px 56px 40px;
}

h2 {
  position: relative;
  margin: 48px 0 18px;
  padding: 0 0 10px 15px;
  font-size: 26px;
  line-height: 1.4;
  color: var(--navy);
  border-bottom: 1px solid var(--line);
}
h2::before {
  content: "";
  position: absolute;
  left: 0;
  top: 7px;
  width: 4px;
  height: 22px;
  border-radius: 2px;
  background: var(--accent);
}
h3 {
  margin: 30px 0 10px;
  font-size: 19px;
  color: #24405f;
}
p { margin: 12px 0; }
ul, ol { padding-left: 26px; }
li { margin: 5px 0; }
strong { color: #12263d; }

blockquote {
  margin: 20px 0;
  padding: 14px 18px;
  background: #f2f7ff;
  border-left: 4px solid var(--accent);
  border-radius: 0 10px 10px 0;
  color: #334a63;
}
blockquote p { margin: 0; }

img {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 24px auto 10px;
  border: 1px solid #dfe6ef;
  border-radius: 12px;
  box-shadow: 0 10px 28px rgba(22, 50, 79, .10);
}
em {
  display: block;
  margin: 0 0 26px;
  text-align: center;
  color: var(--muted);
  font-size: 14px;
  font-style: normal;
}

code {
  font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
  font-size: .92em;
  background: #eef2f7;
  color: #0b5cad;
  padding: 2px 6px;
  border-radius: 5px;
}
pre {
  margin: 18px 0 24px;
  padding: 18px 20px;
  background: var(--code-bg);
  color: var(--code-fg);
  border-radius: 12px;
  overflow-x: auto;
  line-height: 1.62;
  font-size: 14px;
}
pre code {
  background: transparent;
  color: inherit;
  padding: 0;
  font-size: inherit;
}

table {
  width: 100%;
  margin: 18px 0 28px;
  border-collapse: collapse;
  font-size: 15px;
}
th, td {
  border: 1px solid var(--line);
  padding: 10px 12px;
  vertical-align: top;
  text-align: left;
}
th { background: #f3f6fa; color: #24405f; font-weight: 600; }
tr:nth-child(even) td { background: #fafcff; }

.toc {
  margin: 24px 0 8px;
  padding: 18px 24px;
  background: #f7f9fc;
  border: 1px solid var(--line);
  border-radius: 12px;
}
.toc-title {
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 700;
  color: var(--navy);
}
.toc > ul { columns: 2; column-gap: 34px; margin: 0; padding-left: 18px; }
.toc ul { list-style: disc; }
.toc ul ul { display: none; }
.toc li { margin: 5px 0; font-size: 14px; break-inside: avoid; }
.toc a { color: #2b5c8f; }

hr {
  border: 0;
  border-top: 1px solid var(--line);
  margin: 40px 0;
}

footer {
  max-width: 1000px;
  margin: 0 auto 60px;
  padding: 0 24px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.top {
  position: fixed;
  right: 26px;
  bottom: 26px;
  width: 42px;
  height: 42px;
  line-height: 42px;
  text-align: center;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  box-shadow: 0 8px 20px rgba(31, 111, 235, .35);
  font-size: 18px;
}
.top:hover { text-decoration: none; background: #2f81f7; }

@media (max-width: 760px) {
  .hero { padding: 40px 20px 54px; }
  .hero h1 { font-size: 28px; }
  main { margin: -26px 12px 34px; padding: 28px 20px 24px; border-radius: 14px; }
  h2 { font-size: 22px; margin-top: 38px; }
  .toc > ul { columns: 1; }
  table { display: block; overflow-x: auto; }
}

@media print {
  body { background: #fff; }
  .hero { background: #16324f; print-color-adjust: exact; }
  main { box-shadow: none; margin: 0 auto; padding: 24px 0; }
  .top { display: none; }
  img { box-shadow: none; break-inside: avoid; }
  h2 { break-after: avoid; }
}
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Source Insight 文件清单生成器 · 使用教程</title>
<style>
{css}
</style>
</head>
<body id="top">
<header class="hero">
  <div class="hero-inner">
    <div class="eyebrow">Source Insight File List Generator</div>
    <h1>使用教程</h1>
    <p>从 Xilinx / Vitis 构建产物生成 Source Insight 工程文件清单</p>
    <div class="meta">
      <span>v{version}</span>
      <span>Windows 10 / 11</span>
      <span>单文件 exe · 无需 Python</span>
      <span>点击“帮助 (F1)”随时打开</span>
    </div>
  </div>
</header>
<main>
{body}
</main>
<footer>
  Source Insight 文件清单生成器 v{version} · 本页为离线教程，所有图片已内嵌
</footer>
<a class="top" href="#top" title="回到顶部">↑</a>
</body>
</html>
"""


def embed_images(html: str) -> str:
    pattern = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")')

    def replace(match: re.Match[str]) -> str:
        src = match.group(2)
        if src.startswith("data:"):
            return match.group(0)
        image_path = (ROOT / src).resolve()
        if not image_path.is_file():
            raise SystemExit(f"missing tutorial image: {src}")
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f'{match.group(1)}data:image/png;base64,{encoded}{match.group(3)}'

    return pattern.sub(replace, html)


def build() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"missing tutorial source: {SOURCE}")

    text = SOURCE.read_text(encoding="utf-8")
    md = markdown.Markdown(
        extensions=["extra", "tables", "fenced_code", "toc", "sane_lists"],
        extension_configs={"toc": {"toc_depth": "2-3"}},
    )
    body = md.convert(text)

    # The Markdown keeps its H1 for GitHub; the HTML hero already has one.
    body = re.sub(r"<h1\b[^>]*>.*?</h1>", "", body, count=1, flags=re.DOTALL)
    toc_html = md.toc.replace(
        '<div class="toc">',
        '<div class="toc"><div class="toc-title">目录</div>',
        1,
    )
    body = body.replace("<!-- TOC -->", toc_html)
    body = embed_images(body)

    version = "1.0.0"
    html = TEMPLATE.format(css=CSS, body=body, version=version)

    for output in OUTPUTS:
        output.write_text(html, encoding="utf-8", newline="\n")
        print(f"written {output.name} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    try:
        build()
    except SystemExit as exc:
        print(exc)
        sys.exit(1)
