import os
import time
import json
import logging
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
try:
    import onnxruntime as ort
except ImportError:
    ort = None
import numpy as np

from app.database import get_db, engine
from app.config import DATA_DIR, BALLOON_MODEL_PATH, PSD_CLI_PATH
from app.ocr_manager import ocr_manager
from app.config import RUNTIME_MODE
from app.security.dependencies import get_current_user_or_local

router = APIRouter(tags=["Diagnostics"])
logger = logging.getLogger("houmi-diagnostics-router")

DIAGNOSTICS_DIR = DATA_DIR / "diagnostics"
DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = DIAGNOSTICS_DIR / "e2e_report.json"


class AIProviderSettingsRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    google_api_key: str | None = None
    clear_google_api_key: bool = False

class AddAIKeyRequest(BaseModel):
    name: str | None = None
    key: str
    priority: int | None = None

class UpdateAIKeyRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    priority: int | None = None

class ReorderAIKeysRequest(BaseModel):
    key_ids: list[str]


def _require_global_settings_access(user) -> None:
    """Global credentials are editable by local desktop or a host admin only."""
    if RUNTIME_MODE in {"host", "admin"} and (user is None or getattr(user, "role", "") != "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator permission required")


def _ai_provider_status() -> dict:
    from app.services.ai_provider_settings import (
        get_ai_provider_full_status,
        get_stored_google_api_key,
    )
    from app.services.ocr import _get_gemini_api_key

    full_status = get_ai_provider_full_status()
    has_stored_key = bool(get_stored_google_api_key())
    has_key = bool(_get_gemini_api_key())
    return {
        **full_status,
        "has_google_api_key": has_key,
        "key_source": "global_settings" if has_stored_key else ("environment" if has_key else None),
        "agy_available": bool(shutil.which("agy")),
        "gemini_cli_available": bool(shutil.which("gemini")),
    }


@router.get("/settings/ai-provider")
@router.get("/system/ai-provider")
def get_ai_provider_settings(user=Depends(get_current_user_or_local)):
    """Return provider status without ever returning raw API keys."""
    _require_global_settings_access(user)
    return _ai_provider_status()


