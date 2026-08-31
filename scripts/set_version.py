import re
import json
import sys
from pathlib import Path

def set_version(new_ver: str):
    root = Path(__file__).resolve().parent.parent
    
    # 1. Update frontend/package.json
    pkg_json = root / "frontend" / "package.json"
    if pkg_json.exists():
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
        data["version"] = new_ver
        pkg_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"✅ Updated frontend/package.json -> v{new_ver}")

    # 2. Update frontend/package-lock.json if present
    pkg_lock = root / "frontend" / "package-lock.json"
    if pkg_lock.exists():
        data = json.loads(pkg_lock.read_text(encoding="utf-8"))
        data["version"] = new_ver
        if "packages" in data and "" in data["packages"]:
            data["packages"][""]["version"] = new_ver
        pkg_lock.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"✅ Updated frontend/package-lock.json -> v{new_ver}")

    # 3. Update backend/app/routes/updater.py
    updater_py = root / "backend" / "app" / "routes" / "updater.py"
    if updater_py.exists():
        txt = updater_py.read_text(encoding="utf-8")
        txt = re.sub(r'CURRENT_VERSION\s*=\s*"[^"]+"', f'CURRENT_VERSION = "{new_ver}"', txt)
        updater_py.write_text(txt, encoding="utf-8")
        print(f"✅ Updated backend/app/routes/updater.py -> v{new_ver}")

    # 4. Update HoumiInstaller.iss
    iss_path = root / "HoumiInstaller.iss"
    if iss_path.exists():
        txt = iss_path.read_text(encoding="utf-8")
        txt = re.sub(r'#define MyAppVersion\s+"[^"]+"', f'#define MyAppVersion "{new_ver}"', txt)
        iss_path.write_text(txt, encoding="utf-8")
        print(f"✅ Updated HoumiInstaller.iss -> v{new_ver}")

    # 5. Update data/update_manifest.json
    manifest = root / "data" / "update_manifest.json"
    manifest_data = {
        "version": new_ver,
        "latest_version": new_ver,
        "download_url": "/api/system/download-update",
        "download_size_mb": 204.46,
        "patch_notes": f"v{new_ver} Auto-Patch, RapidOCR ONNX, Project Preset & Cloudflare Fix"
    }
    manifest.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
    print(f"✅ Updated data/update_manifest.json -> v{new_ver}")

    print(f"\n=========================================")
    print(f"🎉 Houmi Studio Software Version synchronized to v{new_ver} across all configuration files!")
    print(f"=========================================\n")

if __name__ == "__main__":
    ver = sys.argv[1] if len(sys.argv) > 1 else "0.1.5"
    set_version(ver)
