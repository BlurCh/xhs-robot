"""P3 封面模板引擎：把 cover_text/标题排版成统一风格的 3:4 封面图。

零外部依赖（Pillow 本地渲染），风格参数取自 config/style.json「封面规范」：
色板/字体/留白都由它控制，保证每期封面一致。漫画/插画类生图仍需图像 API（P3 后半）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import style as style_mod

FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),  # 微软雅黑 Bold
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
]
DEFAULT_SIZE = (900, 1200)  # 3:4，小红书竖图

_re_frontmatter = re.compile(r"^---\n(.*?)\n---\n", re.S)


def load_post_frontmatter(path: str | Path) -> dict:
    """读 drafts/<day>/post.md 顶部的 JSON frontmatter（studio.save_post 的格式）。"""
    text = Path(path).read_text(encoding="utf-8")
    m = _re_frontmatter.match(text)
    if not m:
        raise ValueError(f"不是帖子包格式（缺 JSON frontmatter）：{path}")
    return json.loads(m.group(1))


def _pick_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for cand in FONT_CANDIDATES:
        if cand.exists():
            try:
                return ImageFont.truetype(str(cand), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(text: str, font, max_width: int, draw: ImageDraw.ImageDraw, max_lines: int = 4) -> list[str]:
    """按像素宽度换行成 ≤max_lines 行（放不下时末尾截断加 …）。"""
    lines: list[str] = []
    for raw in text.split("\n"):
        cur = ""
        for ch in raw:
            if draw.textlength(cur + ch, font=font) <= max_width:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def make_cover(text: str, out: str | Path, *, palette: list[str] | None = None,
               brand: str = "· 记录与成长 ·", size: tuple[int, int] = DEFAULT_SIZE) -> Path:
    """渲染封面：白底 + 品牌色强调条 + 大标题。字体先按宽度换行，超高则自动缩号。"""
    pal = palette or ["#FFFFFF", "#1F2937", "#F97316"]
    bg, ink, accent = pal[0], pal[1], pal[2]
    w, h = size
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)
    margin = int(w * 0.08)
    max_width = w - 2 * margin

    font = _pick_font(110)
    lines = _wrap(text, font, max_width, draw)
    line_h = int(font.size * 1.25)
    while line_h * len(lines) > h - 2 * margin and font.size > 48:
        font = _pick_font(font.size - 10)
        lines = _wrap(text, font, max_width, draw)
        line_h = int(font.size * 1.25)

    block_h = line_h * len(lines)
    x = margin
    y = (h - block_h) // 2 - 10

    # 左侧品牌色强调条
    draw.rectangle([x - 12, y - 10, x - 6, y + block_h + 10], fill=accent)
    for ln in lines:
        draw.text((x, y), ln, font=font, fill=ink)
        y += line_h

    small = _pick_font(30)
    draw.text((x, h - 90), brand, font=small, fill=accent)

    out_p = Path(out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_p, format="PNG")
    return out_p


def render_cover_for_day(day: str, *, repo_root: Path | None = None) -> Path:
    """根据 drafts/<day>/post.md（cover_text 或 title）生成 drafts/<day>/cover.png。"""
    root = repo_root or Path(__file__).resolve().parent
    post_md = root / "drafts" / day / "post.md"
    fm = load_post_frontmatter(post_md)
    text = (fm.get("cover_text") or fm.get("title") or "").strip()
    if not text:
        raise ValueError(f"post.md 缺 cover_text 与 title（{post_md}）")
    style_cfg = style_mod.load(root / "config" / "style.json")
    cover = style_cfg.get("封面规范", {})
    pal = cover.get("色板") or ["#FFFFFF", "#1F2937", "#F97316"]
    brand = cover.get("品牌文字") or "· 记录与成长 ·"
    return make_cover(text, root / "drafts" / day / "cover.png", palette=pal, brand=brand)