@router.put("/settings/ai-provider")
@router.post("/settings/ai-provider")
@router.put("/system/ai-provider")
@router.post("/system/ai-provider")
def update_ai_provider_settings(
    request: AIProviderSettingsRequest,
    user=Depends(get_current_user_or_local),
):
    """Store the local Google key/provider preference outside project settings."""
    _require_global_settings_access(user)
    from app.services.ai_provider_settings import update_ai_provider_preferences

    try:
        update_ai_provider_preferences(
            provider=request.provider,
            model=request.model,
            google_api_key=request.google_api_key,
            clear_google_api_key=request.clear_google_api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _ai_provider_status()


@router.post("/settings/ai-provider/keys")
def add_ai_provider_key(request: AddAIKeyRequest, user=Depends(get_current_user_or_local)):
    """Add a new API key to the priority failover pool."""
    _require_global_settings_access(user)
    from app.services.ai_provider_settings import add_google_api_key
    try:
        add_google_api_key(name=request.name or "", key=request.key, priority=request.priority)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _ai_provider_status()


@router.delete("/settings/ai-provider/keys/{key_id}")
def delete_ai_provider_key(key_id: str, user=Depends(get_current_user_or_local)):
    """Remove a key from the pool by ID."""
    _require_global_settings_access(user)
    from app.services.ai_provider_settings import remove_google_api_key
    return remove_google_api_key(key_id)


@router.patch("/settings/ai-provider/keys/{key_id}")
def update_ai_provider_key(key_id: str, request: UpdateAIKeyRequest, user=Depends(get_current_user_or_local)):
    """Update name, priority, or enabled status of a key."""
    _require_global_settings_access(user)
    from app.services.ai_provider_settings import update_google_api_key_item
    try:
        update_google_api_key_item(key_id, name=request.name, enabled=request.enabled, priority=request.priority)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _ai_provider_status()


@router.post("/settings/ai-provider/keys/reorder")
def reorder_ai_provider_keys(request: ReorderAIKeysRequest, user=Depends(get_current_user_or_local)):
    """Reorder key priority sequence based on ID list."""
    _require_global_settings_access(user)
    from app.services.ai_provider_settings import reorder_google_api_keys
    return reorder_google_api_keys(request.key_ids)


@router.get("/system/ai-quota-status")
@router.get("/settings/ai-quota-status")
def get_ai_quota_status():
    """Return real-time AI quota status and cooldown reset state."""
    from app.services.gemini_quota import get_quota_status
    return get_quota_status()


@router.post("/system/ai-quota-status/check")
@router.post("/settings/ai-quota-status/check")
def check_ai_quota_status():
    """Run an active CLI check to test AGY CLI quota and cooldown reset timer."""
    from app.services.gemini_quota import check_agy_cli_status
    return check_agy_cli_status()


@router.post("/system/agy-login")
@router.post("/settings/agy-login")
def trigger_agy_login():
    """Trigger 'agy auth login' command in terminal to authenticate AGY CLI."""
    import subprocess
    import sys
    try:
        if sys.platform == "win32":
            subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", "agy auth login"])
        else:
            subprocess.Popen(["agy", "auth", "login"])
        return {"success": True, "message": "AGY CLI login terminal launched"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

@router.get("/diagnostics/show-console")
@router.post("/diagnostics/show-console")
def show_debug_console():
    """Allocates and shows a live Windows CMD Console window for real-time log debugging."""
    import sys
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
        return {"success": True, "message": "CMD Console window popped open"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/diagnostics/crashes")
def list_crash_reports():
    """List recorded crash reports from logs/crash_reports directory."""
    from app.services.crash_logger import CRASH_LOG_DIR
    if not CRASH_LOG_DIR.exists():
        return {"crashes": []}
    
    reports = []
    for f in sorted(CRASH_LOG_DIR.glob("crash_*.txt"), reverse=True):
        reports.append({
            "filename": f.name,
            "path": str(f),
            "size_bytes": f.stat().st_size,
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime))
        })
    return {"crashes": reports, "count": len(reports)}

@router.get("/diagnostics/crashes/latest")
def get_latest_crash_report():
    """Retrieve the content of the latest crash report."""
    from app.services.crash_logger import CRASH_LOG_DIR
    latest_json = CRASH_LOG_DIR / "latest_crash.json"
    if latest_json.exists():
        try:
            with open(latest_json, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
            
    files = sorted(CRASH_LOG_DIR.glob("crash_*.txt"), reverse=True)
    if not files:
        return {"status": "no_crashes", "message": "No crash reports recorded."}
    
    latest_txt = files[0]
    try:
        with open(latest_txt, "r", encoding="utf-8") as f:
            content = f.read()
        return {"status": "ok", "filename": latest_txt.name, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/diagnostics/health")
def get_diagnostics_health(db: Session = Depends(get_db)):
    health_results = {
        "status": "online",
        "timestamp": time.time(),
    }

    # 1. Database Check
    db_health = {"status": "unknown", "latency_ms": 0.0, "message": ""}
    try:
        t0 = time.time()
        db.execute(text("SELECT 1"))
        db_latency = (time.time() - t0) * 1000.0
        db_health["status"] = "ok"
        db_health["latency_ms"] = round(db_latency, 2)
        db_health["message"] = "SQLite database connected"
    except Exception as e:
        db_health["status"] = "error"
        db_health["message"] = str(e)
        health_results["status"] = "degraded"

    # 2. OCR Check
    ocr_health = {"status": "unknown", "message": ""}
    try:
        is_alive = ocr_manager.check_health()
        if is_alive:
            ocr_health["status"] = "ok"
            ocr_health["message"] = "OCR managed subprocess is healthy"
        else:
            ocr_health["status"] = "error"
            ocr_health["message"] = "OCR managed subprocess is not responding"
            health_results["status"] = "degraded"
    except Exception as e:
        ocr_health["status"] = "error"
        ocr_health["message"] = str(e)
        health_results["status"] = "degraded"

    # 3. GPU Inpaint Server Check
    inpaint_health = {"status": "unknown", "message": "", "server_type": "none", "latency_ms": 0.0}
    try:
        from app.services.inpainter import _is_local_lama_cleaner_alive
        from app.services.ai_provider_settings import get_ai_provider_settings

        settings = get_ai_provider_settings()
        custom_url = settings.get("gpu_inpaint_url")

        # Check custom URL first
        if custom_url and custom_url.strip():
            try:
                import urllib.request
                target_url = custom_url.strip().rstrip("/")
                base_url = target_url.split("/inpaint")[0]
                t0 = time.time()
                req = urllib.request.Request(f"{base_url}/health", headers={"User-Agent": "HoumiStudio"}, method="GET")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    latency = (time.time() - t0) * 1000.0
                    if resp.status in (200, 404, 405):
                        inpaint_health["status"] = "ok"
                        inpaint_health["server_type"] = "custom_gpu"
                        inpaint_health["message"] = f"Custom GPU server online at {custom_url}"
                        inpaint_health["latency_ms"] = round(latency, 2)
            except Exception as e:
                inpaint_health["status"] = "error"
                inpaint_health["message"] = f"Custom GPU server unreachable: {e}"
                health_results["status"] = "degraded"

        # Check local ports if no custom URL or custom failed
        if inpaint_health["status"] == "unknown":
            for port in (2328, 2322, 2335):
                t0 = time.time()
                if _is_local_lama_cleaner_alive(port, timeout=0.5):
                    latency = (time.time() - t0) * 1000.0
                    inpaint_health["status"] = "ok"
                    inpaint_health["server_type"] = "local_gpu"
                    inpaint_health["message"] = f"Local GPU server online on port {port}"
                    inpaint_health["latency_ms"] = round(latency, 2)
                    break

        # Fallback to ONNX check
        if inpaint_health["status"] == "unknown":
            from app.config import INPAINT_MODEL_PATH, MODELS_DIR
            onnx_found = False
            for alt in (INPAINT_MODEL_PATH, MODELS_DIR / "inpainting" / "lama_manga.onnx", MODELS_DIR / "inpainting" / "lama.onnx"):
                if alt.exists():
                    inpaint_health["status"] = "fallback"
                    inpaint_health["server_type"] = "onnx_local"
                    inpaint_health["message"] = f"Using ONNX fallback: {alt.name}"
                    onnx_found = True
                    break
            if not onnx_found:
                inpaint_health["status"] = "degraded"
                inpaint_health["server_type"] = "telea_only"
                inpaint_health["message"] = "No GPU server or ONNX model found, using Telea fallback"
                health_results["status"] = "degraded"
    except Exception as e:
        inpaint_health["status"] = "error"
        inpaint_health["message"] = str(e)

    # 4. YOLO Model Check
    from app.config import BALLOON_MODEL_PATH, INPAINT_MODEL_PATH, MODELS_DIR
    yolo_health = {
        "status": "unknown",
        "latency_ms": 0.0,
        "model_path": str(BALLOON_MODEL_PATH),
        "message": ""
    }
    try:
        if not BALLOON_MODEL_PATH.exists():
            yolo_health["status"] = "missing"
            yolo_health["message"] = f"Model file not found at {BALLOON_MODEL_PATH}"
            health_results["status"] = "degraded"
        else:
            t0 = time.time()
            if ort is not None:
                session = ort.InferenceSession(str(BALLOON_MODEL_PATH), providers=["CPUExecutionProvider"])
                dummy_input = np.random.randn(1, 3, 640, 640).astype(np.float32)
                input_name = session.get_inputs()[0].name
                session.run(None, {input_name: dummy_input})
            latency = (time.time() - t0) * 1000.0

            yolo_health["status"] = "ok"
            yolo_health["latency_ms"] = round(latency, 2)
            yolo_health["message"] = f"YOLO balloon detector model loaded and functional ({round(BALLOON_MODEL_PATH.stat().st_size / 1024 / 1024, 1)} MB)"
    except Exception as e:
        yolo_health["status"] = "error"
        yolo_health["message"] = str(e)
        health_results["status"] = "degraded"

    # 5. PSD CLI Check
    psd_health = {
        "status": "unknown",
        "executable_path": str(PSD_CLI_PATH),
        "message": ""
    }
    try:
        if PSD_CLI_PATH.exists():
            psd_health["status"] = "ok"
            psd_health["message"] = f"PSD CLI found at {PSD_CLI_PATH}"
        else:
            psd_health["status"] = "missing"
            psd_health["message"] = f"PSD CLI executable not found at {PSD_CLI_PATH}"
    except Exception as e:
        psd_health["status"] = "error"
        psd_health["message"] = str(e)

    health_results["checks"] = {
        "database": db_health,
        "ocr": ocr_health,
        "inpaint": inpaint_health,
        "yolo": yolo_health,
        "psd": psd_health,
    }

    return health_results


@router.get("/diagnostics/models-audit")
def audit_system_models():
    """Return an exhaustive file-by-file audit of all AI models in Houmi Studio."""
    from app.config import MODELS_DIR, INPAINT_MODEL_PATH, BALLOON_MODEL_PATH, MANGA_TEXT_SEG_MODEL_PATH
    
    models_spec = [
        {
            "name": "Manga UNet++ Text Segmentation (ONNX)",
            "key": "manga_unet_onnx",
            "category": "mask",
            "role": "สแกนตัวอักษร AI / แยกหมึกอักษรไม่กินเส้นบอลลูน",
            "path": str(MODELS_DIR / "manga_text_segmentation" / "manga_unet.onnx"),
            "exists": (MODELS_DIR / "manga_text_segmentation" / "manga_unet.onnx").exists(),
            "size_mb": round((MODELS_DIR / "manga_text_segmentation" / "manga_unet.onnx").stat().st_size / 1024 / 1024, 1) if (MODELS_DIR / "manga_text_segmentation" / "manga_unet.onnx").exists() else 0,
            "critical": True,
        },
        {
            "name": "Anime & Manga LaMa Inpainter (ONNX)",
            "key": "lama_manga_onnx",
            "category": "inpaint",
            "role": "AI ลบตัวหนังสือและเติมฉากหลังความละเอียดสูง",
            "path": str(MODELS_DIR / "inpainting" / "lama_manga.onnx"),
            "exists": (MODELS_DIR / "inpainting" / "lama_manga.onnx").exists(),
            "size_mb": round((MODELS_DIR / "inpainting" / "lama_manga.onnx").stat().st_size / 1024 / 1024, 1) if (MODELS_DIR / "inpainting" / "lama_manga.onnx").exists() else 0,
            "critical": True,
        },
        {
            "name": "Standard Big-LaMa Inpainter (ONNX)",
            "key": "lama_onnx",
            "category": "inpaint",
            "role": "โมเดลลบภาพมาตรฐาน (LaMa Standard Fallback)",
            "path": str(MODELS_DIR / "inpainting" / "lama.onnx"),
            "exists": (MODELS_DIR / "inpainting" / "lama.onnx").exists(),
            "size_mb": round((MODELS_DIR / "inpainting" / "lama.onnx").stat().st_size / 1024 / 1024, 1) if (MODELS_DIR / "inpainting" / "lama.onnx").exists() else 0,
            "critical": False,
        },
        {
            "name": "YOLO Speech Balloon Detector (ONNX)",
            "key": "yolo_balloon_onnx",
            "category": "detect",
            "role": "AI ตรวจจับและวาดกรอบบอลลูนคำพูดอัตโนมัติ",
            "path": str(BALLOON_MODEL_PATH),
            "exists": BALLOON_MODEL_PATH.exists(),
            "size_mb": round(BALLOON_MODEL_PATH.stat().st_size / 1024 / 1024, 1) if BALLOON_MODEL_PATH.exists() else 0,
            "critical": True,
        },
        {
            "name": "Meta SAM 2.1 Encoder (ONNX)",
            "key": "sam2_encoder",
            "category": "segment",
            "role": "โมเดลตัดภาพและ SFX วัตถุซับซ้อน (Segment Anything)",
            "path": str(MODELS_DIR / "sam" / "sam2.1_hiera_base_plus.encoder.onnx"),
            "exists": (MODELS_DIR / "sam" / "sam2.1_hiera_base_plus.encoder.onnx").exists(),
            "size_mb": round((MODELS_DIR / "sam" / "sam2.1_hiera_base_plus.encoder.onnx").stat().st_size / 1024 / 1024, 1) if (MODELS_DIR / "sam" / "sam2.1_hiera_base_plus.encoder.onnx").exists() else 0,
            "critical": False,
        },
    ]

    missing_critical = [m for m in models_spec if m["critical"] and not m["exists"]]
    
    return {
        "status": "ok" if not missing_critical else "missing_models",
        "models_dir": str(MODELS_DIR),
        "models_dir_exists": MODELS_DIR.exists(),
        "total_models": len(models_spec),
        "installed_models": len([m for m in models_spec if m["exists"]]),
        "missing_critical_count": len(missing_critical),
        "missing_critical_names": [m["name"] for m in missing_critical],
        "models": models_spec,
        "fix_instructions": f"หากมีโมเดลหาย ให้คัดลอกโฟลเดอร์ models ทั้งหมดไปวางที่: {MODELS_DIR}"
    }

@router.get("/diagnostics/e2e-report")
def get_e2e_report():
    if not REPORT_PATH.exists():
        return {
            "status": "no_report",
            "message": "No E2E test report found. Please run the E2E diagnostics script first."
        }
    try:
        with open(REPORT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read diagnostic report: {e}"
        )


def _detect_gpu_info() -> dict:
    """Try multiple methods to detect GPU name and VRAM."""
    # Method 1: pynvml (NVIDIA)
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        pynvml.nvmlShutdown()
        return {"gpu_name": str(name), "gpu_vram_gb": round(mem.total / (1024**3), 1)}
    except Exception:
        pass

    # Method 2: torch.cuda (if PyTorch installed)
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            return {"gpu_name": str(name), "gpu_vram_gb": round(vram, 1)}
    except Exception:
        pass

    # Method 3: Windows WMI via subprocess (AMD/Intel/NVIDIA DirectML)
    try:
        import subprocess
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            gpus = json.loads(result.stdout)
            if not isinstance(gpus, list):
                gpus = [gpus]
            valid_gpus = [g for g in gpus if g.get("Name")]
            if valid_gpus:
                gpu = valid_gpus[0]
                ram = gpu.get("AdapterRAM")
                vram = round(ram / (1024**3), 1) if (ram and isinstance(ram, (int, float)) and ram > 0) else None
                return {"gpu_name": str(gpu.get("Name")), "gpu_vram_gb": vram}
    except Exception:
        pass

    return {"gpu_name": None, "gpu_vram_gb": None}


@router.get("/diagnostics/hardware")
@router.get("/hardware-status")
def get_hardware_diagnostics():
    """Detect GPU hardware availability (Nvidia CUDA, AMD/Intel DirectML, or CPU fallback) and hardware specs."""
    import platform
    import psutil
    import onnxruntime as ort
    from app.config import get_execution_providers
    from app.services.ai_provider_settings import _load_raw_settings

    try:
        avail_providers = ort.get_available_providers()
    except Exception:
        avail_providers = ["CPUExecutionProvider"]

    active_providers = get_execution_providers()
    has_nvidia_cuda = "CUDAExecutionProvider" in avail_providers
    has_directml = "DmlExecutionProvider" in avail_providers
    is_cpu_only = not (has_nvidia_cuda or has_directml)

    cpu_cores = os.cpu_count() or 1
    cpu_name = platform.processor() or platform.machine() or "Unknown CPU"
    
    vm = psutil.virtual_memory()
    ram_total_gb = round(vm.total / (1024**3), 1)
    ram_available_gb = round(vm.available / (1024**3), 1)

    gpu_info = _detect_gpu_info()
    gpu_name = gpu_info.get("gpu_name")
    gpu_vram_gb = gpu_info.get("gpu_vram_gb")

    # Optimal execution provider calculation
    if has_nvidia_cuda:
        optimal_provider = "CUDA"
    elif has_directml:
        optimal_provider = "DirectML"
    else:
        optimal_provider = "CPU"

    # Optimal thread calculation
    if optimal_provider in ("CUDA", "DirectML"):
        optimal_thread_count = max(2, cpu_cores // 2)
    else:
        optimal_thread_count = max(2, cpu_cores - 2)

    # Check settings and optimization status
    raw_settings = _load_raw_settings()
    saved_provider = raw_settings.get("execution_provider")
    
    active_primary = active_providers[0] if active_providers else "CPUExecutionProvider"
    
    # Provider matches optimal?
    provider_is_optimal = False
    if optimal_provider == "CUDA" and active_primary == "CUDAExecutionProvider":
        provider_is_optimal = True
    elif optimal_provider == "DirectML" and active_primary in ("DmlExecutionProvider", "CUDAExecutionProvider"):
        provider_is_optimal = True
    elif optimal_provider == "CPU" and active_primary == "CPUExecutionProvider":
        provider_is_optimal = True

    is_optimized = provider_is_optimal and (saved_provider == optimal_provider or saved_provider is not None)

    # Acceleration text
    if active_primary == "CUDAExecutionProvider":
        acceleration_type = "Nvidia CUDA Acceleration ⚡ (สปีดสูงสุด)"
        notice = "พบการ์ดจอ Nvidia! ระบบทำงานด้วย CUDA ความเร็วสูงเต็มประสิทธิภาพ"
    elif active_primary == "DmlExecutionProvider":
        acceleration_type = "DirectML Acceleration 🚀 (AMD / Intel / Nvidia GPU)"
        notice = "ระบบเปิดใช้งาน DirectML เร่งความเร็วด้วยการ์ดจออัตโนมัติ"
    else:
        acceleration_type = "CPU Fallback Mode 🐢 (Standard Processor)"
        notice = "ระบบใช้ CPU Multi-Threading ประมวลผลโดยแอปไม่แครช"

    # Generate suggestions
    suggestions = []
    gpu_str_lower = (gpu_name or "").lower()
    is_nvidia_gpu = any(k in gpu_str_lower for k in ("nvidia", "geforce", "rtx", "gtx", "quadro"))

    if is_nvidia_gpu and not has_nvidia_cuda:
        suggestions.append({
            "type": "driver_install",
            "title": "ดาวน์โหลด NVIDIA CUDA Toolkit",
            "description": f"ตรวจพบการ์ดจอ {gpu_name}! ติดตั้ง CUDA Toolkit เพื่อเพิ่มสปีดการประมวลผลสูงสุด (5x - 10x)",
            "action_url": "https://developer.nvidia.com/cuda-downloads",
            "action_label": "ดาวน์โหลด NVIDIA CUDA",
            "priority": "high"
        })
    elif is_nvidia_gpu and has_nvidia_cuda and active_primary != "CUDAExecutionProvider":
        suggestions.append({
            "type": "setting_change",
            "title": "สลับการทำงานไปใช้ NVIDIA CUDA",
            "description": "CUDA พร้อมใช้งานแล้วบนเครื่องของคุณ กด Auto-Optimize เพื่อเปลี่ยนไปใช้ CUDA",
            "action_url": None,
            "action_label": None,
            "priority": "high"
        })

    if gpu_name and not is_nvidia_gpu and not has_directml:
        suggestions.append({
            "type": "driver_install",
            "title": "ติดตั้ง DirectML Runtime",
            "description": f"ตรวจพบการ์ดจอ {gpu_name}! ติดตั้ง DirectML เพื่อใช้เร่งความเร็วการ์ดจอ",
            "action_url": "https://learn.microsoft.com/en-us/windows/ai/directml/dml-intro",
            "action_label": "ดาวน์โหลด DirectML Runtime",
            "priority": "medium"
        })

    if is_cpu_only and gpu_name:
        suggestions.append({
            "type": "setting_change",
            "title": "เปลี่ยนการประมวลผลไปใช้การ์ดจอ (GPU)",
            "description": "ปัจจุบันระบบทำงานในโหมด CPU กด Auto-Optimize เพื่อเร่งสปีดด้วย GPU",
            "action_url": None,
            "action_label": None,
            "priority": "high"
        })

    if ram_total_gb < 8.0:
        suggestions.append({
            "type": "info",
            "title": "หน่วยความจำ (RAM) ต่ำกว่า 8GB",
            "description": "แนะนำให้ปิดโปรแกรมอื่นขณะใช้งานเพื่อป้องกัน RAM เต็ม",
            "action_url": None,
            "action_label": None,
            "priority": "medium"
        })

    return {
        "status": "ok",
        "has_nvidia_cuda": has_nvidia_cuda,
        "has_directml": has_directml,
        "is_cpu_only": is_cpu_only,
        "acceleration_type": acceleration_type,
        "notice": notice,
        "available_providers": avail_providers,
        "active_providers": active_providers,
        "cpu_cores": cpu_cores,
        "cpu_name": cpu_name,
        "ram_total_gb": ram_total_gb,
        "ram_available_gb": ram_available_gb,
        "gpu_name": gpu_name,
        "gpu_vram_gb": gpu_vram_gb,
        "optimal_provider": optimal_provider,
        "optimal_thread_count": optimal_thread_count,
        "is_optimized": is_optimized,
        "optimization_suggestions": suggestions,
    }


@router.post("/diagnostics/auto-optimize")
@router.post("/auto-optimize")
def auto_optimize_hardware():
    """
    1-Click: Automatically detect hardware specs and apply optimal execution provider & CPU thread limits.
    """
    import onnxruntime as ort
    from app.services.ai_provider_settings import _load_raw_settings, _write_raw_settings

    try:
        avail = ort.get_available_providers()
    except Exception:
        avail = ["CPUExecutionProvider"]

    if "CUDAExecutionProvider" in avail:
        optimal_provider = "CUDA"
    elif "DmlExecutionProvider" in avail:
        optimal_provider = "DirectML"
    else:
        optimal_provider = "CPU"

    cpu_cores = os.cpu_count() or 4
    if optimal_provider in ("CUDA", "DirectML"):
        optimal_thread_count = max(2, cpu_cores // 2)
    else:
        optimal_thread_count = max(2, cpu_cores - 2)

    # Persist to environment and global_settings.json
    os.environ["HOUMI_EXECUTION_PROVIDER"] = optimal_provider
    raw_settings = _load_raw_settings()
    raw_settings["execution_provider"] = optimal_provider
    raw_settings["optimal_thread_count"] = optimal_thread_count
    _write_raw_settings(raw_settings)

    hardware_report = get_hardware_diagnostics()

    return {
        "status": "ok",
        "message": f"ปรับแต่งระบบเรียบร้อยแล้ว! เปิดใช้งาน {optimal_provider} ({optimal_thread_count} Threads)",
        "applied": {
            "execution_provider": optimal_provider,
            "optimal_thread_count": optimal_thread_count,
        },
        "hardware_report": hardware_report,
    }


class TestInpaintServerRequest(BaseModel):
    url: str


@router.post("/diagnostics/test-inpaint-server")
def test_inpaint_server(req: TestInpaintServerRequest):
    import urllib.request
    import json
    url = (req.url or "").strip()
    if not url:
        return {"success": False, "message": "กรุณาระบุ URL ของ Inpaint Server"}

    # Determine health URL
    base_url = url.split("/inpaint")[0].rstrip("/")
    health_url = f"{base_url}/health"

    t0 = time.perf_counter()
    try:
        req_obj = urllib.request.Request(health_url, headers={"User-Agent": "HoumiStudio"}, method="GET")
        with urllib.request.urlopen(req_obj, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed_ms = (time.perf_counter() - t0) * 1000
            gpu_name = data.get("gpu_name") or data.get("device", "GPU")
            return {
                "success": True,
                "message": f"เชื่อมต่อสำเร็จ ({elapsed_ms:.1f} ms) — {gpu_name}",
                "gpu_name": gpu_name,
                "device": data.get("device", "cuda"),
                "status": "connected",
                "latency_ms": round(elapsed_ms, 1)
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"ไม่สามารถเชื่อมต่อ Inpaint Server ได้ ({str(e)})",
            "status": "error"
        }

