"""P3 生图流水线（接口预留）。

当前没有图像 API key 时不产生任何网络调用；拿到 key 后只需：
1. 设环境变量（默认读 XHS_IMAGE_API_KEY）或改 config/vision.json；
2. 填 provider 与 model（已内置三家主流形态的接入点注释）；
3. 调用 generate_post_images(day) 即可按统一风格生成配图。
风格统一靠「固定风格卡 prompt + 每次相同 seed/风格词」，一致性以人工抽检为准。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import covers
import style as style_mod

REPO = Path(__file__).resolve().parent
VISION_CONFIG = REPO / "config" / "vision.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "provider": None,          # "volc_seedream" | "ali_wanx" | "openai_image" | ...
    "model": None,
    "api_key_env": "XHS_IMAGE_API_KEY",
    "api_base": None,          # 火山方舟/阿里百炼兼容 OpenAI images 形态时填网关地址
    "style_suffix": "扁平插画风，低饱和白底+橙色点缀，简洁留白，无文字",
    "size": "3:4",
}

# provider 接入点说明（拿到 key 时按需启用）
# - volc_seedream: 火山方舟 OpenAI 兼容 /images/generations，model=seedream-x
# - ali_wanx: 阿里百炼 dashscope 兼容 /images/generations，model=wanx2.x-t2i-turbo
# - openai_image: 标准 OpenAI images API，model=gpt-image-1 / dall-e-3
# 各家鉴权/URL 不同，接入时在此函数内完成唯一分支。


def load_config() -> dict:
    if not VISION_CONFIG.exists():
        VISION_CONFIG.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        cfg = json.loads(VISION_CONFIG.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        cfg = dict(DEFAULT_CONFIG)
    cfg.setdefault("enabled", False)
    return cfg


def available() -> bool:
    cfg = load_config()
    key = os.environ.get(cfg.get("api_key_env", "XHS_IMAGE_API_KEY"), "")
    return bool(cfg.get("enabled") and cfg.get("provider") and cfg.get("model") and key)


def style_prompt_for_day(day: str) -> str:
    """固定风格的配图 prompt：取帖子主题 + 风格卡 + 风格后缀，保证每篇同调。"""
    fm = covers.load_post_frontmatter(REPO / "drafts" / day / "post.md")
    cfg = load_config()
    style_cfg = style_mod.load(REPO / "config" / "style.json")
    cover = style_cfg.get("封面规范", {})
    pal = "/".join(cover.get("色板") or ["#FFFFFF", "#1F2937", "#F97316"])
    suffix = cfg.get("style_suffix", DEFAULT_CONFIG["style_suffix"])
    topic = fm.get("title") or fm.get("cover_text") or "今日分享"
    body = (fm.get("body") or "")[:80]
    return (
        f"主题：{topic}。内容要点：{body}。"
        f"风格：{suffix}；色板 {pal}；无文字，竖版 3:4。"
    )


def generate_post_images(day: str, count: int = 1, *, dry_run: bool = False) -> list[Path]:
    """生成该篇配图到 drafts/<day>/img/。未配置 key 时给出明确指引，不产生网络调用。"""
    if not available():
        raise RuntimeError(
            "图像服务未启用。请先提供图像 API key：设置环境变量 XHS_IMAGE_API_KEY，"
            "并把 config/vision.json 的 enabled/provider/model 填好（参考 images.py 头注释）。"
        )
    if dry_run:
        return []
    # TODO(生图接入点)：按 provider 分支调用 REST，保存到 img/note-<n>.png
    # 目前无 key 无法联调，待用户提供后实现并自测。
    raise NotImplementedError("生图接入点：拿到 key 后在此实现（images.py 已留好位置与说明）")
