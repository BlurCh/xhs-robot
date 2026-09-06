"""素材输入通道：读取 inbox 文件夹里的日记文件并入历史库。

命名约定：文件名以日期开头即可，例如
  2026-09-06-晚上.md / 20260906.txt / 2026-09-06-散步偶感.md
可选的文件内指令（会被剥离、不入正文）：
  第一行前几行：`分类: 心情`（心情/经历/学习/想法/内容素材，缺省自动猜）
  以及        `标签: 焦虑, 备孕`（逗号分隔）
其余内容全部作为正文入库；处理完的文件移到 inbox/archive/ 防重复。

对话框直述：直接发文字给我，我用 `journal add` 走同一条历史库。
"""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

import db
import style as style_mod

REPO = Path(__file__).resolve().parent
INBOX = REPO / "inbox"

_DATE_RE = re.compile(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})")


def _parse(text: str, fallback_day: str):
    """拆出 分类/标签 指令行 + 正文。"""
    cat, tags, kept = None, [], []
    for line in text.splitlines():
        m = re.match(r"^\s*(分类)\s*[:：]\s*(.+?)\s*$", line)
        if m:
            cat = m.group(2).strip()
            continue
        m = re.match(r"^\s*(标签)\s*[:：]\s*(.+?)\s*$", line)
        if m:
            tags = [t.strip() for t in m.group(2).split(",") if t.strip()]
            continue
        kept.append(line)
    if not cat:
        cat = style_mod.auto_category(" ".join(kept))
    return cat, tags, "\n".join(kept).strip() or text.strip()


def _file_day(name: str, mtime_day: str) -> str:
    m = _DATE_RE.search(name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return mtime_day


def ingest_dir(conn, folder: Path | None = None, archive: Path | None = None) -> dict:
    """读取 folder（默认 inbox）内 *.md/*.txt 入库，处理后移入 archive。"""
    folder = Path(folder) if folder else INBOX
    folder = folder.resolve()
    archive = (Path(archive) if archive else folder / "archive").resolve()
    archive.mkdir(parents=True, exist_ok=True)
    exts = {".md", ".txt"}
    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in exts and not p.name.startswith(".")
    )
    days: set[str] = set()
    n = 0
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            f.unlink(missing_ok=True)
            continue
        mtime_day = date.fromtimestamp(f.stat().st_mtime).isoformat()
        day = _file_day(f.name, mtime_day)
        cat, tags, body = _parse(text, day)
        db.journal_add(conn, day=day, text=body, category=cat, tags=tags, source="inbox")
        days.add(day)
        n += 1
        dst = archive / f.name
        i = 1
        while dst.exists():
            dst = archive / f"{f.stem}-{i}{f.suffix}"
            i += 1
        shutil.move(str(f), str(dst))
    return {"files": n, "days": sorted(days), "archive": str(archive)}
