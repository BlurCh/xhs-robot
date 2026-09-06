r"""第一期自测（无框架）：db / style / studio / cli 冒烟。

运行：python C:\Harness_Projects\xhs-robot\selftest.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

import covers  # noqa: E402
import db  # noqa: E402
import report  # noqa: E402
import site_auto  # noqa: E402
import studio  # noqa: E402
import style as style_mod  # noqa: E402


def main() -> None:
    tmp = REPO / ".selftest"
    tmp.mkdir(exist_ok=True)
    try:
        _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("P1 自测全部通过 ✔")


def _run(tmp: Path) -> None:
    from datetime import date, timedelta

    db_path = tmp / "t.db"
    d2 = (date.today() - timedelta(days=2)).isoformat()
    d1 = (date.today() - timedelta(days=1)).isoformat()
    d0 = date.today().isoformat()

    with db.connect(db_path) as conn:
        id1 = db.journal_add(conn, day=d2, text="今天读完《认知觉醒》，学到如何复盘", category="auto", tags=["读书", "复盘"])
        id2 = db.journal_add(conn, day=d1, text="有点焦虑，感觉进度慢", category="auto", tags=["心情"])
        id3 = db.journal_add(conn, day=d0, text="想写一篇关于复盘的帖子", category="auto", tags=["想法", "复盘"])
        assert id1 and id2 and id3
        assert style_mod.auto_category("今天读完《认知觉醒》，学到如何复盘") == "学习"
        assert style_mod.auto_category("有点焦虑，感觉进度慢") == "心情"
        assert style_mod.auto_category("想写一篇关于复盘的帖子") == "内容素材"

        rows = db.journal_list(conn, tag="复盘")
        assert len(rows) == 2, rows
        assert rows[0]["tags"] == ["想法", "复盘"]

        hits = db.journal_search(conn, "焦虑")
        assert len(hits) == 1 and hits[0]["id"] == id2

        top = db.journal_topics(conn, days=30, group="tag")
        names = [t["name"] for t in top]
        assert names[0] == "复盘", names

        brief = studio.build_brief(conn, day=d0, lookback_days=30)
        assert brief["today_logs"][0]["id"] == id3
        md = studio.brief_markdown(brief)
        assert "选题 Brief" in md and "复盘" in md

    # CLI 冒烟：journal list / topics / studio new / studio save
    cli = sys.executable
    smoke = (
        (["journal", "list", "--tag", "复盘"], None),
        (["journal", "topics", "--days", "30", "--group", "tag"], None),
        (["studio", "new", "--day", d0], None),
        (["studio", "save", "--day", d0, "--title", "测试定稿", "--tags", "复盘,经验"], "正文内容\n第二行"),
    )
    for argv, stdin in smoke:
        r = subprocess.run(
            [cli, str(REPO / "cli.py"), "--db", str(db_path), *argv],
            capture_output=True, text=True, encoding="utf-8", input=stdin,
        )
        assert r.returncode == 0, (argv, r.stderr)
        assert r.stdout.strip(), argv
        print("OK  cli:", " ".join(argv))

    post = studio.save_post(d0, title="测试标题", tags=["复盘"], cover_text="测试封面", body="正文")
    assert post.exists() and "测试标题" in post.read_text(encoding="utf-8")

    # ---- P3 封面引擎（离线渲染 + frontmatter 解析）----
    from PIL import Image  # noqa: PLC0415

    fm = covers.load_post_frontmatter(REPO / "drafts" / d0 / "post.md")
    assert fm["title"] == "测试标题" and fm["cover_text"] == "测试封面"
    cover_png = covers.make_cover("复盘三步法实测：把一天变成资产", tmp / "cover.png",
                                  palette=["#FFFFFF", "#1F2937", "#F97316"])
    assert cover_png.exists()
    with Image.open(cover_png) as im:
        assert im.size == (900, 1200), im.size

    # ---- v2/v3：posts / metrics / account_daily + 导入 ----
    with db.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        db.account_daily_upsert(conn, day="2026-09-01", views=5, impl=20, likes=1)
        al = db.account_daily_list(conn, days=3)
        assert len(al) == 1 and al[0]["impl"] == 20
        db.account_daily_upsert(conn, day="2026-09-01", views=7, impl=21)
        al = db.account_daily_list(conn, days=3)
        assert al[0]["views"] == 7 and al[0]["impl"] == 21
        db.posts_upsert(conn, note_id="a" * 24, day=d2, title="复盘三步法实测", tags=["复盘"])
        db.posts_upsert(conn, note_id="b" * 24, day=d1, title="读书笔记：认知觉醒", tags=["读书"])
        db.metrics_upsert(conn, note_id="a" * 24, day=d2, impressions=500, views=300, likes=20, collects=10)
        db.metrics_upsert(conn, note_id="a" * 24, day=d1, impressions=1200, views=900, likes=88, collects=40)
        hist = db.metrics_history(conn, note_id="a" * 24)
        assert len(hist) == 2 and hist[1]["impressions"] == 1200
        joined = db.posts_with_metrics(conn, require_snapshots=2)
        assert len(joined) == 1 and joined[0]["likes"] == 88
        md = report.report_markdown(conn)
        assert "复盘三步法实测" in md and "归因" in md

    # CSV 导入（创作者中心导出格式样例）
    csv_path = tmp / "creator_export.csv"
    csv_path.write_text(
        "笔记ID,标题,统计日期,曝光,观看,点赞,收藏,评论,分享,涨粉\n"
        f"{'c' * 24},导入测试笔记,{d0},800,600,50,30,5,3,2\n",
        encoding="utf-8-sig",
    )
    with db.connect(db_path) as conn:
        summary = report.import_creator_csv(conn, csv_path)
        assert summary == {"rows": 1, "posts": 1}, summary
        rows = db.posts_list(conn)
        assert any(r["title"] == "导入测试笔记" for r in rows)
        j2 = db.posts_with_metrics(conn, require_snapshots=1)
        imported = [r for r in j2 if r["title"] == "导入测试笔记"]
        assert len(imported) == 1 and imported[0]["likes"] == 50

    # live pull 接口 JSON 导入（posted 列表捕获格式）
    pull_json = tmp / "network-pull.json"
    pull_json.write_text(json.dumps({
        "url": "https://creator.xiaohongshu.com/api/galaxy/v2/creator/note/user/posted?tab=0&page=0",
        "body": json.dumps({"data": {"notes": [
            {"id": "ab" * 12, "display_title": "拉取笔记A", "view_count": "99", "likes": "8",
             "collected_count": "4", "comments_count": "2", "shared_count": "1", "visible_time": "1775729122"},
        ]}}),
    }), encoding="utf-8")
    with db.connect(db_path) as conn:
        summary = report.import_pull_json(conn, pull_json, snapshot_day=d0)
        assert summary == {"notes": 1, "metrics": 1}, summary
        rows = db.posts_list(conn)
        pulled = [r for r in rows if r["note_id"] == "ab" * 12]
        assert len(pulled) == 1 and pulled[0]["title"] == "拉取笔记A"
        hist = db.metrics_history(conn, note_id="ab" * 12)
        assert hist[0]["views"] == 99 and hist[0]["likes"] == 8 and hist[0]["shares"] == 1, hist

    # CLI 冒烟补充：posts / stats（第二轮）
    report_path = tmp / "report.md"
    smoke2 = (
        ["posts", "list"],
        ["stats", "report", "--out", str(report_path)],
    )
    for argv in smoke2:
        r = subprocess.run(
            [cli, str(REPO / "cli.py"), "--db", str(db_path), *argv],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert r.returncode == 0, (argv, r.stderr)
        assert r.stdout.strip(), argv
        print("OK  cli:", " ".join(argv))
    assert report_path.exists() and "导入测试笔记" in report_path.read_text(encoding="utf-8")

    # CLI 容错：非法日期应报友好错误而非裸 traceback
    bad = subprocess.run(
        [cli, str(REPO / "cli.py"), "--db", str(db_path), "journal", "add", "--day", "2026-13-99", "测试"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert bad.returncode == 2, bad.returncode
    assert "参数错误" in (bad.stderr + bad.stdout)
    assert "Traceback" not in (bad.stderr + bad.stdout)
    print("OK  cli friendly-error")

    # ---- P2 发布负载组装（离线可测部分）----
    assert site_auto.extract_note_id("https://www.xiaohongshu.com/explore/64a1b2c3d4e5f6a7b8c9d0e1?x=x") == "64a1b2c3d4e5f6a7b8c9d0e1"
    img_dir = REPO / "drafts" / d0 / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    from PIL import Image  # noqa: PLC0415

    Image.new("RGB", (8, 8), (255, 255, 255)).save(img_dir / "p1.png")
    payload = site_auto.build_payload(d0)
    fm_expected = covers.load_post_frontmatter(REPO / "drafts" / d0 / "post.md")
    assert payload["title"] == fm_expected["title"] and payload["title"]
    assert len(payload["images"]) == 1 and payload["images"][0].endswith("p1.png")
    print("OK  site_auto payload/extract")

    # ---- P3 生图接口预留：未配 key 时应干净地报指引 ----
    import images  # noqa: PLC0415

    assert images.available() is False
    try:
        images.generate_post_images(d0)
        raise AssertionError("未配 key 不应生成成功")
    except RuntimeError as e:
        assert "XHS_IMAGE_API_KEY" in str(e)
    prompt = images.style_prompt_for_day(d0)
    assert prompt and "主题：" in prompt
    shutil.rmtree(img_dir, ignore_errors=True)  # 清理测试图片，避免污染真实草稿
    print("OK  images interface reserve")


if __name__ == "__main__":
    main()
