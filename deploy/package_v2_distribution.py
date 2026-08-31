import os
import shutil
from pathlib import Path
import subprocess

root = Path(r"E:\houmi")
dist_dir = root / "dist" / "HoumiStudio"
dist_dir.mkdir(parents=True, exist_ok=True)
binaries_dir = dist_dir / "binaries"
binaries_dir.mkdir(parents=True, exist_ok=True)

# 1. Copy Tauri Release App
src_exe = root / "frontend" / "src-tauri" / "target" / "release" / "houmi-studio.exe"
dst_exe = dist_dir / "HoumiStudio.exe"
shutil.copy2(src_exe, dst_exe)
print("✓ Copied HoumiStudio.exe (14 MB)")

# 2. Copy Sidecar Binary (both root and binaries/ subfolder)
src_sidecar = root / "frontend" / "src-tauri" / "binaries" / "houmi-local-x86_64-pc-windows-msvc.exe"
shutil.copy2(src_sidecar, dist_dir / "houmi-local-x86_64-pc-windows-msvc.exe")
shutil.copy2(src_sidecar, dist_dir / "houmi-local.exe")
shutil.copy2(src_sidecar, binaries_dir / "houmi-local-x86_64-pc-windows-msvc.exe")
shutil.copy2(src_sidecar, binaries_dir / "houmi-local.exe")
print("✓ Copied houmi-local sidecar binaries")

# 3. Create Desktop shortcut pointing to dist/HoumiStudio/HoumiStudio.exe
desktop_shortcut = Path(os.environ["USERPROFILE"]) / "Desktop" / "Houmi Studio v2.lnk"
ps_shortcut = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{desktop_shortcut}")
$Shortcut.TargetPath = "{dst_exe}"
$Shortcut.WorkingDirectory = "{dist_dir}"
$Shortcut.IconLocation = "{dst_exe},0"
$Shortcut.Description = "Houmi Studio v2.0.0 Native Desktop App"
$Shortcut.Save()
'''
subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_shortcut], check=True)
print("✓ Created Desktop Shortcut:", desktop_shortcut)
