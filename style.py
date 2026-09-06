"""风格卡（人设与文风配置）加载 + 日志自动分类的轻量关键词规则。

风格卡是「人设 + 文风 + 话题习惯 + 封面规范」的唯一事实来源，存放在
config/style.json，可随时手改。文案生成时由 Agent 读取本卡执行。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

STYLE_PATH = Path(__file__).resolve().parent / "config" / "style.json"

# 自动分类规则，两段式：
# 1) 意图词（想写/选题/灵感…）优先——说"想写什么"通常是 想法/内容素材；
# 2) 内容词（学到/焦虑…）再匹配——描述已发生的输入/状态。
# 都命中不了归「经历」。规则永远只是建议，Agent 可修正。
INTENT_KEYWORDS: dict[str, list[str]] = {
    "想法": ["灵感", "计划", "创意", "我想", "观点", "我觉得应该", "如果", "反思", "想法"],
    "内容素材": ["想写一篇", "想写", "素材", "案例", "参考", "金句", "选题", "截图"],
}
CONTENT_KEYWORDS: dict[str, list[str]] = {
    "学习": ["学到", "学会了", "课程", "读书", "书里", "论文", "知识", "复盘", "练习", "教程", "看完", "笔记"],
    "心情": ["开心", "难过", "焦虑", "累", "感动", "生气", "孤独", "兴奋", "沮丧", "平静", "压力"],
}
DEFAULT_CATEGORY = "经历"
FALLBACK_STYLE: dict = {"schema": 1, "categories": ["心情", "经历", "学习", "想法", "内容素材"], "persona": {}, "文风": {}, "话题习惯": {}, "封面规范": {}, "发布习惯": {}}


def load(path: Path = STYLE_PATH) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return dict(FALLBACK_STYLE)
    return dict(FALLBACK_STYLE)


def categories(style: dict | None = None) -> list[str]:
    s = style if style is not None else load()
    return list(s.get("categories") or FALLBACK_STYLE["categories"])


def auto_category(text: str) -> str:
    """两段式关键词猜测：先意图词，后内容词，都不中归「经历」。"""
    for table in (INTENT_KEYWORDS, CONTENT_KEYWORDS):
        for cat, words in table.items():
            for w in words:
                if w in text:
                    return cat
    return DEFAULT_CATEGORY


def normalize_day(day: str) -> str:
    """接受 YYYY-MM-DD 或 YYYYMMDD，统一成 ISO 格式，并校验是真实日历日期。"""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", day)
    if m:
        cand = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", day)
        if not m:
            raise ValueError(f"日期格式应为 YYYY-MM-DD 或 YYYYMMDD，收到：{day!r}")
        cand = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    from datetime import date  # noqa: PLC0415

    try:
        date.fromisoformat(cand)
    except ValueError as e:
        raise ValueError(f"不是有效日期：{cand!r}") from e
    return cand
