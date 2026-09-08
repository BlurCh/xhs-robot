"""豆包（火山方舟 Seedream）文生图客户端。

配置（任选其一）：
  1) 环境变量 ARK_API_KEY=<你的 key>
  2) 文件 config/doubao.json: {"api_key": "...", "model": "doubao-seedream-...", "base": "https://ark.cn-beijing.volces.com/api/v3"}

用法：
  python doubao_gen.py "画面描述" out.png [--size 768x1024] [--seed 42]

说明：
- API 为 OpenAI images 兼容（POST {base}/images/generations）。
- 模型 id 以你在方舟「模型广场」开通/使用的为准（如 doubao-seedream-4-0-250828 一类），
  填错会报错并提示，改 config 或换模型 id 即可。
- 角色参考图参数待确认后接入（保持猪猪/虎虎跨画面一致）。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent
CONFIG = REPO / "config" / "doubao.json"
DEFAULT_BASE = "https://ark.cn-beijing.volces.com/api/v3"


def load_config() -> dict:
    cfg = {}
    if CONFIG.exists():
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cfg = {}
    key = os.environ.get("ARK_API_KEY", "") or cfg.get("api_key", "")
    if not key:
        raise SystemExit(
            "缺少豆包 API key。两种方式：\n"
            "  1) set ARK_API_KEY=你的key\n"
            "  2) 编辑 config/doubao.json 填入 api_key（推荐，key 不进对话/代码库）"
        )
    model = cfg.get("model") or os.environ.get("ARK_MODEL", "")
    if not model:
        raise SystemExit("缺少模型 id：请在 config/doubao.json 填 model（方舟模型广场里你开通的 doubao-seedream 模型 id）")
    return {"api_key": key, "model": model, "base": cfg.get("base", DEFAULT_BASE)}


def generate(prompt: str, out: str | Path, size: str = "768x1024", seed: int | None = None,
             model_hint: str | None = None) -> Path:
    cfg = load_config()
    if model_hint:
        cfg["model"] = model_hint
    w, h = (int(x) for x in size.lower().split("x"))
    payload: dict = {
        "model": cfg["model"],
        "prompt": prompt,
        "size": f"{w}x{h}",
        "response_format": "b64_json",
    }
    if seed is not None:
        payload["seed"] = seed
    r = requests.post(
        f"{cfg['base']}/images/generations",
        json=payload,
        headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f"豆包 API {r.status_code}: {r.text[:500]}")
    data = r.json()["data"][0]
    img_bytes = base64.b64decode(data["b64_json"]) if data.get("b64_json") else requests.get(data["url"]).content
    dest = Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(img_bytes)
    print(f"已保存 {dest}")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("out")
    ap.add_argument("--size", default="768x1024")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--model", default=None, help="临时指定模型 id")
    a = ap.parse_args()
    generate(a.prompt, a.out, a.size, a.seed, a.model)


if __name__ == "__main__":
    main()
