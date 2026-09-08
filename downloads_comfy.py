"""可断点续传下载器（python requests，Range 续传 + 进度条）。

用法：
  python downloads_comfy.py comfy        # 只下 ComfyUI 便携包 (~2GB)
  python downloads_comfy.py models       # 下 SDXL+IPAdapter 模型 (~12GB)
  python downloads_comfy.py all
环境变量 HUB 可切换镜像：默认官方 huggingface.co；国内可设 set HUB=hf-mirror.com
"""
import os
import sys
import time
from pathlib import Path

import requests

HUB = os.environ.get("HUB", "huggingface.co")
ROOT = Path(__file__).resolve().parent / "comfyui"
STAGE = ROOT / "downloads"
STAGE.mkdir(parents=True, exist_ok=True)

COMFY_URL = "https://github.com/Comfy-Org/ComfyUI/releases/download/v0.34.0/ComfyUI_windows_portable_nvidia_cu126.7z"

MODELS = [
    ("checkpoints", "sd_xl_base_1.0.safetensors",
     f"https://{HUB}/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors", 6938078334),
    ("clip_vision", "model.safetensors",
     f"https://{HUB}/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors", 3689912664),
    ("ipadapter", "ip-adapter-plus_sdxl_vit-h.safetensors",
     f"https://{HUB}/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors", 847517512),
    ("ipadapter", "ip-adapter_sdxl_vit-h.safetensors",
     f"https://{HUB}/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl_vit-h.safetensors", 698391064),
]


_CDN_CACHE: dict[str, str] = {}


def _resolve(url: str) -> str:
    """跟一次 302 拿到 CDN 直链（之后稳定续传，不再反复走重定向）。"""
    if url in _CDN_CACHE:
        return _CDN_CACHE[url]
    try:
        r = requests.head(url, timeout=30, allow_redirects=False)
        loc = r.headers.get("location")
        if loc and loc.startswith("http"):
            _CDN_CACHE[url] = loc
            return loc
    except requests.exceptions.RequestException:
        pass
    return url


def fetch(name: str, url: str, dest: Path, expected: int, hub: str, max_tries: int = 60) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    direct = _resolve(url)
    for attempt in range(1, max_tries + 1):
        cur = dest.stat().st_size if dest.exists() else 0
        if cur >= expected * 0.99:
            print(f"[完成] {name}: {cur}", flush=True)
            return
        start = cur
        headers = {"Range": f"bytes={start}-"} if start else {}
        t0 = time.time()
        try:
            with requests.get(direct, stream=True, timeout=90, headers=headers) as r:
                r.raise_for_status()
                if start and r.status_code != 206:
                    start = 0
                    dest.unlink(missing_ok=True)
                with open(dest, "ab" if start else "wb") as f:
                    for chunk in r.iter_content(chunk_size=4 * 1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            done = dest.stat().st_size
                            if done % (512 * 1024 * 1024) < 4 * 1024 * 1024:
                                el = time.time() - t0
                                print(f"  {name}: {done/1e9:.2f}/{expected/1e9:.2f} GB  {done/1e6/el:.1f} MB/s", flush=True)
            print(f"[完成] {name}: {dest.stat().st_size}", flush=True)
            return
        except requests.exceptions.RequestException as e:
            got = dest.stat().st_size if dest.exists() else 0
            print(f"[第{attempt}次中断 @{got/1e9:.2f}GB] {name}: {str(e)[:80]} —— 3秒后续传", flush=True)
            time.sleep(3)
    got = dest.stat().st_size if dest.exists() else 0
    print(f"[仍不完整] {name}: {got}（期望 {expected}），可再重跑脚本续传", flush=True)
    raise SystemExit(4)


def main() -> None:
    job = sys.argv[1] if len(sys.argv) > 1 else "all"
    if job in ("comfy", "all"):
        print(f"下载 ComfyUI …（{COMFY_URL}）", flush=True)
        fetch("comfyui.7z", COMFY_URL, STAGE / "comfyui.7z", 2097152000, HUB)  # ~2GB，完成后校验
    if job in ("models", "all"):
        for sub, name, url, size in MODELS:
            rel = Path(sub) / name
            print(f"下载 {rel} …", flush=True)
            fetch(name, url, ROOT / "models-staging" / rel, size, HUB)
    print("全部完成。下一步：解压 ComfyUI 并把 models-staging 移入 ComfyUI/models。", flush=True)

if __name__ == "__main__":
    main()
