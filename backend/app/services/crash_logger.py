import sys
import os
import traceback
import time
import json
import logging
from pathlib import Path

logger = logging.getLogger("houmi-crash-reporter")

# Define crash log directory: <root>/logs/crash_reports
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CRASH_LOG_DIR = BASE_DIR / "logs" / "crash_reports"
CRASH_LOG_DIR.mkdir(parents=True, exist_ok=True)

def get_system_memory_info():
    """Retrieve RAM and memory stats if psutil is available."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {
            "ram_used_mb": round(vm.used / 1024 / 1024, 1),
            "ram_total_mb": round(vm.total / 1024 / 1024, 1),
            "ram_percent": vm.percent
        }
    except Exception:
        return {"ram_info": "psutil unavailable"}

def log_crash_report(exc_type, exc_value, exc_tb, source="sys_excepthook"):
    """Format and save a detailed crash report to disk and stdout."""
    timestamp_str = time.strftime("%Y-%m-%d_%H-%M-%S")
    formatted_tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    
    memory_info = get_system_memory_info()
    
    report_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "exception_type": str(exc_type.__name__ if hasattr(exc_type, "__name__") else exc_type),
        "exception_message": str(exc_value),
        "traceback": formatted_tb,
        "system_memory": memory_info,
        "python_version": sys.version,
    }
    
    # Save TXT report
    txt_filename = CRASH_LOG_DIR / f"crash_{timestamp_str}.txt"
    txt_content = (
        "==========================================================================\n"
        "  HOUMI STUDIO CRASH REPORT\n"
        "==========================================================================\n"
        f"Timestamp: {report_data['timestamp']}\n"
        f"Source: {source}\n"
        f"Error: {report_data['exception_type']}: {report_data['exception_message']}\n"
        f"Memory: {json.dumps(memory_info)}\n"
        "--------------------------------------------------------------------------\n"
        "FULL STACK TRACEBACK:\n"
        "--------------------------------------------------------------------------\n"
        f"{formatted_tb}\n"
        "==========================================================================\n"
    )
    
    try:
        with open(txt_filename, "w", encoding="utf-8") as f:
            f.write(txt_content)
            
        latest_json = CRASH_LOG_DIR / "latest_crash.json"
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Failed to write crash log file: {exc}", file=sys.stderr)

    # Print to CMD console with prominent formatting
    print("\n" + "=" * 80, file=sys.stderr)
    print("🚨 [CRITICAL APPLICATION CRASH / EXCEPTION DETECTED]", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(f"Crash Log Saved: {txt_filename}", file=sys.stderr)
    print(f"Exception: {report_data['exception_type']}: {report_data['exception_message']}", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    print(formatted_tb, file=sys.stderr)
    print("=" * 80 + "\n", file=sys.stderr)

def install_crash_handlers():
    """Install global exception hooks for sys, threading, and asyncio."""
    def handle_sys_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        log_crash_report(exc_type, exc_value, exc_tb, source="Global Exception Hook")
        
    def handle_thread_exception(args):
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        log_crash_report(args.exc_type, args.exc_value, args.exc_traceback, source=f"Thread ({args.thread.name})")

    sys.excepthook = handle_sys_exception
    
    import threading
    threading.excepthook = handle_thread_exception
    logger.info("Global Crash Handler & Unhandled Exception Hooks installed successfully.")
