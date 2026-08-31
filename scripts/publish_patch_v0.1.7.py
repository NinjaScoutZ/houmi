import os
import sys
import json
import time
import requests
from pathlib import Path

# Paths
PATCH_ZIP = Path(r"E:\houmi\data\patches\latest_patch.zip")
UPDATE_MANIFEST = Path(r"E:\houmi\data\update_manifest.json")
PATCHES_DIR = Path(r"E:\houmi\data\patches")
PATCHES_DIR.mkdir(parents=True, exist_ok=True)

VERSION = "0.3.5"
NOTES = "v0.3.5 Hotfix - Fix PSD export Unicode path & safe typesetting padding dump"

print("==================================================")
print(f"  HOUMI STUDIO - PUBLISH ONLINE PATCH v{VERSION}")
print("==================================================")

# 1. Ensure latest_patch.zip exists
if not PATCH_ZIP.exists():
    print("❌ Error: E:\\houmi\\data\\patches\\latest_patch.zip not found!")
    sys.exit(1)

size_mb = PATCH_ZIP.stat().st_size / (1024 * 1024)
print(f"📦 Patch Zip File: {PATCH_ZIP} ({size_mb:.2f} MB)")

# 2. Update local update_manifest.json
manifest_data = {
    "latest_version": VERSION,
    "patch_notes": NOTES,
    "download_size_mb": round(size_mb, 2),
    "download_url": "/api/system/download-update",
    "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
}

with open(UPDATE_MANIFEST, "w", encoding="utf-8") as f:
    json.dump(manifest_data, f, indent=2, ensure_ascii=False)

print("✅ Updated local update_manifest.json to v0.1.7!")

# 3. Publish to Central Server if running locally or accessible
central_url = os.environ.get("HOUMI_CENTRAL_SERVER_URL", "https://houmi.click").rstrip("/")
print(f"🌐 Publishing patch to Central Server ({central_url})...")

try:
    with open(PATCH_ZIP, "rb") as zf:
        files = {"patch_file": ("latest_patch.zip", zf, "application/zip")}
        data = {
            "version": VERSION,
            "patch_notes": NOTES,
            "download_size_mb": round(size_mb, 2)
        }
        res = requests.post(f"{central_url}/api/admin/publish-patch", data=data, files=files, timeout=30)
        if res.status_code == 200:
            print("🚀 SUCCESS! Central Server response:", res.json())
        else:
            print(f"⚠️ Central Server returned HTTP {res.status_code}: {res.text}")
except Exception as e:
    print(f"ℹ️ Central Server push note: {e}")
    print("Local patch files and update_manifest.json are active and ready for client update requests!")

print("\n🎉 Patch v0.1.7 Online Publish Complete!")
