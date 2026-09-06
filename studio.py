"""创作工坊：选题弹药（brief）与草稿包骨架的确定性生成。

真正的高质量文案由 Agent（在 DSH 会话里读风格卡 + 历史 + 联网热点）撰写，
本模块负责把它落地成 drafts/<day>/ 下的帖子包文件，保证可复现、可回溯。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import db
import style as style_mod

REPO_ROOT = Path(__file__).resolve().parent
DRAFTS_DIR = REPO_ROOT / "drafts"

POST_TEMPLATE = """---
day: {day}
title: ""
tags: []
cover_text: ""
status: draft
---

# 正文

（正文留空，由 Agent 按风格卡撰写后回填）
"""


def drafts_dir() -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    return DRAFTS_DIR


def build_brief(conn, *, day: str, lookback_days: int = 30) -> dict:
    """聚合当日日志 + 近期主题榜，产出选题 brief 数据。"""
    today_logs = db.journal_list(conn, day=day, limit=200)
    top_cats = db.journal_topics(conn, days=lookback_days, group="category", limit=8)
    top_tags = db.journal_topics(conn, days=lookback_days, group="tag", limit=15)
    counts = db.stats(conn)
    return {
        "day": day,
        "today_logs": today_logs,
        "top_categories": top_cats,
        "top_tags": top_tags,
        "stats": counts,
    }


def brief_markdown(brief: dict) -> str:
    lines: list[str] = []
    day = brief["day"]
    lines.append(f"# 选题 Brief · {day}")
    lines.append("")
    lines.append(f"历史库共 {brief['stats']['entries']} 条 / {brief['stats']['days']} 天")
    lines.append("")
    lines.append("## 今日日志输入")
    logs = brief["today_logs"]
    if not logs:
        lines.append("（今日暂无日志——先 `cli.py journal add` 记录今天的心情/经历/学习/想法）")
    for r in logs:
        tags = " ".join(f"#{t}" for t in r["tags"]) or "无标签"
        lines.append(f"- [{r['category']}] {r['day']} {tags}\n  {r['text']}")
    lines.append("")
    lines.append("## 近期高频主题（近 30 天聚合，可作选题线索）")
    lines.append("### 分类")
    for c in brief["top_categories"]:
        lines.append(f"- {c['name']} × {c['count']}（最近 {c['last_day']}）")
    lines.append("### 标签")
    for t in brief["top_tags"]:
        lines.append(f"- #{t['name']} × {t['count']}（最近 {t['last_day']}）")
    lines.append("")
    lines.append("## 候选选题（Agent 填充）")
    lines.append("- [ ] 选题 A：")
    lines.append("- [ ] 选题 B：")
    lines.append("- [ ] 选题 C：")
    lines.append("")
    lines.append("## 同领域热点（Agent 用联网检索填充：今天大家在聊什么、爆款标题结构）")
    lines.append("- 热点 1：")
    lines.append("")
    lines.append("## 决定：今日写哪个选题 + 一句话角度")
    lines.append("（确认后新建 post 草稿并撰写正文）")
    return "\n".join(lines)


def new_day(day: str) -> list[Path]:
    """初始化 drafts/<day>/：brief.md + post.md 骨架。返回创建的文件列表。"""
    out_dir = drafts_dir() / day
    out_dir.mkdir(parents=True, exist_ok=True)
    files = [out_dir / "brief.md", out_dir / "post.md"]
    with db.connect() as conn:
        brief = build_brief(conn, day=day)
    files[0].write_text(brief_markdown(brief), encoding="utf-8")
    files[1].write_text(POST_TEMPLATE.format(day=day), encoding="utf-8")
    return files


def save_post(day: str, *, title: str, tags: list[str], cover_text: str, body: str) -> Path:
    """把定稿的今日帖子写入 drafts/<day>/post.md（供人工复核 / P2 发布器读取）。"""
    out_dir = drafts_dir() / day
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "day": day,
        "title": title,
        "tags": tags,
        "cover_text": cover_text,
        "body": body,
    }
    text = (
        "---\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n---\n"
    )
    path = out_dir / "post.md"
    path.write_text(text, encoding="utf-8")
    return path


def today() -> str:
    return date.today().isoformat()
