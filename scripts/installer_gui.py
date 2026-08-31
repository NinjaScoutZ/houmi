import os
import sys
import shutil
import time
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

def get_bundled_dir():
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", Path(sys.executable).parent)
        bundled = Path(meipass) / "HoumiDesktop"
        if bundled.exists():
            return bundled
        return Path(meipass)
    return Path(__file__).resolve().parent.parent / "dist" / "HoumiDesktop"

class InstallerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Houmi Studio v0.1.4 Setup")
        self.root.geometry("540x320")
        self.root.resizable(False, False)
        self.root.configure(bg="#09090b")

        # Center window on screen
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Set dark theme styles
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#18181b",
            background="#f59e0b",
            thickness=14,
            bordercolor="#27272a",
            lightcolor="#f59e0b",
            darkcolor="#d97706"
        )

        # Header Frame
        header_frame = tk.Frame(root, bg="#09090b", pady=15, padx=20)
        header_frame.pack(fill="x")

        title_label = tk.Label(
            header_frame,
            text="Houmi Translation Studio v0.1.4",
            font=("Segoe UI", 16, "bold"),
            fg="#f4f4f5",
            bg="#09090b"
        )
        title_label.pack(anchor="w")

        subtitle_label = tk.Label(
            header_frame,
            text="Automatic Windows Desktop Setup & File Maintenance",
            font=("Segoe UI", 9),
            fg="#a1a1aa",
            bg="#09090b"
        )
        subtitle_label.pack(anchor="w", pady=(2, 0))

        # Main Content Frame
        content_frame = tk.Frame(root, bg="#18181b", padx=20, pady=15, highlightbackground="#27272a", highlightthickness=1)
        content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        self.status_label = tk.Label(
            content_frame,
            text="พร้อมเริ่มการติดตั้งโปรแกรม...",
            font=("Segoe UI", 10, "bold"),
            fg="#fbbf24",
            bg="#18181b",
            anchor="w"
        )
        self.status_label.pack(fill="x", pady=(5, 5))

        self.detail_label = tk.Label(
            content_frame,
            text="กำลังเตรียมระบบตรวจสอบโฟลเดอร์ปลายทาง...",
            font=("Segoe UI", 8),
            fg="#71717a",
            bg="#18181b",
            anchor="w"
        )
        self.detail_label.pack(fill="x", pady=(0, 12))

        self.progress = ttk.Progressbar(
            content_frame,
            style="Custom.Horizontal.TProgressbar",
            orient="horizontal",
            mode="determinate"
        )
        self.progress.pack(fill="x", pady=(0, 10))

        self.percent_label = tk.Label(
            content_frame,
            text="0%",
            font=("Segoe UI", 9, "bold"),
            fg="#a1a1aa",
            bg="#18181b"
        )
        self.percent_label.pack(anchor="e")

        # Action Buttons Frame
        self.btn_frame = tk.Frame(root, bg="#09090b", padx=20, pady=10)
        self.btn_frame.pack(fill="x", side="bottom")

        self.launch_btn = tk.Button(
            self.btn_frame,
            text="🚀 เปิดโปรแกรม Houmi Studio",
            font=("Segoe UI", 10, "bold"),
            fg="#ffffff",
            bg="#d97706",
            activebackground="#b45309",
            activeforeground="#ffffff",
            bd=0,
            padx=15,
            pady=6,
            cursor="hand2",
            state="disabled",
            command=self.launch_app
        )
        self.launch_btn.pack(side="right")

        self.close_btn = tk.Button(
            self.btn_frame,
            text="ปิดหน้าต่าง",
            font=("Segoe UI", 9),
            fg="#a1a1aa",
            bg="#27272a",
            activebackground="#3f3f46",
            activeforeground="#ffffff",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.root.destroy
        )
        self.close_btn.pack(side="right", padx=(0, 10))

        # Start Installation Worker Thread
        self.installed_exe_path = None
        threading.Thread(target=self.run_installation, daemon=True).start()

    def update_status(self, text, detail="", percent=0):
        def _update():
            self.status_label.config(text=text)
            if detail:
                self.detail_label.config(text=detail)
            self.progress["value"] = percent
            self.percent_label.config(text=f"{int(percent)}%")
        self.root.after(0, _update)

    def run_installation(self):
        try:
            # 1. Target directory
            local_appdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            install_target = Path(local_appdata) / "Programs" / "HoumiStudio"

            self.update_status("กำลังปิดกระบวนการทำงานเก่า...", f"ตำแหน่งเป้าหมาย: {install_target}", 5)
            subprocess.run(["taskkill", "/F", "/IM", "HoumiDesktop.exe"], capture_output=True)
            time.sleep(1.0)

            # 2. Clean old installation files
            if install_target.exists():
                self.update_status("กำลังล้างไฟล์เก่าในเครื่อง...", "ล้างโฟลเดอร์ AppData/Local/Programs/HoumiStudio", 15)
                try:
                    shutil.rmtree(install_target, ignore_errors=True)
                    time.sleep(0.5)
                except Exception as e:
                    print(f"Cleanup notice: {e}")

            install_target.mkdir(parents=True, exist_ok=True)

            # 3. Copy bundled files
            bundled_src = get_bundled_dir()
            if not bundled_src.exists():
                self.update_status("❌ เกิดข้อผิดพลาด", f"ไม่พบไฟล์ต้นทางที่ {bundled_src}", 0)
                return

            all_files = [p for p in bundled_src.rglob("*") if p.is_file()]
            total_files = max(1, len(all_files))

            self.update_status("กำลังคัดลอกไฟล์โปรแกรม Houmi Studio v0.1.4...", "คัดลอกไฟล์ไบนารีและไดนามิกไลบรารี...", 25)

            for idx, file_path in enumerate(all_files, start=1):
                rel_path = file_path.relative_to(bundled_src)
                target_file = install_target / rel_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target_file)

                # Update progress
                if idx % 100 == 0 or idx == total_files:
                    pct = 25 + (idx / total_files) * 60
                    self.update_status(
                        "กำลังคัดลอกไฟล์โปรแกรม Houmi Studio v0.1.4...",
                        f"คัดลอกไฟล์แล้ว {idx}/{total_files} ไฟล์ ({rel_path.name})",
                        pct
                    )

            exe_path = install_target / "HoumiDesktop.exe"
            self.installed_exe_path = exe_path

            # 4. Create Desktop & Start Menu Shortcuts
            self.update_status("กำลังสร้างทางลัดบน Desktop และ Start Menu...", "สร้างไฟล์ทางลัด Houmi Studio.lnk", 90)
            desktop = Path.home() / "Desktop"
            start_menu = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "Microsoft" / "Windows" / "Start Menu" / "Programs"

            desktop_lnk = desktop / "Houmi Studio.lnk"
            start_shortcut = start_menu / "Houmi Studio.lnk"

            for shortcut in [desktop_lnk, start_shortcut]:
                try:
                    ps_cmd = (
                        f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{shortcut}');"
                        f"$s.TargetPath='{exe_path}';"
                        f"$s.WorkingDirectory='{exe_path.parent}';"
                        f"$s.Save()"
                    )
                    subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
                except Exception as e:
                    print(f"Shortcut notice: {e}")

            # 5. Complete
            self.update_status("🎉 การติดตั้งเสร็จสมบูรณ์ 100%!", "สามารถกดปุ่มเพื่อเปิดใช้งานโปรแกรม Houmi Studio ได้ทันที", 100)
            
            def _enable_btn():
                self.launch_btn.config(state="normal")
            self.root.after(0, _enable_btn)

        except Exception as exc:
            self.update_status("❌ ติดตั้งไม่สำเร็จ", str(exc), 0)

    def launch_app(self):
        if self.installed_exe_path and self.installed_exe_path.exists():
            subprocess.Popen([str(self.installed_exe_path)], cwd=str(self.installed_exe_path.parent))
        self.root.destroy()

def main():
    root = tk.Tk()
    app = InstallerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
