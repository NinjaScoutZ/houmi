import os
import sys
import shutil
import time
import subprocess
from pathlib import Path

def get_bundled_dir():
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", Path(sys.executable).parent)
        bundled = Path(meipass) / "HoumiDesktop"
        if bundled.exists():
            return bundled
        return Path(meipass)
    return Path(__file__).resolve().parent.parent / "dist" / "HoumiDesktop"

def main():
    print("=" * 65)
    print("      🚀 HOUMI TRANSLATION STUDIO v0.1.4 WINDOWS INSTALLER")
    print("=" * 65)
    print()

    # 1. Target Directory: AppData Local Programs
    local_appdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    install_target = Path(local_appdata) / "Programs" / "HoumiStudio"

    print(f"📍 Target Installation Path:\n   {install_target}\n")

    # 2. Terminate any running instances
    print("🔄 Closing any running instances of Houmi Studio...")
    subprocess.run(["taskkill", "/F", "/IM", "HoumiDesktop.exe"], capture_output=True)
    time.sleep(1.0)

    # 3. Clean old directory to prevent stale _internal bytecode conflicts
    if install_target.exists():
        print(f"🧹 Removing old installation files in {install_target}...")
        try:
            shutil.rmtree(install_target, ignore_errors=True)
            time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Notice during cleanup: {e}")

    install_target.mkdir(parents=True, exist_ok=True)

    # 4. Copy bundled HoumiDesktop files
    bundled_src = get_bundled_dir()
    print(f"📦 Extracting & Installing Houmi Studio v0.1.4 files...")
    
    if not bundled_src.exists():
        print(f"❌ Error: Bundled program files missing at {bundled_src}")
        input("\nPress Enter to exit...")
        sys.exit(1)

    # Copy tree
    for item in bundled_src.iterdir():
        target_path = install_target / item.name
        if item.is_dir():
            if target_path.exists():
                shutil.rmtree(target_path, ignore_errors=True)
            shutil.copytree(item, target_path)
        else:
            shutil.copy2(item, target_path)

    main_exe = install_target / "HoumiDesktop.exe"
    print(f"✅ Program installed successfully: {main_exe}")

    # 5. Create Desktop & Start Menu Shortcuts
    print("🔗 Creating Shortcuts on Desktop and Start Menu...")
    desktop = Path.home() / "Desktop"
    start_menu = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "Microsoft" / "Windows" / "Start Menu" / "Programs"

    desktop_shortcut = desktop / "Houmi Studio.lnk"
    start_shortcut = start_menu / "Houmi Studio.lnk"

    for shortcut in [desktop_shortcut, start_shortcut]:
        try:
            ps_cmd = (
                f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{shortcut}');"
                f"$s.TargetPath='{main_exe}';"
                f"$s.WorkingDirectory='{main_exe.parent}';"
                f"$s.Save()"
            )
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
            print(f"   ✓ {shortcut.name}")
        except Exception as err:
            print(f"   ⚠️ Shortcut notice ({shortcut.name}): {err}")

    print()
    print("🎉 Installation Completed Successfully!")
    print("🚀 Launching Houmi Studio v0.1.4...")
    print("=" * 65)

    if main_exe.exists():
        subprocess.Popen([str(main_exe)], cwd=str(main_exe.parent))
    time.sleep(2)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n❌ Installation error: {exc}")
        input("\nPress Enter to exit...")
