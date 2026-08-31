"""
DOBKLE Cloud Hub Host Launcher
Bootstraps the AI Cloud OCR & Inpainting server on your PC.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def check_host_prerequisites() -> dict:
    """Audit all dependencies, models, and agy CLI on this host machine."""
    results = {
        "agy": False,
        "agy_path": None,
        "gpu": False,
        "gpu_name": "CPU",
        "lama": False,
        "cloudflared": False,
        "cloudflared_path": None,
    }

    # 1. Check AGY CLI
    agy_path = shutil.which("agy")
    if not agy_path:
        default_agy = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
        if default_agy.exists():
            agy_path = str(default_agy)
            os.environ["PATH"] = f"{default_agy.parent};{os.environ.get('PATH', '')}"

    if agy_path:
        results["agy"] = True
        results["agy_path"] = str(agy_path)

    # 2. Check GPU & PyTorch
    try:
        import torch
        if torch.cuda.is_available():
            results["gpu"] = True
            results["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception:
        pass

    # 3. Check LaMa inpainter model
    try:
        from app.services.inpainter import _get_lama
        lama = _get_lama()
        results["lama"] = lama is not None
    except Exception:
        results["lama"] = False

    # 4. Check Cloudflared
    cf_path = shutil.which("cloudflared")
    if not cf_path:
        local_cf = PROJECT_ROOT / "cloudflared.exe"
        if local_cf.exists():
            cf_path = str(local_cf)

    if cf_path:
        results["cloudflared"] = True
        results["cloudflared_path"] = str(cf_path)

    return results


def print_banner(audit: dict, port: int, host: str, tunnel_url: str):
    print("\n" + "=" * 70)
    print("      ☁️  DOBKLE CLOUD AI HUB — HOST SERVER (AGY & INPAINT)  ☁️")
    print("=" * 70)
    print(f"📡 Local Binding   : http://{host}:{port}")
    print(f"🌐 Public Domain   : {tunnel_url}")
    print("-" * 70)
    
    agy_status = f"🟢 READY ({audit['agy_path']})" if audit["agy"] else "🔴 NOT FOUND (Install agy CLI)"
    gpu_status = f"🟢 {audit['gpu_name']}" if audit["gpu"] else "⚪ CPU Mode"
    lama_status = "🟢 READY" if audit["lama"] else "🟡 Fallback to Telea"
    cf_status = f"🟢 READY ({audit['cloudflared_path']})" if audit["cloudflared"] else "⚪ Manual Tunnel / Local Only"

    print(f"  [AI Engine]  AGY Gemini VLM OCR : {agy_status}")
    print(f"  [Hardware]   GPU Acceleration   : {gpu_status}")
    print(f"  [Inpainter]  LaMa Cleaner Engine: {lama_status}")
    print(f"  [Gateway]    Cloudflare Tunnel  : {cf_status}")
    print("=" * 70)
    print("🚀 Server is active. Clients can connect and send OCR / Clean jobs.\n")


def main():
    parser = argparse.ArgumentParser(description="Start DOBKLE Cloud AI Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=4000, help="Port to bind")
    parser.add_argument("--tunnel", action="store_true", help="Start Cloudflare Tunnel daemon")
    parser.add_argument("--dry-run", action="store_true", help="Perform pre-flight checks and exit")
    args = parser.parse_args()

    audit = check_host_prerequisites()
    tunnel_url = os.environ.get("HOUMI_CENTRAL_URL", "https://houmi.click")

    print_banner(audit, args.port, args.host, tunnel_url)

    if args.dry_run:
        print("✅ Pre-flight dry run checks passed successfully.")
        return 0

    # Start Cloudflare Tunnel if requested
    tunnel_process = None
    if args.tunnel and audit["cloudflared_path"]:
        config_file = PROJECT_ROOT / "cloudflared-local.yml"
        if not config_file.exists():
            config_file = PROJECT_ROOT / "cloudflared-config.yml"
        if config_file.exists():
            print(f"🚇 Spawning Cloudflare Tunnel with config: {config_file}")
            tunnel_cmd = [audit["cloudflared_path"], "tunnel", "--config", str(config_file), "run"]
            tunnel_process = subprocess.Popen(tunnel_cmd)

    try:
        import uvicorn
        os.environ["HOUMI_RUNTIME_MODE"] = "host"
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down DOBKLE Cloud Hub Server...")
    finally:
        if tunnel_process:
            tunnel_process.terminate()

    return 0


if __name__ == "__main__":
    sys.exit(main())
