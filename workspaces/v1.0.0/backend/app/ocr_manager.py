import os
import subprocess
import time
import socket
import logging
import requests
import psutil
from app.config import OCR_SERVER_DIR, OCR_PORT, OCR_HOST, OCR_API_URL

logger = logging.getLogger("houmi-ocr-manager")

class OCRManager:
    def __init__(self):
        self.process = None
        self.should_run = True
        self.last_start_time = 0.0

    def check_port_in_use(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((OCR_HOST, port)) == 0

    def force_kill_port_owner(self, port: int):
        """Finds and kills any process using the specified port on Windows efficiently."""
        logger.info(f"Checking for any process holding port {port}...")
        try:
            # Fast path using system TCP net_connections
            killed_any = False
            for conn in psutil.net_connections(kind="tcp"):
                if conn.laddr and conn.laddr.port == port and conn.pid:
                    try:
                        proc = psutil.Process(conn.pid)
                        proc_name = proc.name().lower()
                        if proc_name in ["system", "svchost.exe", "lsass.exe", "csrss.exe", "smss.exe", "services.exe", "wininit.exe"]:
                            logger.warning(f"Skipping force-killing of critical system process: {proc.name()} (PID: {proc.pid})")
                            continue
                        logger.warning(f"Found process {proc.name()} (PID: {proc.pid}) holding port {port}. Force killing...")
                        proc.kill()
                        proc.wait(timeout=2)
                        killed_any = True
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                        pass
            if killed_any:
                return
        except Exception as e:
            logger.debug(f"psutil.net_connections fallback due to: {e}")

        # Fallback path if net_connections requires admin elevation
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                for conn in proc.connections(kind="inet"):
                    if conn.laddr and conn.laddr.port == port:
                        proc_name = proc.info['name'].lower()
                        if proc_name in ["system", "svchost.exe", "lsass.exe", "csrss.exe", "smss.exe", "services.exe", "wininit.exe"]:
                            continue
                        logger.warning(f"Found process {proc.info['name']} (PID: {proc.info['pid']}) holding port {port}. Force killing...")
                        proc.kill()
                        proc.wait(timeout=2)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass

    def start_server(self):
        self.should_run = True
        if self.check_port_in_use(OCR_PORT):
            logger.info(f"OCR Server port {OCR_PORT} is already active.")
            return

        # 1. Prioritize launching subprocess via dedicated venv python if installed
        python_exe = OCR_SERVER_DIR / "venv" / "Scripts" / "python.exe"
        server_py = OCR_SERVER_DIR / "server.py"

        if python_exe.exists() and server_py.exists():
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = "0"
            env["PRELOAD_MODEL"] = "true"
            env["LOAD_IN_4BIT"] = "true"
            env["OCR_BACKEND"] = "auto"

            log_dir = OCR_SERVER_DIR / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "ocr_server.log"

            logger.info(f"Starting VLM OCR Server subprocess: {python_exe} {server_py} (logs: {log_file})")
            try:
                log_out = open(log_file, "a", encoding="utf-8", errors="replace")
                self.process = subprocess.Popen(
                    [str(python_exe), str(server_py)],
                    cwd=str(OCR_SERVER_DIR),
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    stdout=log_out,
                    stderr=log_out
                )
                self.last_start_time = time.time()
                logger.info("VLM OCR Server subprocess spawned successfully on port 2322.")
                return
            except Exception as e:
                logger.error(f"Failed to start VLM OCR Server subprocess: {e}")

        # 2. In-process fallback (for dev environment where PyTorch is installed in main env)
        try:
            logger.info("Attempting in-process OCR Server thread on port 2322...")
            import threading
            from socketserver import ThreadingMixIn
            from wsgiref.simple_server import WSGIServer

            try:
                from ocr_server.server import run as run_bottle_server
            except ImportError:
                from backend.ocr_server.server import run as run_bottle_server

            class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
                daemon_threads = True

            def _run_thread():
                try:
                    run_bottle_server(host=OCR_HOST, port=OCR_PORT, reloader=False, server_class=ThreadingWSGIServer, quiet=True)
                except Exception as err:
                    logger.warning(f"In-process OCR Server thread ended: {err}")

            t = threading.Thread(target=_run_thread, daemon=True)
            t.start()
            self.last_start_time = time.time()
            logger.info("OCR Server in-process thread started successfully on port 2322.")
            return
        except Exception as e_thread:
            logger.info(f"Local PyTorch VLM server unavailable on port 2322: {e_thread}")
            self.should_run = False

    def stop_server(self):
        self.should_run = False
        if self.process:
            logger.info("Terminating OCR Server process...")
            try:
                # Terminate process and all its children
                parent = psutil.Process(self.process.pid)
                for child in parent.children(recursive=True):
                    child.terminate()
                parent.terminate()
                
                # Wait for shutdown
                gone, alive = psutil.wait_procs(parent.children(recursive=True) + [parent], timeout=3)
                for p in alive:
                    p.kill()  # Force kill if still running
                logger.info("OCR Server terminated completely.")
            except Exception as e:
                logger.error(f"Error terminating OCR Server process: {e}")
            finally:
                self.process = None

    def check_health(self) -> bool:
        """Pings OCR health endpoint."""
        try:
            url = f"http://{OCR_HOST}:{OCR_PORT}/health"
            res = requests.get(url, timeout=2.0)
            if res.status_code == 200:
                data = res.json()
                return data.get("status") == "ok"
        except Exception:
            pass
        return False

    def maintain_server(self):
        """Call this in a background thread to keep OCR Server alive if explicitly started."""
        while self.should_run:
            time.sleep(15)
            if not self.should_run:
                break
            
            # Only monitor and restart if a VLM server process was explicitly spawned
            if self.process is not None:
                is_alive = self.process.poll() is None
                if not is_alive:
                    if self.should_run:
                        logger.warning("VLM OCR Server process terminated. Attempting restart...")
                        self.start_server()
                elif time.time() - self.last_start_time > 120:
                    if not self.check_health() and self.should_run:
                        logger.warning("VLM OCR Server unresponsive after grace period. Attempting restart...")
                        self.start_server()

# Global manager instance
ocr_manager = OCRManager()
