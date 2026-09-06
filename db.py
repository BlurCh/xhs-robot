"""SQLite 存储层。

Schema v1: journal（日志历史）。
Schema v2: + posts（已发布笔记元数据）、metrics（创作者中心每日数据快照）。
Schema v3: + account_daily（账号级每日趋势，来自数据中心 account/base）。
迁移方式：升 PRAGMA user_version 并追加 DDL。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

SCHEMA_VERSION = 3

DDL_V1 = """
CREATE TABLE IF NOT EXISTS journal (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  day        TEXT NOT NULL,
  category   TEXT NOT NULL DEFAULT '经历',
  tags       TEXT NOT NULL DEFAULT '[]',
  text       TEXT NOT NULL,
  mood       TEXT,
  source     TEXT NOT NULL DEFAULT 'cli',
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_journal_day ON journal(day);
CREATE INDEX IF NOT EXISTS idx_journal_category ON journal(category);
"""

DDL_V2 = """
CREATE TABLE IF NOT EXISTS posts (
  note_id      TEXT PRIMARY KEY,
  day          TEXT NOT NULL,
  title        TEXT NOT NULL,
  tags         TEXT NOT NULL DEFAULT '[]',
  cover_text   TEXT NOT NULL DEFAULT '',
  body         TEXT NOT NULL DEFAULT '',
  status       TEXT NOT NULL DEFAULT 'published',
  published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_day ON posts(day);

CREATE TABLE IF NOT EXISTS metrics (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  note_id        TEXT NOT NULL REFERENCES posts(note_id),
  day            TEXT NOT NULL,
  impressions    INTEGER NOT NULL DEFAULT 0,
  views          INTEGER NOT NULL DEFAULT 0,
  likes          INTEGER NOT NULL DEFAULT 0,
  collects       INTEGER NOT NULL DEFAULT 0,
  comments       INTEGER NOT NULL DEFAULT 0,
  shares         INTEGER NOT NULL DEFAULT 0,
  new_followers  INTEGER NOT NULL DEFAULT 0,
  extra          TEXT NOT NULL DEFAULT '{}',
  UNIQUE(note_id, day)
);
"""

DDL_V3 = """
CREATE TABLE IF NOT EXISTS account_daily (
  day       TEXT PRIMARY KEY,
  views     INTEGER NOT NULL DEFAULT 0,
  impl      INTEGER NOT NULL DEFAULT 0,
  likes     INTEGER NOT NULL DEFAULT 0,
  collects  INTEGER NOT NULL DEFAULT 0,
  comments  INTEGER NOT NULL DEFAULT 0,
  shares    INTEGER NOT NULL DEFAULT 0,
  fans_gain INTEGER NOT NULL DEFAULT 0
);
"""


def default_db_path() -> Path:
    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "xhs.db"


@contextmanager
def connect(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path) if db_path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        conn.executescript(DDL_V1)
        version = 1
    if version < 2:
        conn.executescript(DDL_V2)
        version = 2
    if version < 3:
        conn.executescript(DDL_V3)
        version = 3
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


# ---------------- journal ----------------

def journal_add(
    conn: sqlite3.Connection,
    *,
    day: str,
    text: str,
    category: str,
    tags: list[str],
    mood: Optional[str] = None,
    source: str = "cli",
) -> int:
    cur = conn.execute(
        "INSERT INTO journal(day, category, tags, text, mood, source) VALUES(?,?,?,?,?,?)",
        (day, category, _json(tags), text.strip(), mood, source),
    )
    return int(cur.lastrowid)


def journal_list(
    conn: sqlite3.Connection,
    *,
    day: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM journal WHERE 1=1"
    args: list[Any] = []
    if day:
        sql += " AND day = ?"
        args.append(day)
    if category:
        sql += " AND category = ?"
        args.append(category)
    if tag:
        sql += " AND EXISTS (SELECT 1 FROM json_each(journal.tags) WHERE json_each.value = ?)"
        args.append(tag)
    sql += " ORDER BY day DESC, id DESC LIMIT ?"
    args.append(limit)
    return [_row(r) for r in conn.execute(sql, args).fetchall()]


def journal_search(conn: sqlite3.Connection, keyword: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM journal WHERE text LIKE ? OR category LIKE ? ORDER BY day DESC, id DESC LIMIT ?",
        (f"%{keyword}%", f"%{keyword}%", limit),
    ).fetchall()
    return [_row(r) for r in rows]


def journal_topics(
    conn: sqlite3.Connection,
    *,
    days: int = 30,
    group: str = "category",
    limit: int = 15,
) -> list[dict[str, Any]]:
    """按 category 或 tag 聚合近 N 天日志：次数 + 最近一次日期，供选题参考。"""
    since = _day_before(days)
    if group == "tag":
        sql = """
          SELECT json_each.value AS name, COUNT(*) AS count, MAX(day) AS last_day
          FROM journal, json_each(journal.tags)
          WHERE journal.day >= ?
          GROUP BY json_each.value ORDER BY count DESC, last_day DESC LIMIT ?
        """
    else:
        sql = """
          SELECT category AS name, COUNT(*) AS count, MAX(day) AS last_day
          FROM journal WHERE day >= ?
          GROUP BY category ORDER BY count DESC, last_day DESC LIMIT ?
        """
    rows = conn.execute(sql, (since, limit)).fetchall()
    return [{"name": r["name"], "count": r["count"], "last_day": r["last_day"]} for r in rows]


def stats(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute("SELECT COUNT(*) AS n, COUNT(DISTINCT day) AS d FROM journal").fetchone()
    return {"entries": row["n"], "days": row["d"]}


# ---------------- posts / metrics（P2 数据回流） ----------------

_METRIC_FIELDS = ("impressions", "views", "likes", "collects", "comments", "shares", "new_followers")


def posts_upsert(
    conn: sqlite3.Connection,
    *,
    note_id: str,
    day: str,
    title: str,
    tags: Optional[list[str]] = None,
    cover_text: str = "",
    body: str = "",
    status: str = "published",
    published_at: Optional[str] = None,
) -> None:
    conn.execute(
        """INSERT INTO posts(note_id, day, title, tags, cover_text, body, status, published_at)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(note_id) DO UPDATE SET
             day=excluded.day, title=excluded.title, tags=excluded.tags,
             cover_text=excluded.cover_text, body=excluded.body, status=excluded.status,
             published_at=excluded.published_at""",
        (note_id, day, title, _json(tags or []), cover_text, body, status, published_at),
    )


def posts_list(conn: sqlite3.Connection, status: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
    sql = "SELECT * FROM posts"
    args: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        args.append(status)
    sql += " ORDER BY day DESC, note_id DESC LIMIT ?"
    args.append(limit)
    return [_row(r) for r in conn.execute(sql, args).fetchall()]


def metrics_upsert(
    conn: sqlite3.Connection,
    *,
    note_id: str,
    day: str,
    impressions: int = 0,
    views: int = 0,
    likes: int = 0,
    collects: int = 0,
    comments: int = 0,
    shares: int = 0,
    new_followers: int = 0,
    extra: Optional[dict] = None,
) -> None:
    conn.execute(
        """INSERT INTO metrics(note_id, day, impressions, views, likes, collects, comments, shares, new_followers, extra)
           VALUES(?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(note_id, day) DO UPDATE SET
             impressions=excluded.impressions, views=excluded.views, likes=excluded.likes,
             collects=excluded.collects, comments=excluded.comments, shares=excluded.shares,
             new_followers=excluded.new_followers, extra=excluded.extra""",
        (note_id, day, impressions, views, likes, collects, comments, shares, new_followers, _json(extra or {})),
    )


def metrics_history(conn: sqlite3.Connection, note_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM metrics WHERE note_id = ? ORDER BY day ASC", (note_id,)
    ).fetchall()
    return [_row(r) for r in rows]


def posts_with_metrics(
    conn: sqlite3.Connection,
    *,
    since_day: Optional[str] = None,
    require_snapshots: int = 1,
) -> list[dict[str, Any]]:
    """每篇已发布笔记 + 最近一次数据快照；可选要求至少 N 个快照日。"""
    sql = """
      SELECT p.note_id, p.day AS post_day, p.title, p.status,
             COUNT(m.id) AS snapshots,
             (SELECT mm.day FROM metrics mm WHERE mm.note_id = p.note_id ORDER BY mm.day DESC LIMIT 1) AS last_day,
             (SELECT mm.impressions FROM metrics mm WHERE mm.note_id = p.note_id ORDER BY mm.day DESC LIMIT 1) AS impressions,
             (SELECT mm.views      FROM metrics mm WHERE mm.note_id = p.note_id ORDER BY mm.day DESC LIMIT 1) AS views,
             (SELECT mm.likes      FROM metrics mm WHERE mm.note_id = p.note_id ORDER BY mm.day DESC LIMIT 1) AS likes,
             (SELECT mm.collects   FROM metrics mm WHERE mm.note_id = p.note_id ORDER BY mm.day DESC LIMIT 1) AS collects,
             (SELECT mm.comments   FROM metrics mm WHERE mm.note_id = p.note_id ORDER BY mm.day DESC LIMIT 1) AS comments,
             (SELECT mm.shares     FROM metrics mm WHERE mm.note_id = p.note_id ORDER BY mm.day DESC LIMIT 1) AS shares,
             (SELECT mm.new_followers FROM metrics mm WHERE mm.note_id = p.note_id ORDER BY mm.day DESC LIMIT 1) AS new_followers
      FROM posts p LEFT JOIN metrics m ON m.note_id = p.note_id
      WHERE p.status = 'published'
      GROUP BY p.note_id
      HAVING COUNT(m.id) >= ?
      ORDER BY last_day DESC
    """
    args: list[Any] = [require_snapshots]
    if since_day:
        sql = sql.replace("WHERE p.status = 'published'", "WHERE p.status = 'published' AND p.day >= ?")
        args.insert(0, since_day)
    return [_row(r) for r in conn.execute(sql, args).fetchall()]


# ---------------- account_daily（v3，账号级每日趋势） ----------------

def account_daily_upsert(
    conn: sqlite3.Connection,
    *,
    day: str,
    views: int = 0,
    impl: int = 0,
    likes: int = 0,
    collects: int = 0,
    comments: int = 0,
    shares: int = 0,
    fans_gain: int = 0,
) -> None:
    conn.execute(
        """INSERT INTO account_daily(day, views, impl, likes, collects, comments, shares, fans_gain)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(day) DO UPDATE SET
             views=excluded.views, impl=excluded.impl, likes=excluded.likes,
             collects=excluded.collects, comments=excluded.comments, shares=excluded.shares,
             fans_gain=excluded.fans_gain""",
        (day, views, impl, likes, collects, comments, shares, fans_gain),
    )


def account_daily_list(conn: sqlite3.Connection, *, days: int = 30) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM account_daily ORDER BY day DESC LIMIT ?", (days,)
    ).fetchall()
    return [_row(r) for r in rows]


# ---------------- helpers ----------------

def _json(v: list[str]) -> str:
    import json

    return json.dumps(v, ensure_ascii=False)


def _row(r: sqlite3.Row) -> dict[str, Any]:
    import json

    d = dict(r)
    if "tags" in d:
        try:
            d["tags"] = json.loads(d["tags"] or "[]")
        except json.JSONDecodeError:
            d["tags"] = []
    return d


def _day_before(days: int) -> str:
    from datetime import date, timedelta

    return (date.today() - timedelta(days=days)).isoformat()
