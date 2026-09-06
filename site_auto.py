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
    "image_text_tab": "text=上传图文",
    "title_input": [
        'input[placeholder*="填写标题"]',
        'input.d-text',
        'input[placeholder*="标题"]',
    ],
    "body_editable": [
        '.tiptap.ProseMirror',
        'div.ql-editor',
        '[contenteditable="true"]',
    ],
    "file_input": 'input[type="file"]',
    "topic_add_btn": 'text=添加话题',
    "topic_search_input": ['input[placeholder*="搜索"]', 'input[placeholder*="话题"]'],
    "publish_btn": ["text=发布笔记", "button:has-text('发布')", "text=发布"],
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


def _dump_dom(page, path: Path) -> None:
    try:
        js = """() => {
          const out = {url: location.href};
          out.inputs = [...document.querySelectorAll('input, textarea')].map(e => ({
            tag: e.tagName, type: e.type||'', ph: e.placeholder||'', cls: (e.className||'').toString().slice(0,100)
          })).slice(0, 60);
          out.contenteditable = [...document.querySelectorAll('[contenteditable="true"]')].map(e => ({
            ph: e.getAttribute('data-placeholder')||'', cls: (e.className||'').toString().slice(0,100)
          })).slice(0, 10);
          out.buttons = [...document.querySelectorAll('button')].map(e => (e.innerText||'').trim())
            .filter(t => t && t.length < 14).slice(0, 80);
          return out;
        }"""
        import json  # noqa: PLC0415

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(page.evaluate(js), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _log(*a):
    print(*a, flush=True)


def _visible_editor(page) -> dict:
    """返回可见的输入框/富文本编辑区清单，用于按真实 DOM 定位标题与正文。"""
    return page.evaluate(
        """() => {
          const vis = el => { const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'; };
          const ins = [...document.querySelectorAll('input, textarea')].filter(vis)
            .map((e, i) => ({i, tag: e.tagName, type: e.type || '', ph: e.placeholder || '',
                              aria: e.getAttribute('aria-label') || '', cls: (e.className || '').toString().slice(0, 80)}));
          const cets = [...document.querySelectorAll('[contenteditable="true"]')].filter(vis)
            .map((e, i) => ({i, ph: e.getAttribute('data-placeholder') || '', aria: e.getAttribute('aria-label') || '',
                              cls: (e.className || '').toString().slice(0, 80), txt: (e.innerText || '').length}));
          return {ins, cets};
        }"""
    )


def _click_red_center(page, shot_path: Path) -> bool:
    """像素定位法：在截图底部区域找红色按钮块，换算页面坐标鼠标点击。

    用于按钮藏在 shadow DOM / 非常规标签时的兜底。返回是否找到并点击。
    """
    try:
        from PIL import Image  # noqa: PLC0415

        img = Image.open(shot_path).convert("RGB")
        w, h = img.size
        px = img.load()
        pts = []
        for y in range(int(h * 0.45), h):
            for x in range(int(w * 0.2), w):
                r, g, b = px[x, y]
                if r > 150 and g < 130 and b < 130:
                    pts.append((x, y))
        if len(pts) < 300:
            return False
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        span_w, span_h = max(xs) - min(xs), max(ys) - min(ys)
        # 按钮形态：宽 ≥50，高在 20~150 之间，避免误中大面积横幅
        if span_w < 50 or span_h < 20 or span_h > 150 or span_w > w * 0.8:
            return False
        cx, cy = int(sum(xs) / len(xs)), int(sum(ys) / len(ys))
        page.mouse.click(cx, cy)
        _log(f"coordinate-clicked red button at ({cx},{cy}) span=({span_w}x{span_h})")
        return True
    except Exception as e:  # noqa: BLE001
        _log(f"red-click unavailable: {type(e).__name__}")
        return False


def publish_image_post(*, day: str, yes: bool = False, headless: bool = False,
                       images_dir: Path | None = None, debug_shots: bool = False,
                       no_topics: bool = False) -> dict:
    """读取 drafts/<day> 的定稿并发布图文。返回 {status, note_id, url}。"""
    payload = build_payload(day, images_dir)
    _log("准备发布内容：")
    _log(f"  标题：{payload['title']}")
    _log(f"  正文 {len(payload['body'])} 字｜话题：{payload['tags']}｜图片 {len(payload['images'])} 张")
    for p in payload["images"]:
        _log(f"    - {p}")
    if not yes:
        ans = input("确认以上内容无误？发布到当前登录的小红书账号。输入 y 继续：").strip().lower()
        if ans not in ("y", "yes", "是"):
            return {"status": "cancelled"}

    shot_dir = REPO / "drafts" / day / "debug"
    result: dict = {"status": "failed", "note_id": None, "url": None, "steps": []}

    def mark(step: str):
        result["steps"].append(step)
        _log("STEP:", step)

    def shot(name: str):
        if debug_shots:
            shot_dir.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(path=str(shot_dir / f"{name}.png"))
            except Exception:  # noqa: BLE001
                pass

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
            _log("未登录。请先运行：cli.py live login。")
            ctx.close()
            return {"status": "login_required", **result}
        # 0) 切"上传图文"
        try:
            page.get_by_text("上传图文", exact=False).last.click(timeout=6000)
            mark("tab_clicked")
        except Exception as e:  # noqa: BLE001
            mark(f"tab_failed: {e}")
        page.wait_for_timeout(4000)
        shot("0_after_tab")
        _dump_dom(page, shot_dir / "dom-0-tab.json")

        # 1) 上传图片（accept 含 jpg 的文件框）
        try:
            idx = int(page.evaluate(
                """() => {
                  const els = [...document.querySelectorAll('input[type="file"]')];
                  for (let i = 0; i < els.length; i++)
                    if ((els[i].accept || '').toLowerCase().includes('jpg')) return i;
                  return els.length - 1;
                }"""
            ))
            page.locator('input[type="file"]').nth(idx).set_input_files(payload["images"], timeout=60000)
            mark("uploaded")
        except Exception as e:  # noqa: BLE001
            mark(f"upload_failed: {e}")
            _dump_dom(page, shot_dir / "dom-1-upload-fail.json")
            shot("1_upload_fail")
            ctx.close()
            return result
        page.wait_for_timeout(10000)
        shot("1_after_upload")
        _dump_dom(page, shot_dir / "dom-1-upload.json")

        # 2) 等标题框出现并填写（精确选择器）
        title_ok, body_ok = False, False
        title_loc = None
        for attempt in range(15):
            for sel in SELECTORS["title_input"]:
                loc = page.locator(sel).first
                try:
                    loc.wait_for(state="visible", timeout=2500)
                    title_loc = loc
                    break
                except Exception:  # noqa: BLE001
                    continue
            if title_loc is not None:
                break
            page.wait_for_timeout(1500)
        if title_loc is not None:
            try:
                title_loc.click(timeout=4000)
                title_loc.fill(payload["title"], timeout=8000)
                val = (title_loc.input_value(timeout=3000) or "")
                title_ok = payload["title"][:6] in val
            except Exception as e:  # noqa: BLE001
                mark(f"title_fill_err: {type(e).__name__}")
        mark("title_filled" if title_ok else "title_not_found")
        shot("2_after_title")
        _dump_dom(page, shot_dir / "dom-2-title.json")

        # 3) 填正文并校验（精确选择器）
        if title_ok:
            for sel in SELECTORS["body_editable"]:
                loc = page.locator(sel).first
                try:
                    loc.wait_for(state="visible", timeout=4000)
                    loc.click(timeout=5000)
                    loc.fill(payload["body"], timeout=15000)
                    got = (loc.inner_text(timeout=5000) or "").strip()
                    body_ok = len(got) >= 50
                    if body_ok:
                        break
                except Exception:  # noqa: BLE001
                    continue
        mark("body_filled" if body_ok else "body_not_filled")
        shot("3_after_body")
        _dump_dom(page, shot_dir / "dom-3-body.json")
        if not (title_ok and body_ok):
            ctx.close()
            return result

        # 4) 话题（找不到就快速跳过，不阻塞发布）
        if not no_topics and payload["tags"]:
            added = 0
            for tag in payload["tags"]:
                if not try_click(SELECTORS["topic_add_btn"], timeout_ms=2000):
                    continue
                search = None
                for sel in SELECTORS["topic_search_input"]:
                    loc = page.locator(sel).first
                    try:
                        loc.wait_for(state="visible", timeout=3000)
                        loc.fill(tag)
                        search = loc
                        break
                    except Exception:  # noqa: BLE001
                        continue
                if search is None:
                    continue
                page.wait_for_timeout(1200)
                try:
                    page.locator("li, .topic-item, [class*=suggest]").first.click(timeout=3000)
                    added += 1
                except Exception:  # noqa: BLE001
                    pass
            mark(f"topics_added={added}")
        shot("4_after_topics")

        # 5) 发布：点左侧红色“发布笔记”，再处理可能的确认弹窗
        if not try_click(SELECTORS["publish_btn"], timeout_ms=6000):
            mark("publish_btn_not_found")
            _dump_dom(page, shot_dir / "dom-5-no-publish.json")
            ctx.close()
            return result
        mark("publish_clicked")
        page.wait_for_timeout(2500)
        # 兜底：滚动到底部，用像素法点红色发布按钮（处理 shadow DOM 等情况）
        try:
            for _ in range(3):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(700)
            shot_dir.mkdir(parents=True, exist_ok=True)
            tmp_png = shot_dir / "coordinate.png"
            page.screenshot(path=str(tmp_png))
            _click_red_center(page, tmp_png)
            page.wait_for_timeout(3000)
        except Exception:  # noqa: BLE001
            pass
        # 弹窗确认：找非侧栏区域(x>208)新出现的“发布/确认/确定/继续发布”类按钮并点击
        try:
            dialog_target = page.evaluate(
                """() => {
                  const vis = el => { const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
                  const hits = [];
                  for (const e of document.querySelectorAll('button,div,span,a')) {
                    if (e.childElementCount > 2 || !vis(e)) continue;
                    const r = e.getBoundingClientRect();
                    const t = (e.textContent || '').trim().replace(/\\s+/g, '');
                    if (r.x > 208 && /(发布|确认|确定|继续|完成)/.test(t) && t.length <= 8) {
                      hits.push({x: Math.round(r.x), y: Math.round(r.y), t});
                    }
                  }
                  hits.sort((a, b) => b.y - a.y || a.x - b.x);
                  return hits[0] ? hits[0].t : null;
                }"""
            )
            if dialog_target:
                loc = page.get_by_text(dialog_target, exact=True).last
                loc.wait_for(state="visible", timeout=3000)
                loc.click(timeout=4000)
                mark(f"dialog_confirm:{dialog_target}")
        except Exception as e:  # noqa: BLE001
            mark(f"dialog_skip: {type(e).__name__}")
        page.wait_for_timeout(8000)
        shot("5_after_publish")
        url = page.url
        try:
            content_sniff = str(page.evaluate("document.body ? document.body.innerText.slice(0, 3000) : ''"))
        except Exception:  # noqa: BLE001
            content_sniff = ""
        success_text = ("发布成功" in content_sniff) or ("审核" in content_sniff) or ("已发布" in content_sniff)
        note_id = extract_note_id(url) or extract_note_id(content_sniff)
        result.update(status="published" if (success_text or note_id or "success" in url) else "published_unverified",
                      note_id=note_id, url=url)
        _log(f"发布结果：{result['status']} note_id={note_id}")
        (REPO / "drafts" / day / "publish-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            ctx.close()
        except Exception:  # noqa: BLE001
            pass
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
    """监听页面网络响应，把疑似“笔记数据 JSON”的响应连同请求方式/参数保存下来。"""
    captured: list[dict] = []

    def on_response(resp):
        try:
            ctype = resp.headers.get("content-type", "")
            url = resp.url
            if "json" not in ctype and "text" not in ctype:
                return
            if not any(k in url for k in ("note", "content", "data", "list", "publish", "article")):
                return
            req = resp.request
            post_data = req.post_data if req else None
            body = resp.text()
            if len(body) < 200 or len(captured) >= max_bodies:
                return
            captured.append({
                "url": url,
                "method": (req.method if req else "GET"),
                "post_data": post_data[:4000] if post_data else None,
                "body": body[:200_000],
            })
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


# ============ 取数：逐篇笔记详情（内容管理 → 点开分析 → 抓 note_detail 等接口） ============

DETAIL_TRIGGER_TEXTS = ["数据分析", "查看数据", "分析", "数据"]


def pull_note_details(*, out: Path | None = None, headless: bool = True, max_notes: int = 20) -> dict:
    """对已登记的每篇笔记：进内容管理→点开该篇分析页→抓详情接口（含请求参数）落盘。

    页面结构常改，属校准型代码：先跑通一篇看 pulls/details/<note_id>/ 里的接口与参数，
    再决定是否/如何批量。返回 {ok: [note_id...], fail: {note_id: err}}。
    """
    base = Path(out) if out else REPO / "pulls" / "details"
    base.mkdir(parents=True, exist_ok=True)
    with db.connect() as conn:
        posts = db.posts_list(conn, status="published")
    ok, fail = [], {}
    for p in posts[:max_notes]:
        note_id, title = p["note_id"], p.get("title") or ""
        od = base / note_id
        od.mkdir(parents=True, exist_ok=True)
        err = None
        try:
            with sync_playwright() as pw:
                ctx = pw.chromium.launch_persistent_context(
                    str(PROFILE_DIR), headless=headless,
                    args=["--disable-blink-features=AutomationControlled"])
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                captured = _collect_network_json(page, od, max_bodies=80)
                _open(page, CREATOR_HOME, wait_ms=6000)
                if login_state(page) == "login_required":
                    raise RuntimeError("login_required")
                landed = False
                for url in CONTENT_MANAGER_URLS:
                    try:
                        _open(page, url, wait_ms=7000)
                        landed = True
                        break
                    except Exception:  # noqa: BLE001
                        continue
                if not landed:
                    page.get_by_text("内容管理", exact=False).first.click(timeout=4000)
                    page.wait_for_timeout(5000)
                # 用标题定位该篇所在行，优先点行内“数据/分析”类按钮
                hint = (title or note_id)[:8]
                clicked = False
                try:
                    loc = page.get_by_text(hint, exact=False).first
                    loc.wait_for(state="visible", timeout=6000)
                    row = loc.locator(
                        "xpath=ancestor::tr[1] | ancestor::li[1] | ancestor::div[contains(@class,'note')][1]"
                    ).first
                    for t in DETAIL_TRIGGER_TEXTS:
                        try:
                            row.get_by_text(t, exact=False).first.click(timeout=2500)
                            clicked = True
                            break
                        except Exception:  # noqa: BLE001
                            continue
                    if not clicked:
                        loc.click(timeout=3000)  # 没有按钮就点标题行
                        clicked = True
                except Exception as e:  # noqa: BLE001
                    err = f"locate_row: {e}"
                page.wait_for_timeout(9000)
                (od / "screen.png").write_bytes(page.screenshot())
                for i, cap in enumerate(captured):
                    (od / f"network-{i:02d}.json").write_text(
                        json.dumps(cap, ensure_ascii=False, indent=2), encoding="utf-8")
                text = ""
                try:
                    text = page.evaluate("document.body ? document.body.innerText.slice(0, 6000) : ''")
                except Exception:  # noqa: BLE001
                    pass
                (od / "page-text.txt").write_text(text, encoding="utf-8")
                ctx.close()
            if err:
                fail[note_id] = err
            else:
                ok.append(note_id)
                print(f"✓ {note_id} {title[:20]} → {od}")
        except Exception as e:  # noqa: BLE001
            fail[note_id] = str(e)[:200]
            print(f"✗ {note_id}: {str(e)[:120]}")
    (base / "summary.json").write_text(json.dumps({"ok": ok, "fail": fail}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"详情抓取完成：ok={len(ok)} fail={len(fail)} → {base}")
    return {"ok": ok, "fail": fail}
