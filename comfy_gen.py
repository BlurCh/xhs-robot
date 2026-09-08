"""ComfyUI 本地生图客户端：SDXL + IPAdapter（多张角色参考图）+ 竖版3:4。

用法：python comfy_gen.py "<正向提示词>" <输出文件名>
参考图默认取 ComfyUI input/ 下 comic-refs 系列（可 --refs 指定多个）。
依赖：ComfyUI 服务已在 127.0.0.1:8188 运行；SDXL 基底已放入 models/checkpoints。
"""
from __future__ import annotations

import argparse
import http.client
import json
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent
COMFY = REPO / "comfyui" / "ComfyUI_windows_portable" / "ComfyUI"
INPUT_DIR = COMFY / "input"
OUT_DIR = COMFY / "output"
HOST, PORT = "127.0.0.1", 8188

NEGATIVE = ("text, 文字, 字, words, letters, symbols, 符号, 对话框, speech bubble, frame, 分格, 漫画边框, border, "
            "panel, watermark, logo, sticker, 贴纸, cutout, white box, 白色方块, plain white background, "
            "blurry, low quality, worst quality, deformed, 变形, extra limbs, bad anatomy, 歪鼻子")
SIZE = (768, 1024)  # 3:4


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 120) -> dict:
    conn = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    try:
        if body is not None:
            conn.request(method, path, json.dumps(body), {"Content-Type": "application/json"})
        else:
            conn.request(method, path)
        resp = conn.getresponse()
        data = resp.read()
        return json.loads(data.decode("utf-8"))
    finally:
        conn.close()


def build_graph(positive: str, refs: list[str], seed: int, negative: str = NEGATIVE) -> dict:
    g: dict = {}
    n = [0]

    def add(class_type: str, inputs: dict) -> str:
        n[0] += 1
        i = str(n[0])
        g[i] = {"class_type": class_type, "inputs": inputs}
        return i

    ckpt = add("CheckpointLoaderSimple", {"ckpt_name": "sd_xl_base_1.0.safetensors"})
    pos = add("CLIPTextEncode", {"text": positive, "clip": [ckpt, 1]})
    neg = add("CLIPTextEncode", {"text": negative, "clip": [ckpt, 1]})
    latent = add("EmptyLatentImage", {"width": SIZE[0], "height": SIZE[1], "batch_size": 1})

    cur_model = [ckpt, 0]
    if refs:
        # 角色参考：统一加载器后，对每张参考图依次应用 IPAdapter（链式）
        loader = add("IPAdapterUnifiedLoader", {"model": [ckpt, 0], "preset": "PLUS (high strength)"})
        cur_model = [loader, 0]
        for idx, ref in enumerate(refs):
            img = add("LoadImage", {"image": ref})
            w = 0.7 if idx == 0 else 0.55
            nxt = add("IPAdapter", {
                "model": cur_model, "ipadapter": [loader, 1], "image": [img, 0],
                "weight": w, "start_at": 0.0, "end_at": 1.0, "weight_type": "standard",
            })
            cur_model = [nxt, 0]

    sample = add("KSampler", {
        "model": cur_model, "positive": [pos, 0], "negative": [neg, 0],
        "latent_image": [latent, 0], "seed": seed, "steps": 28, "cfg": 6.5,
        "sampler_name": "euler_ancestral", "scheduler": "karras", "denoise": 1.0,
    })
    decoded = add("VAEDecode", {"samples": [sample, 0], "vae": [ckpt, 2]})
    add("SaveImage", {"images": [decoded, 0], "filename_prefix": "comfy_gen"})
    return g


def generate(positive: str, out_name: str, refs: list[str] | None = None, seed: int | None = None) -> Path:
    refs = refs or ["img-01.jpg", "img-02.jpg"]
    # 确保参考图在 input/ 里
    for r in refs:
        src = Path(r)
        if not src.exists():
            cand = INPUT_DIR / r
            if not cand.exists():
                raise FileNotFoundError(f"参考图缺失: {r}")
    graph = build_graph(positive, refs, seed if seed is not None else uuid.uuid4().int % (2**31))
    client_id = str(uuid.uuid4())
    prompt_id = http_json("POST", "/prompt", {"prompt": graph, "client_id": client_id})["prompt_id"]

    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        hist = http_json("GET", f"/history/{prompt_id}")
        if prompt_id in hist:
            outputs = hist[prompt_id].get("outputs", {})
            for oid, o in outputs.items():
                for img in o.get("images", []):
                    fname = img["filename"]
                    src = OUT_DIR / fname
                    if src.exists():
                        dest = REPO / "gen" / out_name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(src.read_bytes())
                        print(f"已保存 {dest}")
                        return dest
            raise RuntimeError("无输出图片：" + json.dumps(hist[prompt_id].get("status"))[:300])
        time.sleep(3)
    raise TimeoutError("生成超时")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("positive")
    ap.add_argument("out")
    ap.add_argument("--refs", nargs="*", default=["img-01.jpg", "img-02.jpg"])
    ap.add_argument("--no-refs", action="store_true", help="纯文生图（不带角色参考）")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    refs = [] if a.no_refs else a.refs
    print(generate(a.positive, a.out, refs, a.seed))


if __name__ == "__main__":
    main()
