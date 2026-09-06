"""小红书创作机器人 · 命令行入口（第一期：日志中心 + 选题/草稿骨架）。

用法示例（Windows PowerShell，建议先 chcp 65001 或设 PYTHONIOENCODING=utf-8）：
  python C:\\Harness_Projects\\xhs-robot\\cli.py journal add --category 学习 --tags 读书,复盘 "今天读完《xxx》，学到..."
  python C:\\Harness_Projects\\xhs-robot\\cli.py journal add --auto "今天心情有点焦虑，因为..."
  python C:\\Harness_Projects\\xhs-robot\\cli.py journal today
  python C:\\Harness_Projects\\xhs-robot\\cli.py journal list --days 7
  python C:\\Harness_Projects\\xhs-robot\\cli.py journal search 焦虑
  python C:\\Harness_Projects\\xhs-robot\\cli.py journal topics --days 30 --group tag
  python C:\\Harness_Projects\\xhs-robot\\cli.py studio new --day 2026-06-01
  python C:\\Harness_Projects\\xhs-robot\\cli.py style show
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import db
import report
import studio
import style as style_mod


def _c(args: argparse.Namespace):
    return db.connect(db_path=Path(args.db) if args.db else None)


def _fmt_row(r: dict) -> str:
    tags = " ".join(f"#{t}" for t in r.get("tags") or [])
    mood = f"（{r['mood']}）" if r.get("mood") else ""
    return f"[{r['id']}] {r['day']} {r['category']}{mood} {tags}\n    {r['text']}"


def _print_rows(rows: list[dict]) -> None:
    if not rows:
        print("（无记录）")
        return
    for r in rows:
        print(_fmt_row(r))


# ---------------- journal ----------------

def cmd_journal_add(args) -> None:
    day = style_mod.normalize_day(args.day)
    if args.text:
        text = " ".join(args.text)
    else:
        text = sys.stdin.read().strip()
    if not text:
        print("错误：正文为空。用参数传文字或经 stdin 输入。", file=sys.stderr)
        sys.exit(2)
    cat = args.category
    if cat == "auto":
        cat = style_mod.auto_category(text)
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    with _c(args) as conn:
        rid = db.journal_add(conn, day=day, text=text, category=cat, tags=tags, mood=args.mood)
    print(f"已记录 #{rid}  [{cat}] {day}  {tags or ''}".rstrip())


def cmd_journal_list(args) -> None:
    with _c(args) as conn:
        rows = db.journal_list(conn, day=args.day, category=args.category, tag=args.tag, limit=args.limit)
    _print_rows(rows)


def cmd_journal_today(args) -> None:
    with _c(args) as conn:
        rows = db.journal_list(conn, day=args.day, limit=200)
    _print_rows(rows)


def cmd_journal_search(args) -> None:
    with _c(args) as conn:
        rows = db.journal_search(conn, args.keyword)
    _print_rows(rows)


def cmd_journal_topics(args) -> None:
    with _c(args) as conn:
        rows = db.journal_topics(conn, days=args.days, group=args.group, limit=args.limit)
    if not rows:
        print("（该时段无记录，先积累一些日志吧）")
        return
    width = max(len(r["name"]) for r in rows)
    for r in rows:
        print(f"{r['name']:<{width}}  ×{r['count']:<3}  最近 {r['last_day']}")


# ---------------- studio ----------------

def cmd_studio_new(args) -> None:
    day = style_mod.normalize_day(args.day)
    files = studio.new_day(day)
    for f in files:
        print(f"已生成 {f}")
    print("brief.md = 选题弹药；post.md = 帖子骨架（title/tags/cover_text 待填）")


def cmd_studio_save(args) -> None:
    """把定稿写入 drafts/<day>/post.md（JSON frontmatter 格式，P2 发布器可读）。"""
    day = style_mod.normalize_day(args.day)
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    else:
        body = sys.stdin.read().strip()
    if not args.title or not body.strip():
        print("错误：--title 与正文都不能为空。", file=sys.stderr)
        sys.exit(2)
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    path = studio.save_post(day, title=args.title, tags=tags, cover_text=args.cover_text, body=body.strip())
    print(f"已保存帖子包 {path}")


def cmd_style_show(_args) -> None:
    print(json.dumps(style_mod.load(), ensure_ascii=False, indent=2))


# ---------------- posts / stats（P2 数据回流） ----------------

def cmd_posts_list(args) -> None:
    with _c(args) as conn:
        rows = db.posts_list(conn, status=args.status, limit=args.limit)
    if not rows:
        print("（还没有登记过发布的笔记）")
        return
    for r in rows:
        tags = " ".join(f"#{t}" for t in r["tags"]) or ""
        print(f"{r['note_id']}  {r['day']}  {r['title'][:30]}  {tags}".rstrip())


def cmd_posts_add(args) -> None:
    note_id = args.note_id
    if not note_id:
        print("错误：--note-id 必填（创作者中心笔记 ID，或你自定义的唯一标识）。", file=sys.stderr)
        sys.exit(2)
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    with _c(args) as conn:
        db.posts_upsert(conn, note_id=note_id, day=style_mod.normalize_day(args.day), title=args.title,
                        tags=tags, cover_text=args.cover_text, body=args.body or "", status=args.status)
    print(f"已登记笔记 {note_id}（{args.status}）")


def cmd_stats_import(args) -> None:
    with _c(args) as conn:
        summary = report.import_creator_csv(conn, args.file, default_day=args.day)
    print(f"导入完成：{summary['rows']} 行 / {summary['posts']} 篇笔记")


def cmd_stats_pull_import(args) -> None:
    with _c(args) as conn:
        summary = report.import_pull_json(conn, args.file, snapshot_day=args.day)
    print(f"导入完成：{summary['notes']} 篇笔记 / {summary['metrics']} 条快照")


def cmd_stats_report(args) -> None:
    with _c(args) as conn:
        md = report.report_markdown(conn)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"报表已写入 {args.out}")
    else:
        print(md)


def cmd_covers_make(args) -> None:
    import covers  # noqa: PLC0415

    day = style_mod.normalize_day(args.day)
    path = covers.render_cover_for_day(day)
    print(f"封面已生成 {path}")


# ---------------- live（P2 真机自动化；惰性导入 site_auto） ----------------

def _site():
    import site_auto  # noqa: PLC0415

    return site_auto


def cmd_live_login(args) -> None:
    sa = _site()
    print("请在打开的浏览器中扫码/登录小红书（个人号试验）。")
    result = sa.cmd_login(headless=args.headless, wait_minutes=args.wait_minutes)
    print(f"login result: {result}")


def cmd_live_status(args) -> None:
    sa = _site()
    sa.cmd_status(headless=args.headless)


def cmd_live_publish(args) -> None:
    day = style_mod.normalize_day(args.day)
    sa = _site()
    images_dir = Path(args.images_dir) if args.images_dir else None
    result = sa.publish_image_post(
        day=day, yes=args.yes, headless=args.headless, images_dir=images_dir,
        debug_shots=args.debug_shots, no_topics=args.no_topics,
    )
    if result.get("note_id"):
        sa.register_published(day, result["note_id"])
        print(f"note_id: {result['note_id']}")
    elif result.get("status") == "published_unverified":
        print("已发布但未捕获到 note_id：请到创作者中心手动核对，或用 `posts add` 登记。")
    else:
        print(f"未发布成功：{result.get('status')}（步骤：{result.get('steps')}）")


def cmd_live_pull(args) -> None:
    sa = _site()
    out_dir = Path(args.out) if args.out else None
    result = sa.pull_notes(out=out_dir, headless=args.headless)
    print(f"pull result: {result.get('status')} rows={result.get('rows')} json={result.get('json_bodies')}")


def cmd_live_detail(args) -> None:
    sa = _site()
    out_dir = Path(args.out) if args.out else None
    result = sa.pull_note_details(out=out_dir, headless=args.headless, max_notes=args.max)
    print(f"detail result: ok={len(result.get('ok', []))} fail={len(result.get('fail', {}))}")


def cmd_env_net(_args) -> None:
    import vpn  # noqa: PLC0415

    st = vpn.net_state()
    print(f"国内可达(小红书)={st['cn']}  国外可达={st['intl']}")
    if not st["cn"]:
        print("提示：小红书不可达——若你正开 Astrill 全局 VPN，需先断开；可用 `env vpn --apply` 尝试断开。")


def cmd_env_vpn(args) -> None:
    import vpn  # noqa: PLC0415

    vpn.plan(apply=args.apply)


# ---------------- main ----------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xhs-robot", description="小红书创作机器人（P1：日志中心 + 选题/草稿）")
    p.add_argument("--db", help="SQLite 文件路径（默认 <仓库>/data/xhs.db）")
    sub = p.add_subparsers(dest="cmd", required=True)

    j = sub.add_parser("journal", help="日志中心")
    js = j.add_subparsers(dest="sub", required=True)

    a = js.add_parser("add", help="记录一条日志")
    a.add_argument("--day", default=studio.today(), help="YYYY-MM-DD，默认今天")
    a.add_argument("--category", choices=style_mod.categories() + ["auto"], default="auto", help="分类，auto=关键词猜测")
    a.add_argument("--tags", default="", help="逗号分隔标签")
    a.add_argument("--mood", default=None, help="心情词（可选）")
    a.add_argument("text", nargs="*", help="正文；不传则从 stdin 读")
    a.set_defaults(fn=cmd_journal_add)

    l = js.add_parser("list", help="按条件列出日志")
    l.add_argument("--day", default=None)
    l.add_argument("--category", default=None)
    l.add_argument("--tag", default=None)
    l.add_argument("--limit", type=int, default=100)
    l.set_defaults(fn=cmd_journal_list)

    t = js.add_parser("today", help="今天的日志")
    t.add_argument("--day", default=studio.today())
    t.set_defaults(fn=cmd_journal_today)

    s = js.add_parser("search", help="全文搜索")
    s.add_argument("keyword")
    s.set_defaults(fn=cmd_journal_search)

    tp = js.add_parser("topics", help="主题聚合（选题参考）")
    tp.add_argument("--days", type=int, default=30)
    tp.add_argument("--group", choices=["category", "tag"], default="category")
    tp.add_argument("--limit", type=int, default=15)
    tp.set_defaults(fn=cmd_journal_topics)

    st = sub.add_parser("studio", help="创作工坊")
    sts = st.add_subparsers(dest="sub", required=True)
    n = sts.add_parser("new", help="初始化某天的草稿目录（brief + post 骨架）")
    n.add_argument("--day", default=studio.today())
    n.set_defaults(fn=cmd_studio_new)

    sv = sts.add_parser("save", help="保存定稿帖子包 drafts/<day>/post.md")
    sv.add_argument("--day", default=studio.today())
    sv.add_argument("--title", required=True, help="最终标题")
    sv.add_argument("--tags", default="", help="逗号分隔话题")
    sv.add_argument("--cover-text", default="", help="封面大字文案（P3 模板用）")
    sv.add_argument("--body-file", default=None, help="正文文件路径；缺省从 stdin 读")
    sv.set_defaults(fn=cmd_studio_save)

    sy = sub.add_parser("style", help="风格卡")
    sys_ = sy.add_subparsers(dest="sub", required=True)
    sh = sys_.add_parser("show", help="查看当前风格卡")
    sh.set_defaults(fn=cmd_style_show)

    po = sub.add_parser("posts", help="已发布笔记登记")
    pos = po.add_subparsers(dest="sub", required=True)
    pal = pos.add_parser("list", help="列出已登记笔记")
    pal.add_argument("--status", default=None)
    pal.add_argument("--limit", type=int, default=200)
    pal.set_defaults(fn=cmd_posts_list)
    paa = pos.add_parser("add", help="登记一篇发布（手动或发布器回填）")
    paa.add_argument("--note-id", required=True)
    paa.add_argument("--day", default=studio.today())
    paa.add_argument("--title", required=True)
    paa.add_argument("--tags", default="")
    paa.add_argument("--cover-text", default="")
    paa.add_argument("--body", default=None)
    paa.add_argument("--status", choices=["draft", "published"], default="published")
    paa.set_defaults(fn=cmd_posts_add)

    st = sub.add_parser("stats", help="数据回流（创作者中心导入/报表）")
    sts = st.add_subparsers(dest="sub", required=True)
    si = sts.add_parser("import", help="导入创作者中心导出的 CSV")
    si.add_argument("--file", required=True, help="CSV 路径")
    si.add_argument("--day", default=None, help="快照日（CSV 无日期列时使用）")
    si.set_defaults(fn=cmd_stats_import)
    si2 = sts.add_parser("pull-import", help="导入 live pull 抓取的 posted 列表 JSON")
    si2.add_argument("--file", required=True, help="pulls/network-*.json 路径")
    si2.add_argument("--day", default=None, help="快照日（默认今天）")
    si2.set_defaults(fn=cmd_stats_pull_import)
    sr = sts.add_parser("report", help="生成趋势/归因报表（markdown）")
    sr.add_argument("--out", default=None, help="写入文件；缺省打印到屏幕")
    sr.set_defaults(fn=cmd_stats_report)

    cv = sub.add_parser("covers", help="统一风格封面（P3）")
    cvs = cv.add_subparsers(dest="sub", required=True)
    cm = cvs.add_parser("make", help="按 drafts/<day>/post.md 生成封面图")
    cm.add_argument("--day", default=studio.today())
    cm.set_defaults(fn=cmd_covers_make)

    lv = sub.add_parser("live", help="真机自动化（需在本机能访问小红书的机器上运行）")
    lvs = lv.add_subparsers(dest="sub", required=True)
    ll = lvs.add_parser("login", help="打开创作者中心并扫码登录（持久化 profile）")
    ll.add_argument("--headless", action="store_true")
    ll.add_argument("--wait-minutes", type=float, default=3.0)
    ll.set_defaults(fn=cmd_live_login)
    ls = lvs.add_parser("status", help="检查登录状态")
    ls.add_argument("--headless", action="store_true")
    ls.set_defaults(fn=cmd_live_status)
    lp = lvs.add_parser("publish", help="发布 drafts/<day> 的定稿图文（发布前确认）")
    lp.add_argument("--day", default=studio.today())
    lp.add_argument("--yes", action="store_true", help="跳过发布前的人工确认")
    lp.add_argument("--headless", action="store_true")
    lp.add_argument("--no-topics", action="store_true", help="不自动添加话题")
    lp.add_argument("--images-dir", default=None, help="图片目录（默认 drafts/<day>/img 或封面）")
    lp.add_argument("--debug-shots", action="store_true", help="每步截图到 drafts/<day>/debug（校准用）")
    lp.set_defaults(fn=cmd_live_publish)

    pl = lvs.add_parser("pull", help="抓取已发布笔记列表/数据到 pulls/（供入库分析）")
    pl.add_argument("--headless", action="store_true", help="默认无头运行（登录态已持久化）")
    pl.add_argument("--out", default=None, help="输出目录（默认 <仓库>/pulls）")
    pl.set_defaults(fn=cmd_live_pull)

    pd = lvs.add_parser("detail", help="逐篇抓取笔记详情（7/30天趋势接口，含请求参数）")
    pd.add_argument("--headless", action="store_true")
    pd.add_argument("--out", default=None, help="输出目录（默认 <仓库>/pulls/details）")
    pd.add_argument("--max", type=int, default=20, help="最多抓取篇数")
    pd.set_defaults(fn=cmd_live_detail)

    en = sub.add_parser("env", help="网络/VPN 状态助手")
    ens = en.add_subparsers(dest="sub", required=True)
    en1 = ens.add_parser("net", help="报告国内/国外可达性")
    en1.set_defaults(fn=cmd_env_net)
    en2 = ens.add_parser("vpn", help="查看/断开 Astrill（默认只读，--apply 才执行）")
    en2.add_argument("--apply", action="store_true", help="真正执行断开动作")
    en2.set_defaults(fn=cmd_env_vpn)
    return p


def main(argv: list[str] | None = None) -> None:
    p = build_parser()
    args = p.parse_args(argv)
    try:
        args.fn(args)
    except ValueError as e:
        print(f"参数错误：{e}", file=sys.stderr)
        sys.exit(2)
    except ModuleNotFoundError as e:  # 缺依赖（Pillow/playwright 等）时给可操作提示
        missing = getattr(e, "name", None)
        print(
            f"缺少依赖 {missing}。请先运行 setup.bat（或 .venv\\Scripts\\python.exe 装 requirements），"
            "再用 .venv\\Scripts\\python.exe 运行本命令。",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
