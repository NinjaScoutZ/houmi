import sys
import os
import time
import threading
from pathlib import Path

# Fix pythonnet runtime initialization in PyInstaller frozen mode on Windows
if getattr(sys, "frozen", False):
    _meipass = getattr(sys, "_MEIPASS", Path(sys.executable).parent)
    search_paths = [
        Path(_meipass),
        Path(sys.executable).parent,
        Path(sys.executable).parent / "_internal",
    ]
    for sp in search_paths:
        if sp.exists():
            for pydll in sp.glob("python*.dll"):
                os.environ["PYTHONNET_PYDLL"] = str(pydll)
                break
            if "PYTHONNET_PYDLL" in os.environ:
                break

import uvicorn
if "--headless" not in sys.argv:
    try:
        import webview
    except ImportError:
        pass

# Add backend and workspace directory to python path
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir / "backend"
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(current_dir))

os.environ["HOUMI_APP_DIR"] = str(current_dir)
os.environ["HOUMI_WORKSPACE_DIR"] = str(current_dir)
os.environ["HOUMI_DATA_DIR"] = str(current_dir / "data")
os.environ["HOUMI_FRONTEND_DIST"] = str(current_dir / "frontend" / "dist")
os.environ["HOUMI_DISABLE_AUTO_PATCH"] = "1"

# Set environment variables for FastAPI backend config and force WebView2 GPU acceleration
HOUMI_PORT_VAL = 4000
try:
    import socket
    for p in range(4000, 4100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                HOUMI_PORT_VAL = p
                break
            except OSError:
                continue
except Exception:
    pass

os.environ["HOUMI_HOST"] = "127.0.0.1"
os.environ["HOUMI_PORT"] = str(HOUMI_PORT_VAL)
os.environ["PRODUCTION_MODE"] = "1"
os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
    "--enable-gpu-rasterization "
    "--enable-zero-copy "
    "--ignore-gpu-blocklist "
    "--enable-hardware-overlays "
    "--num-raster-threads=4 "
    "--enable-features=UseDWritePriorities,FontSrcLocalMatching "
    "--disable-http-cache "
    "--disable-cache"
)

class FastAPIThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.server = None

    def run(self):
        # Disable uvicorn reload in production/desktop mode
        port = int(os.environ.get("HOUMI_PORT", "4000"))
        config = uvicorn.Config(
            "app.main:app",
            host="127.0.0.1",
            port=port,
            log_level="info",
            reload=False
        )
        self.server = uvicorn.Server(config)
        self.server.run()

    def shutdown(self):
        if self.server:
            self.server.should_exit = True

