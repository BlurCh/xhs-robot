r"""
数据回流报表示例（独立 demo，不污染 data/xhs.db）。
用内置样例数据展示「导入 CSV → 趋势/归因报表」的输出形态。
运行：.\.venv\Scripts\python.exe selftest_demo_report.py
产物：.selftest\demo_report\ 目录下（已 gitignore）
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

import db  # noqa: E402
import report  # noqa: E402

SAMPLE_CSV = """note_id,标题,统计日期,曝光,观看,点赞,收藏,评论,分享,涨粉
1f2e3d4c5b6a7988a7b6c5d4,一天过完没痕迹？试试三步复盘法,2026-09-05,3200,1800,156,89,23,11,5
1f2e3d4c5b6a7988a7b6c5d4,一天过完没痕迹？试试三步复盘法,2026-09-06,5100,2900,233,134,31,15,8
9a8b7c6d5e4f3a2b1c0d9e8f,读完《认知觉醒》的三点启发,2026-09-03,2100,1200,98,76,12,6,3
9a8b7c6d5e4f3a2b1c0d9e8f,读完《认知觉醒》的三点启发,2026-09-06,6800,4100,312,208,47,19,11
5e4d3c2b1a0f9e8d7c6b5a4f,散步时想明白的一件事,2026-09-02,900,600,41,12,4,2,1
"""

if __name__ == "__main__":
    out_dir = REPO / ".selftest" / "demo_report"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "sample_creator.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8-sig")
    demo_db = out_dir / "demo.db"
    demo_db.unlink(missing_ok=True)
    with db.connect(demo_db) as conn:
        summary = report.import_creator_csv(conn, csv_path)
        print("导入摘要:", summary)
        md = report.report_markdown(conn)
    out = out_dir / "report.md"
    out.write_text(md, encoding="utf-8")
    print("报表已写入:", out)
