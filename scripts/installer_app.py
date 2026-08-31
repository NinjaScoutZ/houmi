import os
import sys
import shutil
import zipfile
import subprocess
import time
from pathlib import Path

def install():
    print("=" * 60)
    print("  Houmi Translation Studio v0.1.4 Automatic Windows Installer")
    print("=" * 60)

    # 1. Determine installation directory (AppData Local Programs)
    user_appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    install_dir = user_appdata / "Programs" / "HoumiStudio"
    
    print(f"\n📍 Target Install Path: {install_dir}")

    # 2. Kill running processes if open
    print("🔄 Checking for active HoumiStudio processes...")
    subprocess.run(["taskkill", "/F", "/IM", "HoumiDesktop.exe"], capture_output=True)
    time.sleep(1)

    # 3. Locate zip file
    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    zip_path = base_dir / "HoumiDesktop-dist.zip"
    
    if not zip_path.exists():
        zip_path = base_dir.parent / "HoumiDesktop-dist.zip"

    if not zip_path.exists():
        print(f"❌ Error: Cannot find HoumiDesktop-dist.zip in {base_dir}")
        input("Press Enter to exit...")
        sys.exit(1)

    # 4. Extracting clean installation
    print(f"📦 Extracting package ({round(zip_path.stat().st_size / (1024*1024), 2)} MB) to {install_dir}...")
    install_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(install_dir.parent)

    exe_path = install_dir / "HoumiDesktop.exe"
    if not exe_path.exists():
        exe_path = install_dir / "HoumiDesktop" / "HoumiDesktop.exe"

    print(f"✅ Executable installed at: {exe_path}")

    # 5. Create Desktop and Start Menu shortcuts
    desktop_dir = Path.home() / "Desktop"
    start_menu_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"

    desktop_lnk = desktop_dir / "Houmi Studio.lnk"
    start_menu_lnk = start_menu_dir / "Houmi Studio.lnk"

    print("🔗 Creating Windows Desktop & Start Menu Shortcuts...")
    for lnk in [desktop_lnk, start_menu_lnk]:
        try:
            ps_cmd = (
                f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{lnk}');"
                f"$s.TargetPath='{exe_path}';"
                f"$s.WorkingDirectory='{exe_path.parent}';"
                f"$s.Save()"
            )
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
            print(f"   Created: {lnk}")
        except Exception as e:
            print(f"   Shortcut warning: {e}")

    print("\n🎉 Installation Complete!")
    print("🚀 Launching Houmi Studio v0.1.4...")
    subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))
    time.sleep(2)

if __name__ == "__main__":
    try:
        install()
    except Exception as err:
        print(f"\n❌ Installation failed: {err}")
        input("Press Enter to exit...")
