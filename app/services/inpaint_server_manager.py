import os
import time
import subprocess
import socket
import logging
import threading
from pathlib import Path

logger = logging.getLogger("houmi-inpaint-manager")

DEFAULT_INPAINT_PORT = int(os.environ.get("INPAINT_PORT", "2328"))
DEFAULT_INPAINT_HOST = os.environ.get("INPAINT_HOST", "127.0.0.1")


def _find_best_python_exe(search_dir: Path) -> str:
    """Find the best Python executable with backend dependencies."""
    import sys
    for v in [search_dir / "venv", search_dir / ".venv", search_dir.parent / ".venv", search_dir.parent / "venv"]:
        py = v / "Scripts" / "python.exe"
        if py.exists():
            return str(py)
        py_unix = v / "bin" / "python"
        if py_unix.exists():
            return str(py_unix)
    if sys.executable and Path(sys.executable).exists():
        return str(sys.executable)
    return "python"


class InpaintServerManager:
    """Manages the background GPU Inpaint Server daemon."""
    def __init__(self):
        self.process = None
        self.port = DEFAULT_INPAINT_PORT
        self.host = DEFAULT_INPAINT_HOST
        self._start_thread = None
        self._is_starting = False

    def is_port_active(self, port: int | None = None) -> bool:
        p = port or self.port
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                return s.connect_ex((self.host, p)) == 0
        except Exception:
            return False

    def find_local_cleaner_executable(self, custom_folder: str | Path | None = None) -> tuple[Path | None, list[str]]:
        """Finds a local PyTorch CUDA lama-cleaner or inpaint daemon executable or server script."""
        if custom_folder:
            cf = Path(custom_folder)
            if cf.exists():
                if cf.is_file():
                    if cf.suffix.lower() == ".exe":
                        return cf.parent, [str(cf), "--device", "cuda", "--port", str(self.port), "--model", "lama"]
                    elif cf.suffix.lower() == ".py":
                        py_exe = _find_best_python_exe(cf.parent)
                        return cf.parent, [py_exe, str(cf)]
                    elif cf.suffix.lower() == ".bat":
                        return cf.parent, ["cmd.exe", "/c", str(cf)]
                elif cf.is_dir():
                    for sub in [cf, cf / "Scripts", cf / "venv" / "Scripts"]:
                        exe = sub / "lama-cleaner.exe"
                        if exe.exists():
                            return cf, [str(exe), "--device", "cuda", "--port", str(self.port), "--model", "lama"]
                    for sub in [cf, cf / "inpaint_server", cf / "backend" / "inpaint_server"]:
                        srv = sub / "server.py"
                        if srv.exists():
                            py_exe = _find_best_python_exe(sub)
                            return sub, [py_exe, str(srv)]
                    for bat_name in ["start.bat", "run.bat", "start_server.bat", "install_inpaint_server.bat"]:
                        bat = cf / bat_name
                        if bat.exists():
                            return cf, ["cmd.exe", "/c", str(bat)]

        backend_dir = Path(__file__).resolve().parent.parent.parent
        candidates = [
            backend_dir / "inpaint_server" / "server.py",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "HoumiStudio" / "backend" / "inpaint_server" / "server.py",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "HoumiStudio" / "_internal" / "backend" / "inpaint_server" / "server.py",
            Path.home() / "Desktop" / "inpaint_server" / "server.py",
            Path(r"C:\inpaint_server\server.py"),
        ]
        for c in candidates:
            if c.exists():
                py_exe = _find_best_python_exe(c.parent)
                return c.parent, [py_exe, str(c)]
        return None, []

    def _start_server_blocking(self, custom_path: str | Path | None = None):
        """Internal blocking method to start the server (runs in background thread)."""
        try:
            if self.is_port_active(self.port):
                logger.info("✅ GPU Inpaint Server is already active on port %d", self.port)
                return

            # 1. Check Houmi's dedicated inpaint_server folder
            backend_dir = Path(__file__).resolve().parent.parent.parent
            inpaint_dir = backend_dir / "inpaint_server"
            inpaint_server_py = inpaint_dir / "server.py"

            if inpaint_server_py.exists():
                py_exe = _find_best_python_exe(inpaint_dir)
                cmd = [py_exe, str(inpaint_server_py)]
                logger.info("🚀 Launching Built-in GPU Inpaint Server: %s", " ".join(cmd))
                try:
                    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                    self.process = subprocess.Popen(
                        cmd,
                        cwd=str(inpaint_dir),
                        creationflags=creationflags,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    logger.info("Built-in GPU Inpaint Server started (PID: %s)", self.process.pid)
                    for _ in range(20):
                        time.sleep(0.25)
                        if self.is_port_active(self.port):
                            logger.info("✅ Built-in GPU Inpaint Server is ready on port %d!", self.port)
                            return
                except Exception as e:
                    logger.warning("Failed to start inpaint_server: %s", e)

            # 2. Fallback to any local standalone runner
            cwd_path, cmd = self.find_local_cleaner_executable(custom_path)
            if cwd_path and cmd:
                logger.info("🚀 Auto-Launching GPU Inpaint Server: %s (cwd: %s)", " ".join(cmd), cwd_path)
                try:
                    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                    self.process = subprocess.Popen(
                        cmd,
                        cwd=str(cwd_path),
                        creationflags=creationflags,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    logger.info("GPU Inpaint Server daemon started successfully (PID: %s)", self.process.pid)
                    # Wait briefly for server socket to bind
                    for _ in range(20):
                        time.sleep(0.25)
                        if self.is_port_active(self.port):
                            logger.info("✅ GPU Inpaint Server is online and ready on port %d!", self.port)
                            break
                except Exception as e:
                    logger.warning("Failed to start GPU Inpaint Server daemon: %s", e)
            else:
                logger.info("No external lama-cleaner.exe found; GPU server auto-start skipped.")
        finally:
            self._is_starting = False

    def start_server_if_needed(self, custom_path: str | Path | None = None, non_blocking: bool = True):
        """Starts the GPU Inpaint Server in the background if not already active.

        Args:
            custom_path: Optional custom path to server executable/script
            non_blocking: If True (default), start in background thread without blocking
        """
        if self.is_port_active(self.port):
            logger.debug("GPU Inpaint Server port %d is already active.", self.port)
            return

        if self._is_starting:
            logger.debug("GPU Inpaint Server is already starting in background.")
            return

        if non_blocking:
            # Start in background thread (don't block pipeline)
            self._is_starting = True
            self._start_thread = threading.Thread(
                target=self._start_server_blocking,
                args=(custom_path,),
                daemon=True,
                name="InpaintServerAutoStart"
            )
            self._start_thread.start()
            logger.info("⚙️ GPU Inpaint Server auto-start initiated in background (non-blocking)")
        else:
            # Blocking mode (for manual start or testing)
            self._is_starting = True
            self._start_server_blocking(custom_path)


inpaint_manager = InpaintServerManager()