class DesktopApi:
    def __init__(self):
        self.is_max = False

    def show_console(self):
        """Pops open a live Windows CMD Console window for real-time log debugging."""
        try:
            import ctypes
            ctypes.windll.kernel32.AllocConsole()
            sys.stdout = open("CONOUT$", "w", encoding="utf-8")
            sys.stderr = open("CONOUT$", "w", encoding="utf-8")
            print("==========================================================================")
            print("  HOUMI STUDIO — REALTIME DEBUG CONSOLE (CMD TERMINAL)")
            print("==========================================================================")
            print("  Live Python / Uvicorn backend log output stream is active.")
            print("==========================================================================")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def start_window_drag(self):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            win = webview.active_window()
            if not win and hasattr(webview, 'windows') and len(webview.windows) > 0:
                win = webview.windows[0]
            hwnd = getattr(win, 'gui_handle', None) if win else None
            if not hwnd:
                hwnd = user32.GetForegroundWindow()
            if hwnd:
                user32.ReleaseCapture()
                user32.SendMessageW(hwnd, 0x00A1, 2, 0)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def minimize_window(self):
        try:
            win = webview.active_window()
            if not win and hasattr(webview, 'windows') and len(webview.windows) > 0:
                win = webview.windows[0]
            if win:
                win.minimize()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def maximize_window(self):
        try:
            win = webview.active_window()
            if not win and hasattr(webview, 'windows') and len(webview.windows) > 0:
                win = webview.windows[0]
            if win:
                if self.is_max:
                    win.restore()
                    self.is_max = False
                else:
                    win.maximize()
                    self.is_max = True
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close_window(self):
        try:
            win = webview.active_window()
            if not win and hasattr(webview, 'windows') and len(webview.windows) > 0:
                win = webview.windows[0]
            if win:
                win.destroy()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_file_b64(self, b64_content: str, filename_suggestion: str, default_directory: str = None):
        try:
            import base64
            active_win = webview.active_window()
            if not active_win:
                if hasattr(webview, 'windows') and len(webview.windows) > 0:
                    active_win = webview.windows[0]

            file_path = None
            if active_win:
                # Determine file filter based on extension
                ext = filename_suggestion.split('.')[-1].lower() if '.' in filename_suggestion else ''
                
                # Build flat tuple of strings according to pywebview format specification
                # Format: "Description (*.ext1;*.ext2)"
                pywebview_types = []
                if ext == 'txt':
                    pywebview_types.append('Text files (*.txt)')
                elif ext == 'psd':
                    pywebview_types.append('PSD files (*.psd)')
                elif ext == 'zip':
                    pywebview_types.append('ZIP archives (*.zip)')
                pywebview_types.append('All Files (*.*)')

                # Show Save File Dialog
                file_path = active_win.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename=filename_suggestion,
                    file_types=tuple(pywebview_types),
                    directory=default_directory or ''
                )
            else:
                # Tkinter Fallback dialog
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes("-topmost", True)
                    
                    tk_types = []
                    ext = filename_suggestion.split('.')[-1].lower() if '.' in filename_suggestion else ''
                    if ext == 'txt':
                        tk_types.append(("Text files", "*.txt"))
                    elif ext == 'psd':
                        tk_types.append(("PSD files", "*.psd"))
                    elif ext == 'zip':
                        tk_types.append(("ZIP archives", "*.zip"))
                    tk_types.append(("All Files", "*.*"))

                    file_path = filedialog.asksaveasfilename(
                        initialfile=filename_suggestion,
                        filetypes=tk_types,
                        defaultextension=f".{ext}" if ext else "",
                        initialdir=default_directory
                    )
                    root.destroy()
                except Exception as tk_err:
                    return {"success": False, "error": f"No active window and Tkinter failed: {tk_err}"}

            if not file_path:
                return {"success": False, "cancelled": True}

            if isinstance(file_path, (list, tuple)):
                if len(file_path) > 0:
                    file_path = file_path[0]
                else:
                    return {"success": False, "cancelled": True}

            # Write decoded binary content to selected path
            data = base64.b64decode(b64_content)
            with open(file_path, 'wb') as f:
                f.write(data)

            return {"success": True, "path": str(file_path)}
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print("ERROR in save_file_b64:\n", tb)
            return {"success": False, "error": f"{e}\nTraceback:\n{tb}"}

    def browse_folder(self, default_directory: str = None):
        try:
            active_win = webview.active_window()
            if not active_win:
                if hasattr(webview, 'windows') and len(webview.windows) > 0:
                    active_win = webview.windows[0]

            folder_path = None
            if active_win:
                folder_path = active_win.create_file_dialog(
                    webview.FOLDER_DIALOG,
                    directory=default_directory or ''
                )
            else:
                # Tkinter Fallback dialog
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                folder_path = filedialog.askdirectory(initialdir=default_directory)
                root.destroy()

            if not folder_path:
                return {"success": False, "cancelled": True}

            if isinstance(folder_path, (list, tuple)):
                if len(folder_path) > 0:
                    folder_path = folder_path[0]
                else:
                    return {"success": False, "cancelled": True}

            return {"success": True, "path": str(folder_path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

def main():
    # Check if started with --debug or --console flag to show CMD terminal
    if any(arg in sys.argv for arg in ["--debug", "--console", "-d"]) or os.environ.get("HOUMI_SHOW_CONSOLE") == "1":
        try:
            import ctypes
            ctypes.windll.kernel32.AllocConsole()
            sys.stdout = open("CONOUT$", "w", encoding="utf-8")
            sys.stderr = open("CONOUT$", "w", encoding="utf-8")
            print("==========================================================================")
            print("  HOUMI STUDIO — REALTIME DEBUG CONSOLE (CMD TERMINAL)")
            print("==========================================================================")
            print("  Live Python / Uvicorn backend log output stream is active.")
            print("==========================================================================")
        except Exception:
            pass

    # Load .env config
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / "backend" / ".env")
    except Exception:
        pass

    # Start Gemini Proxy in background (only if configured to run locally)
    proxy_proc = None
    proxy_url = os.environ.get("GEMINI_PROXY_URL", "http://localhost:3000")
    is_local_proxy = "localhost" in proxy_url or "127.0.0.1" in proxy_url

    if is_local_proxy:
        try:
            bun_exe = r"C:\Users\dansa\.bun\bin\bun.exe"
            proxy_dir = r"C:\Users\dansa\Desktop\gemini-proxy"
            if os.path.exists(bun_exe) and os.path.exists(proxy_dir):
                print("Starting local Gemini Proxy...")
                import subprocess
                proxy_proc = subprocess.Popen(
                    [bun_exe, "start"],
                    cwd=proxy_dir,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        except Exception as e:
            print(f"Failed to auto-start Gemini Proxy: {e}")

    # 1. Start FastAPI server in a background thread
    print("Starting FastAPI background thread...")
    server_thread = FastAPIThread()
    server_thread.start()

    # Poll backend server until HTTP port responds (prevents white-screen race condition)
    port = int(os.environ.get("HOUMI_PORT", "4000"))
    url = f"http://127.0.0.1:{port}/"
    print(f"Waiting for local backend server at {url}...")
    import urllib.request
    server_ready = False
    for _ in range(60):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/system/check-update")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            time.sleep(0.5)
    if not server_ready:
        print("Warning: Backend server did not respond in 30s, opening window anyway...")

    # Check for headless sidecar mode (for Tauri v2 host)
    if "--headless" in sys.argv or os.environ.get("HOUMI_HEADLESS") == "1":
        print("[INFO] Running in headless sidecar mode for Tauri v2 host...")
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass
        server_thread.shutdown()
        if proxy_proc:
            try:
                import psutil
                parent = psutil.Process(proxy_proc.pid)
                for child in parent.children(recursive=True):
                    child.terminate()
                parent.terminate()
            except Exception:
                pass
        sys.exit(0)

    # 3. Create Webview window
    print("Launching Desktop Webview window...")
    try:
        # 2. Start pywebview window pointing to localhost with registered desktop JS API
        api = DesktopApi()
        port = int(os.environ.get("HOUMI_PORT", "4000"))
        webview.create_window(
            title="Houmi Translation Studio",
            url=f"http://127.0.0.1:{port}/?v={int(time.time())}",
            js_api=api,
            width=1280,
            height=800,
            min_size=(1024, 768),
            resizable=True,
            frameless=False,
            easy_drag=False
        )

        # Disable private mode to persist cookies, cache, and LocalStorage settings on exit.
        # Use a dedicated subfolder for WebView2 data to avoid folder-level locks.
        from pathlib import Path
        import shutil

        base_data_path = Path.home() / ".houmi"
        os.makedirs(base_data_path, exist_ok=True)
        app_data_path = base_data_path / "webview_profile"
        os.makedirs(app_data_path, exist_ok=True)

        # Check if the EBWebView lockfile is held by a dead/stale process
        lock_file = app_data_path / "EBWebView" / "lockfile"
        if lock_file.exists():
            try:
                # Try removing stale lock file if process is no longer active
                lock_file.unlink(missing_ok=True)
            except Exception:
                # If locked by an active process, use a unique session path to prevent 0x800700AA white screen
                app_data_path = base_data_path / f"webview_session_{os.getpid()}"
                os.makedirs(app_data_path, exist_ok=True)

        webview.start(private_mode=False, storage_path=str(app_data_path))
        print("Desktop Window closed. Shutting down...")
    except Exception as e:
        # Fallback if WebView2 or display environment is missing (e.g. stripped Windows)
        print(f"\n[WARNING] Webview failed to initialize: {e}")
        print("Falling back to system default web browser...")
        import webbrowser
        port = int(os.environ.get("HOUMI_PORT", "4000"))
        webbrowser.open(f"http://127.0.0.1:{port}/")
        
        print("\nPress Ctrl+C in this console to shut down the application.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")

    # 4. Clean up FastAPI server and Gemini Proxy
    server_thread.shutdown()
    if proxy_proc:
        print("Shutting down Gemini Proxy...")
        try:
            import psutil
            parent = psutil.Process(proxy_proc.pid)
            for child in parent.children(recursive=True):
                child.terminate()
            parent.terminate()
        except Exception:
            pass
    sys.exit(0)

if __name__ == "__main__":
    try:
        from app.services.crash_logger import install_crash_handlers
        install_crash_handlers()
    except Exception as exc:
        print(f"[WARNING] Could not initialize crash logger: {exc}")
    main()
