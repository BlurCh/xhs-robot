"""P2 真机自动化（Playwright）：登录状态 / 图文发布 / 取数入口。

重要现实：
- 本模块必须在「能访问小红书」的机器/网络下运行（DSH 沙箱内到不了小红书）。
- 页面结构随时可能改版；本文件顶部的 SELECTORS 是唯一需要校准的地方。
  首次真机运行请用 --debug-shots 并把产物截图/日志发回，我据此校准选择器。
- 灰度纪律：默认只在你指定账号上发布；发布前有最终确认（除非 --yes）。
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import db

REPO = Path(__file__).resolve().parent
PROFILE_DIR = REPO / ".pw-profile"
CREATOR_HOME = "https://creator.xiaohongshu.com"
PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?source=official"
NOTE_ID_RE = re.compile(r"[0-9a-fA-F]{24}")

# ============ 唯一需要校准的地方（页面改版时改这里） ============
SELECTORS = {
    "title_input": [
        'input[placeholder*="标题"]',
        'textarea[placeholder*="标题"]',
        'input.title-input',
        'div.note-editor input',
    ],
    "body_editable": [
        '[contenteditable="true"]',
        'div.ql-editor',
        'div[data-placeholder*="正文"]',
    ],
    "file_input": 'input[type="file"]',
    "topic_add_btn": 'text=添加话题',
    "topic_search_input": ['input[placeholder*="搜索"]', 'input[placeholder*="话题"]'],
    "publish_btn": ["button:has-text('发布')", "text=发布笔记"],
    "confirm_btn": ["text=继续发布", "text=确认", "button:has-text('确定')"],
}
LOGIN_MARKERS_JS = (
    "location.href.includes('passport') ? 'login_required' : "
    "(document.querySelector('img[class*=avatar], .user-info, [class*=sidebar]') ? 'ok' : 'unknown')"
)


def extract_note_id(url_or_text: str) -> str | None:
    m = NOTE_ID_RE.search(url_or_text or "")
    return m.group() if m else None


def images_of(day: str, images_dir: Path | None = None) -> list[Path]:
    """默认取 drafts/<day>/img/*，没有则退回封面 cover.png。返回按名排序的绝对路径。"""
    d = images_dir or (REPO / "drafts" / day / "img")
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    found = sorted(p for p in d.iterdir() if p.suffix.lower() in exts) if d.exists() else []
    if not found:
        cover = REPO / "drafts" / day / "cover.png"
        if cover.exists():
            found = [cover]
    return found


def build_payload(day: str, images_dir: Path | None = None) -> dict:
    """从 drafts/<day>/post.md 读定稿并组发布负载。"""
    sys.path.insert(0, str(REPO))
    import covers  # noqa: PLC0415

    fm = covers.load_post_frontmatter(REPO / "drafts" / day / "post.md")
    images = images_of(day, images_dir)
    if not images:
        raise ValueError(f"drafts/{day} 下没有可上传的图片（放 img/ 目录或用 covers make 生成封面）")
    return {
        "day": day,
        "title": (fm.get("title") or "").strip(),
        "body": (fm.get("body") or "").strip(),
        "tags": list(fm.get("tags") or []),
        "cover_text": (fm.get("cover_text") or "").strip(),
        "images": [str(p) for p in images],
    }


def login_state(page) -> str:
    try:
        return str(page.evaluate(LOGIN_MARKERS_JS))
    except Exception:  # noqa: BLE001 - 页面瞬态
        return "unknown"


def _open(page, url: str, wait_ms: int = 15000) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(wait_ms)


def cmd_login(*, headless: bool = False, wait_minutes: float = 3.0) -> str:
    """打开创作者中心，等用户扫码登录；登录态持久化在 .pw-profile。"""
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(PROFILE_DIR), headless=headless,
                                                    args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _open(page, CREATOR_HOME)
        deadline = time.monotonic() + wait_minutes * 60
        state = login_state(page)
        print(f"当前登录状态：{state}")
        if state == "ok":
            ctx.close()
            return "already_logged_in"
        print("请在打开的浏览器里扫码/登录小红书（登录一次即可，profile 会记住）…")
        while time.monotonic() < deadline:
            if login_state(page) == "ok":
                print("登录成功 ✔（已持久化，下次免扫码）")
                ctx.close()
                return "ok"
            time.sleep(2)
        ctx.close()
        return "timeout"


def cmd_status(*, headless: bool = True) -> str:
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(PROFILE_DIR), headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _open(page, CREATOR_HOME, wait_ms=10000)
        state = login_state(page)
        print(f"url={page.url[:70]} 登录状态={state}")
        ctx.close()
        return state


def publish_image_post(*, day: str, yes: bool = False, headless: bool = False,
                       images_dir: Path | None = None, debug_shots: bool = False,
                       no_topics: bool = False) -> dict:
    """读取 drafts/<day> 的定稿并发布图文。返回 {status, note_id, url}。"""
    payload = build_payload(day, images_dir)
    print("准备发布内容：")
    print(f"  标题：{payload['title']}")
    print(f"  正文 {len(payload['body'])} 字｜话题：{payload['tags']}｜图片 {len(payload['images'])} 张")
    for p in payload["images"]:
        print(f"    - {p}")
    if not yes:
        ans = input("确认以上内容无误？发布到当前登录的小红书账号。输入 y 继续：").strip().lower()
        if ans not in ("y", "yes", "是"):
            return {"status": "cancelled"}

    shot_dir = REPO / "drafts" / day / "debug"
    result: dict = {"status": "failed", "note_id": None, "url": None, "steps": []}

    def shot(name: str):
        if debug_shots:
            shot_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(shot_dir / f"{name}.png"))

    def try_click(candidates: list[str], *, timeout_ms: int = 5000) -> bool:
        for sel in candidates:
            loc = page.locator(sel).first
            try:
                loc.wait_for(state="visible", timeout=timeout_ms)
                loc.click(timeout=timeout_ms)
                return True
            except Exception:  # noqa: BLE001
                continue
        return False

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(PROFILE_DIR), headless=headless,
                                                    args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _open(page, PUBLISH_URL)
        if login_state(page) == "login_required":
            print("未登录。请先运行：cli.py live login（扫码一次）。")
            ctx.close()
            return {"status": "login_required", **result}
        shot("0_after_open")

        # 1) 上传图片
        try:
            page.locator(SELECTORS["file_input"]).first.set_input_files(payload["images"], timeout=60000)
            page.wait_for_timeout(12000)  # 上传 + 处理留缓冲
        except Exception as e:  # noqa: BLE001
            result["steps"].append(f"upload_failed: {e}")
            shot("1_upload_fail")
            ctx.close()
            return result
        result["steps"].append("uploaded")
        shot("1_after_upload")

        # 2) 标题
        if not try_click_title_fill(payload["title"], page):
            result["steps"].append("title_not_filled")
        else:
            result["steps"].append("title_filled")
        shot("2_after_title")

        # 3) 正文（contenteditable 支持 fill）
        filled_body = False
        for sel in SELECTORS["body_editable"]:
            loc = page.locator(sel).first
            try:
                loc.wait_for(state="visible", timeout=4000)
                loc.click(timeout=4000)
                loc.fill(payload["body"], timeout=10000)
                filled_body = True
                break
            except Exception:  # noqa: BLE001
                continue
        result["steps"].append("body_filled" if filled_body else "body_not_filled")
        shot("3_after_body")

        # 4) 话题
        if not no_topics and payload["tags"]:
            added = 0
            for tag in payload["tags"]:
                if not try_click(SELECTORS["topic_add_btn"]):
                    continue
                search = None
                for sel in SELECTORS["topic_search_input"]:
                    loc = page.locator(sel).first
                    try:
                        loc.wait_for(state="visible", timeout=4000)
                        loc.fill(tag)
                        search = loc
                        break
                    except Exception:  # noqa: BLE001
                        continue
                if search is None:
                    continue
                page.wait_for_timeout(1500)
                try:
                    page.locator("li, .topic-item, [class*=suggest]").first.click(timeout=4000)
                    added += 1
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(800)
            result["steps"].append(f"topics_added={added}")
        shot("4_after_topics")

        # 5) 发布
        if not try_click(SELECTORS["publish_btn"], timeout_ms=8000):
            result["steps"].append("publish_btn_not_found")
            shot("5_publish_fail")
            ctx.close()
            return result
        page.wait_for_timeout(6000)
        # 可能的二次确认/风险提示弹窗
        try_click(SELECTORS["confirm_btn"], timeout_ms=3000)
        page.wait_for_timeout(6000)
        shot("5_after_publish")
        url = page.url
        note_id = extract_note_id(url) or extract_note_id(page.content())
        result.update(status="published" if note_id or "success" in url else "published_unverified",
                      note_id=note_id, url=url, steps=result["steps"])
        print(f"发布结果：{result['status']} note_id={note_id}")
        (REPO / "drafts" / day / "publish-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        ctx.close()
        return result


def try_click_title_fill(title: str, page) -> bool:
    for sel in SELECTORS["title_input"]:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=4000)
            loc.click(timeout=4000)
            loc.fill(title, timeout=8000)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def register_published(day: str, note_id: str) -> None:
    """发布成功后回填 posts 表。"""
    payload = build_payload(day)
    with db.connect() as conn:
        db.posts_upsert(conn, note_id=note_id, day=day, title=payload["title"],
                        tags=payload["tags"], cover_text=payload["cover_text"], body=payload["body"])
    print(f"已登记发布 {note_id} → `posts list` 可查")


# ============ 取数：抓已发布笔记（内容管理页 + 网络 JSON 兜底） ============

CONTENT_MANAGER_URLS = [
    "https://creator.xiaohongshu.com/new/note-manager?source=official",
    "https://creator.xiaohongshu.com/note-manager",
]
_ROW_JS = r"""
() => {
  const sels = ['tr', '[class*="note-item"]', '[class*="content-item"]', '[class*="list-item"]', 'li'];
  for (const s of sels) {
    const els = [...document.querySelectorAll(s)];
    const rows = els.map(e => (e.innerText || '').replace(/\s+/g, ' ').trim()).filter(t => t.length > 8);
    if (rows.length > 2) return rows.slice(0, 300);
  }
  return [];
}
"""


def _collect_network_json(page, out_dir: Path, max_bodies: int = 40) -> list[dict]:
    """监听页面网络响应，把疑似“笔记数据 JSON”的响应体保存下来供列映射。"""
    captured: list[dict] = []

    def on_response(resp):
        try:
            ctype = resp.headers.get("content-type", "")
            url = resp.url
            if "json" not in ctype and "text" not in ctype:
                return
            if not any(k in url for k in ("note", "content", "data", "list", "publish", "article")):
                return
            body = resp.text()
            if len(body) < 200 or len(captured) >= max_bodies:
                return
            captured.append({"url": url, "body": body[:200_000]})
        except Exception:  # noqa: BLE001 - 跨域/流式响应取不到就跳过
            pass

    page.on("response", on_response)
    return captured


def pull_notes(*, out: Path | None = None, headless: bool = True) -> dict:
    """抓实验账号已发布笔记：内容管理列表文本 + 网络 JSON 兜底，落盘供人工/离线解析。

    产物（out 目录）：rows.txt（列表行文本）、network-*.json（疑似数据接口响应）、
    summary.json、screen.png。返回摘要 dict。列映射需人工/后续校准。
    """
    out_dir = Path(out) if out else REPO / "pulls"
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict = {"status": "failed", "rows": 0, "json_bodies": 0, "out": str(out_dir)}

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(PROFILE_DIR), headless=headless,
                                                    args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        captured = _collect_network_json(page, out_dir)

        # 1) 创作者中心首页
        _open(page, CREATOR_HOME, wait_ms=8000)
        if login_state(page) == "login_required":
            result["status"] = "login_required"
            ctx.close()
            return result
        # 2) 尝试直达内容管理，或从首页点“内容管理/笔记管理”
        landed = False
        for url in CONTENT_MANAGER_URLS:
            try:
                _open(page, url, wait_ms=8000)
                landed = True
                break
            except Exception:  # noqa: BLE001
                continue
        if not landed:
            for text in ("内容管理", "笔记管理", "作品管理", "管理"):
                try:
                    page.get_by_text(text, exact=False).first.click(timeout=4000)
                    page.wait_for_timeout(6000)
                    break
                except Exception:  # noqa: BLE001
                    continue
        page.wait_for_timeout(4000)
        (out_dir / "screen.png").write_bytes(page.screenshot())
        try:
            rows = list(page.evaluate(_ROW_JS))
        except Exception as e:  # noqa: BLE001
            rows = []
            result["dom_error"] = str(e)
        # 3) 落盘
        (out_dir / "rows.txt").write_text("\n".join(f"- {r}" for r in rows), encoding="utf-8")
        body_text = ""
        try:
            body_text = page.evaluate("document.body ? document.body.innerText.slice(0, 8000) : ''")
        except Exception:  # noqa: BLE001
            pass
        (out_dir / "page-text.txt").write_text(body_text, encoding="utf-8")
        for i, cap in enumerate(captured):
            (out_dir / f"network-{i:02d}.json").write_text(
                json.dumps(cap, ensure_ascii=False, indent=2), encoding="utf-8")
        result.update(status="ok", rows=len(rows), json_bodies=len(captured))
        (out_dir / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"抓取完成：列表行 {len(rows)} 条，网络 JSON {len(captured)} 个 → {out_dir}")
        ctx.close()
        return result
