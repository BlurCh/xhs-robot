"""网络与 Astrill VPN 状态助手（保守策略：默认只探测、不擅自动你的网络）。

背景：本机用 Astrill VPN，开全局时国内站点（含小红书）不可达。
- env net：报告当前 国内/国外 可达性，推断 VPN 是否在拦截国内流量；
- env vpn off：尝试断开 VPN（停止 ASOvpnSvc 服务，需 --apply 才真正执行）；
- env vpn on：尽力恢复（启动服务并拉起 astrill.exe；注意：重连选档与凭据需你在
  Astrill 窗口完成——自动"连接"不可靠，本助手不假装能做）。

安全原则：执行前打印将执行的精确动作；默认只输出建议；绝不静默断你的网。
"""
from __future__ import annotations

import os
import socket
import ssl
import subprocess
from pathlib import Path

PROGRAMFILES_X86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
ASTRILL_EXE = PROGRAMFILES_X86 / "Astrill" / "astrill.exe"
SVC = "ASOvpnSvc"


def _reachable(host: str, port: int = 443, timeout: float = 6.0) -> bool:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as s:
            with ctx.wrap_socket(s, server_hostname=host):
                return True
    except Exception:  # noqa: BLE001
        return False


def net_state() -> dict[str, bool]:
    """国内/国外可达性（国内用小红书创作者中心，国外用 example.com）。"""
    return {"cn": _reachable("creator.xiaohongshu.com"), "intl": _reachable("example.com")}


def vpn_process_state() -> str:
    out = subprocess.run(
        ["sc", "query", SVC], capture_output=True, text=True, timeout=15
    ).stdout
    if "RUNNING" in out:
        return "running"
    if "STOPPED" in out:
        return "stopped"
    return "unknown"


def plan(apply: bool = False) -> dict:
    st = net_state()
    svc = vpn_process_state()
    msg = (
        f"国内可达={st['cn']} 国外可达={st['intl']} | ASOvpnSvc={svc}\n"
        "解读："
        + ("当前能访问小红书 ✅" if st["cn"] else "当前小红书不可达 ⚠️（若你开着全局 VPN，需先断开）")
        + "；" + ("当前能访问外网 ✅" if st["intl"] else "当前外网不可达（若需外网请开 Astrill）")
    )
    print(msg)
    if apply:
        _toggle_vpn("off" if st["cn"] is False else "noop")
    return {"cn": st["cn"], "intl": st["intl"], "svc": svc}


def _toggle_vpn(mode: str) -> None:
    if mode == "off":
        print(f"将停止服务 {SVC}（断开 OpenVPN 通道）…")
        subprocess.run(["sc", "stop", SVC], capture_output=True, text=True, timeout=30)
        print("已请求断开。若 Astrill 另有连接方式，请在托盘确认。")
    elif mode == "noop":
        print("无需动作。")
