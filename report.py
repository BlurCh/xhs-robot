"""数据回流：创作者中心导出导入 + 趋势/归因报表（P2，纯本地可验证）。

creator 导出 CSV 的列名因平台改版会变，这里用「同义词匹配」尽量兼容；
拿不准时把文件发来，我按实际表头调整映射即可。
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import db

_INT_RE = re.compile(r"\d+")
_HEX24 = re.compile(r"[0-9a-fA-F]{24}")


def _num(cell: Any) -> int:
    if cell is None:
        return 0
    m = _INT_RE.search(str(cell).replace(",", ""))
    return int(m.group()) if m else 0


def _find(header_low: list[str], keys: list[str]) -> int | None:
    for i, h in enumerate(header_low):
        for k in keys:
            if k in h:
                return i
    return None


def _note_id_from_url(url: str, fallback: str) -> str:
    m = _HEX24.search(url or "")
    if m:
        return m.group()
    return "sync-" + hashlib.sha1(fallback.encode("utf-8")).hexdigest()[:16]


def import_creator_csv(conn, path: str | Path, *, default_day: str | None = None) -> dict[str, Any]:
    """导入创作者中心导出的 CSV（每行=一篇笔记的某个统计日快照）。"""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        return {"rows": 0, "posts": 0, "note": "空文件或无表头"}
    header_low = [h.lower() for h in rows[0].keys()]

    idx = {
        "note": _find(header_low, ["笔记id", "noteid", "note_id", "作品id"]),
        "url": _find(header_low, ["链接", "url", "xhslink", "笔记链接"]),
        "title": _find(header_low, ["标题", "title"]),
        "day": _find(header_low, ["统计日期", "日期", "date", "时间"]),
        "impressions": _find(header_low, ["曝光"]),
        "views": _find(header_low, ["观看", "阅读", "播放"]),
        "likes": _find(header_low, ["获赞", "点赞", "赞"]),
        "collects": _find(header_low, ["收藏"]),
        "comments": _find(header_low, ["评论"]),
        "shares": _find(header_low, ["分享", "转发"]),
        "followers": _find(header_low, ["涨粉", "新增关注", "粉丝"]),
    }
    keys = list(rows[0].keys())
    seen: set[str] = set()
    n = 0
    for r in rows:
        title = (r[keys[idx["title"]]] if idx["title"] is not None else "").strip() or "未命名"
        day = default_day
        if idx["day"] is not None:
            raw = (r[keys[idx["day"]]] or "").strip()
            m = re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", raw)
            if m:
                day = m.group().replace("/", "-")
        day = day or "1970-01-01"

        if idx["note"] is not None:
            note_id = (r[keys[idx["note"]]] or "").strip()
        elif idx["url"] is not None:
            note_id = _note_id_from_url(r[keys[idx["url"]]], f"{title}|{day}")
        else:
            note_id = _note_id_from_url("", f"{title}|{day}|{n}")
        if not note_id:
            note_id = _note_id_from_url("", f"{title}|{day}|{n}")
        seen.add(note_id)
        db.posts_upsert(conn, note_id=note_id, day=day, title=title)
        db.metrics_upsert(
            conn,
            note_id=note_id,
            day=day,
            impressions=_num(r[keys[idx["impressions"]]]) if idx["impressions"] is not None else 0,
            views=_num(r[keys[idx["views"]]]) if idx["views"] is not None else 0,
            likes=_num(r[keys[idx["likes"]]]) if idx["likes"] is not None else 0,
            collects=_num(r[keys[idx["collects"]]]) if idx["collects"] is not None else 0,
            comments=_num(r[keys[idx["comments"]]]) if idx["comments"] is not None else 0,
            shares=_num(r[keys[idx["shares"]]]) if idx["shares"] is not None else 0,
            new_followers=_num(r[keys[idx["followers"]]]) if idx["followers"] is not None else 0,
        )
        n += 1
    return {"rows": n, "posts": len(seen)}


def import_pull_json(conn, path: str | Path, *, snapshot_day: str | None = None) -> dict[str, Any]:
    """导入 live pull 抓到的 posted 列表 JSON（network-*.json 捕获格式或裸响应体）。

    映射字段：id/note_id、display_title/title、likes/like_count、collected_count/collect_count、
    comments_count/comment_count、shared_count/share_count、view_count、visible_time（发布时间）。
    发布时间取 visible_time（epoch 秒）；快照日默认今天。返回 {notes, metrics} 计数。
    """
    from datetime import date, datetime, timedelta, timezone  # noqa: PLC0415

    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, dict) and "body" in data and isinstance(data["body"], str):
        data = json.loads(data["body"])
    notes = (data.get("data") or {}).get("notes") or []
    if not notes and isinstance(data.get("data"), list):
        notes = data["data"]
    today = snapshot_day or date.today().isoformat()
    seen_posts: set[str] = set()
    metrics_rows = 0
    for n in notes:
        if not isinstance(n, dict):
            continue
        note_id = str(n.get("id") or n.get("note_id") or "").strip()
        if not note_id:
            continue
        title = str(n.get("display_title") or n.get("title") or "未命名").strip()
        day = today
        vt = _num(n.get("visible_time"))
        if vt:
            day = datetime.fromtimestamp(vt, tz=timezone.utc).date().isoformat()
        db.posts_upsert(conn, note_id=note_id, day=day, title=title,
                        status="published", published_at=day)
        seen_posts.add(note_id)
        db.metrics_upsert(
            conn,
            note_id=note_id,
            day=today,
            impressions=0,
            views=_num(n.get("view_count")),
            likes=_num(n.get("likes") or n.get("like_count")),
            collects=_num(n.get("collected_count") or n.get("collect_count")),
            comments=_num(n.get("comments_count") or n.get("comment_count")),
            shares=_num(n.get("shared_count") or n.get("share_count")),
            new_followers=0,
            extra={"source": "live_pull"},
        )
        metrics_rows += 1
    return {"notes": len(seen_posts), "metrics": metrics_rows}


def report_markdown(conn, *, top: int = 5) -> str:
    """趋势 + 单篇表现 + 文案归因线索。归因解读留给 Agent/用户。"""
    posts = db.posts_with_metrics(conn, require_snapshots=1)
    L: list[str] = []
    if not posts:
        return "（还没有带数据的已发布笔记。用 `stats import` 导入创作者中心导出，或 `posts add` 登记发布。）"
    total = {k: sum(int(p.get(k) or 0) for p in posts) for k in ("impressions", "views", "likes", "collects", "comments", "shares", "new_followers")}

    def fmt(r: dict) -> str:
        t = (r.get("title") or "")[:22]
        return (
            f"- **{t}**（发 {r['post_day']}，{r['snapshots']} 次快照）\n"
            f"  曝光 {r['impressions']}｜观看 {r['views']}｜赞 {r['likes']}｜藏 {r['collects']}"
            f"｜评 {r['comments']}｜转 {r['shares']}｜涨粉 {r['new_followers']}"
        )

    L.append("# 小红书数据周报（本地生成，人工复核）")
    L.append("")
    L.append(f"已带数据的笔记 {len(posts)} 篇。合计（最新快照）：")
    L.append(
        f"- 曝光 {total['impressions']}｜观看 {total['views']}｜赞 {total['likes']}｜藏 {total['collects']}"
        f"｜评 {total['comments']}｜转 {total['shares']}｜涨粉 {total['new_followers']}"
    )
    L.append("")

    def by(key: str, reverse: bool = True, n: int = top) -> list[dict]:
        return sorted(posts, key=lambda p: int(p.get(key) or 0), reverse=reverse)[:n]

    L.append(f"## 曝光 TOP{top}（流量潜力）")
    for p in by("impressions"):
        L.append(fmt(p))
    L.append("")
    L.append(f"## 赞藏 TOP{top}（内容价值：藏/赞高=干货型）")
    for p in sorted(posts, key=lambda r: int(r.get("collects") or 0) + int(r.get("likes") or 0), reverse=True)[:top]:
        L.append(fmt(p))
    L.append("")

    L.append("## 单篇明细")
    for p in sorted(posts, key=lambda r: r["post_day"], reverse=True):
        L.append(fmt(p))
    L.append("")

    L.append("## 效果归因线索（人工判断用）")
    good = sorted(
        posts,
        key=lambda r: (int(r.get("likes") or 0) + int(r.get("collects") or 0)) / max(1, int(r.get("views") or 0)),
        reverse=True,
    )[:top]
    L.append("互动率（赞+藏）/观看 最高：")
    for p in good:
        v = int(p.get("views") or 0)
        rate = (int(p.get("likes") or 0) + int(p.get("collects") or 0)) / max(1, v)
        t = (p.get("title") or "")[:22]
        L.append(f"- {t}：{rate:.1%}（观看 {v}）")
    L.append("")
    L.append("对照上面标题/话题，找共同点；把「什么标题结构/话题」反馈给创作工坊。")
    return "\n".join(L)
