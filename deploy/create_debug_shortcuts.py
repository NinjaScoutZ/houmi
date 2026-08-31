import os
import subprocess
from pathlib import Path

desktop = Path(os.environ["USERPROFILE"]) / "Desktop"

ps_code = """
$WshShell = New-Object -ComObject WScript.Shell

$s1 = $WshShell.CreateShortcut("{0}")
$s1.TargetPath = "E:\\houmi\\dist\\HoumiStudio\\Start-Houmi-Debug.bat"
$s1.WorkingDirectory = "E:\\houmi\\dist\\HoumiStudio"
$s1.IconLocation = "E:\\houmi\\dist\\HoumiStudio\\HoumiStudio.exe,0"
$s1.Description = "Houmi Studio v2.0.0 Console Debug Mode"
$s1.Save()

$s2 = $WshShell.CreateShortcut("{1}")
$s2.TargetPath = "E:\\houmi\\Start-Dev-CMD.bat"
$s2.WorkingDirectory = "E:\\houmi"
$s2.IconLocation = "E:\\houmi\\dist\\HoumiStudio\\HoumiStudio.exe,0"
$s2.Description = "Houmi Studio Live Developer Mode"
$s2.Save()
""".format(
    str(desktop / "Houmi Studio v2 (Debug Console).lnk"),
    str(desktop / "Houmi Studio (Live Dev Mode).lnk")
)

subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_code], check=True)
print("✓ Successfully created CMD Debug Shortcuts on Desktop!")
