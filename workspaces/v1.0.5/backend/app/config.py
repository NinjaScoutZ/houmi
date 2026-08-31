import os
import sys
from pathlib import Path
from typing import Any

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# ─── CUDA & Nvidia DLL Auto-Registration for Windows GPU Acceleration ──────
if sys.platform == "win32":
    try:
        import site
        for _site_pkg in site.getsitepackages():
            _nvidia_dir = os.path.join(_site_pkg, "nvidia")
            if os.path.isdir(_nvidia_dir):
                for _sub in os.listdir(_nvidia_dir):
                    _bin_dir = os.path.join(_nvidia_dir, _sub, "bin")
                    if os.path.isdir(_bin_dir):
                        try:
                            os.add_dll_directory(_bin_dir)
                        except Exception:
                            pass
                        if _bin_dir not in os.environ.get("PATH", ""):
                            os.environ["PATH"] = _bin_dir + ";" + os.environ.get("PATH", "")
    except Exception:
        pass

# ─── Path Resolution ────────────────────────────────────────────────────
# In PyInstaller frozen mode, we must separate:
#   1. BUNDLE_DIR  – read-only assets extracted by PyInstaller (_MEIPASS)
#   2. APP_DIR     – writable directory next to the .exe for user data
# In development mode, both resolve relative to the source tree.

_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    # PyInstaller frozen runtime
    _MEIPASS = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # Install directories may be read-only. Keep user projects and SQLite in
    # the per-user AppData location so updates cannot erase or block writes.
    _default_user_data = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    ) / "Houmi Studio"
    APP_DIR = Path(os.environ.get("HOUMI_APP_DATA_DIR", _default_user_data))
    BASE_DIR = _MEIPASS / "backend"                # bundled backend code
else:
    env_app_dir = os.environ.get("HOUMI_WORKSPACE_DIR") or os.environ.get("HOUMI_APP_DIR")
    if env_app_dir:
        APP_DIR = Path(env_app_dir).resolve()
        BASE_DIR = APP_DIR / "backend" if (APP_DIR / "backend").exists() else APP_DIR
    else:
        APP_DIR = Path(__file__).resolve().parent.parent.parent   # project root (e:\houmi)
        BASE_DIR = Path(__file__).resolve().parent.parent         # backend dir

# ─── Runtime & User Data (writable) ────────────────────────────────────
DATA_DIR = Path(os.environ.get("HOUMI_DATA_DIR")).resolve() if os.environ.get("HOUMI_DATA_DIR") else APP_DIR / "data"
dynamic_patch_backend = DATA_DIR / "patches" / "current" / "backend"
if dynamic_patch_backend.exists():
    patch_str = str(dynamic_patch_backend)
    if patch_str not in sys.path:
        sys.path.insert(0, patch_str)

PROJECTS_DIR = DATA_DIR / "projects"
ASSET_STORAGE_DIR = DATA_DIR / "assets"
RUNTIME_MODE = os.environ.get("HOUMI_RUNTIME_MODE", "local").strip().lower()
if RUNTIME_MODE not in {"local", "host", "worker", "admin"}:
    raise RuntimeError(
        "HOUMI_RUNTIME_MODE must be one of: local, host, worker, admin"
    )

_default_database_url = f"sqlite:///{DATA_DIR}/houmi.db"
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    if RUNTIME_MODE in {"host", "worker", "admin"}:
        raise RuntimeError(
            "DATABASE_URL is required in host/worker/admin mode; refusing to fall back to SQLite"
        )
    DATABASE_URL = _default_database_url

# Schema creation is retained only for the existing Local desktop workflow.
# Host deployments must run Alembic explicitly before starting the service.
AUTO_CREATE_SCHEMA = (
    os.environ.get(
        "HOUMI_AUTO_CREATE_SCHEMA",
        "1" if RUNTIME_MODE == "local" else "0",
    ).strip().lower()
    in {"1", "true", "yes", "on"}
)

# ─── Bundled Assets (read-only in frozen mode) ──────────────────────────
_models_candidates = [
    BASE_DIR / "models",
    APP_DIR / "models",
    Path(sys.executable).parent / "models",
    Path(sys.executable).parent.parent / "backend" / "models",
    Path(r"E:\houmi\backend\models"),
]
MODELS_DIR = next((p for p in _models_candidates if p.exists()), BASE_DIR / "models")

# Port and server setup.  Desktop defaults remain loopback; a deployment can
# still place the host behind a reverse proxy and keep FastAPI private.
HOST = os.environ.get("HOUMI_HOST", "127.0.0.1")
PORT = int(os.environ.get("HOUMI_PORT", "4000"))
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.environ.get(
        "HOUMI_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
# Tauri v2 hosts packaged frontend assets on tauri.localhost.  Keep both
# schemes because the desktop configuration may opt into the HTTPS scheme.
# Desktop clients also need to call Central Server directly for auth.
CORS_ORIGINS = list(dict.fromkeys(CORS_ORIGINS + [
    "http://tauri.localhost",
    "https://tauri.localhost",
    "https://houmi.click",
    "http://localhost:4000",
    "http://127.0.0.1:4000",
    "http://localhost:4317",
    "http://127.0.0.1:4317",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]))

# Authentication configuration. Host-like runtimes must provide a secret;
# Local development gets an explicit, non-production fallback so existing
# desktop tests and first-run workflows remain usable.
JWT_SECRET = os.environ.get("HOUMI_JWT_SECRET")
if not JWT_SECRET:
    if RUNTIME_MODE in {"host", "worker", "admin"}:
        raise RuntimeError(
            "HOUMI_JWT_SECRET is required in host/worker/admin mode"
        )
    JWT_SECRET = "local-development-only-change-me"

JWT_ALGORITHM = os.environ.get("HOUMI_JWT_ALGORITHM", "HS256")
JWT_ISSUER = os.environ.get("HOUMI_JWT_ISSUER", "houmi")
ACCESS_TOKEN_TTL_MINUTES = int(os.environ.get("HOUMI_ACCESS_TOKEN_TTL_MINUTES", "15"))
REFRESH_TOKEN_TTL_DAYS = int(os.environ.get("HOUMI_REFRESH_TOKEN_TTL_DAYS", "30"))
WORKER_SHARED_SECRET = os.environ.get("HOUMI_WORKER_SHARED_SECRET")
if not WORKER_SHARED_SECRET:
    if RUNTIME_MODE in {"host", "worker", "admin"}:
        raise RuntimeError("HOUMI_WORKER_SHARED_SECRET is required in host/worker/admin mode")
    WORKER_SHARED_SECRET = "local-worker-development-only-change-me"

USER_STORAGE_QUOTA_BYTES = int(
    os.environ.get("HOUMI_USER_STORAGE_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))
)
MAX_ACTIVE_REMOTE_JOBS_PER_USER = int(
    os.environ.get("HOUMI_MAX_ACTIVE_REMOTE_JOBS_PER_USER", "2")
)

# ─── DOBKLE Cloud Hub Configuration ───────────────────────────────────────
HOUMI_CLOUD_ENABLED = os.environ.get("HOUMI_CLOUD_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
HOUMI_CLOUD_API_KEYS = [
    k.strip()
    for k in os.environ.get("HOUMI_CLOUD_API_KEYS", "dobkle_master_key,houmi_default_key").split(",")
    if k.strip()
]
HOUMI_CLOUD_MAX_OCR_CONCURRENCY = int(os.environ.get("HOUMI_CLOUD_MAX_OCR_CONCURRENCY", "4"))
HOUMI_CLOUD_MAX_CLEAN_CONCURRENCY = int(os.environ.get("HOUMI_CLOUD_MAX_CLEAN_CONCURRENCY", "2"))
HOUMI_CLOUD_MAX_PAYLOAD_MB = int(os.environ.get("HOUMI_CLOUD_MAX_PAYLOAD_MB", "50"))

# OCR Server Subprocess Config
OCR_SERVER_DIR = BASE_DIR / "ocr_server"
OCR_PORT = int(os.environ.get("OCR_PORT", "2322"))
OCR_HOST = "127.0.0.1"
OCR_API_URL = f"http://{OCR_HOST}:{OCR_PORT}/ocr"

# Model paths
BALLOON_MODEL_PATH = MODELS_DIR / "sao_balloon_beta" / "model.onnx"
BALLOON_CONFIG_PATH = MODELS_DIR / "sao_balloon_beta" / "model.json"
ACTIVE_LEARNED_MODEL_PATH = DATA_DIR / "models" / "active_learned" / "model.onnx"  # writable
_manga_inpaint_model = MODELS_DIR / "inpainting" / "lama_manga.onnx"
INPAINT_MODEL_PATH = _manga_inpaint_model if _manga_inpaint_model.exists() else (MODELS_DIR / "inpainting" / "lama.onnx")
MAT_MODEL_PATH = MODELS_DIR / "inpainting" / "mat.onnx"
MANGA_TEXT_SEG_MODEL_PATH = MODELS_DIR / "manga_text_segmentation" / "model.pth"
SAM_DIR = MODELS_DIR / "sam"
SAM_ENCODER_PATH = SAM_DIR / "sam2.1_hiera_base_plus.encoder.onnx"
SAM_DECODER_PATH = SAM_DIR / "sam2.1_hiera_base_plus.decoder.onnx"

# Standalone Rust PSD CLI path
_psd_candidates = [
    APP_DIR / "bin" / "houmi-psd-cli.exe",
    APP_DIR / "bin" / "manga-psd-cli.exe",
    BASE_DIR / "bin" / "houmi-psd-cli.exe",
    BASE_DIR / "bin" / "manga-psd-cli.exe",
    BASE_DIR.parent / "houmi-psd-cli" / "target" / "release" / "houmi-psd-cli.exe",
    BASE_DIR.parent / "manga-psd-cli" / "target" / "release" / "manga-psd-cli.exe",
]
PSD_CLI_PATH = next((p for p in _psd_candidates if p.exists()), _psd_candidates[0])

# Ensure crucial directories exist (writable dirs only)
for directory in [DATA_DIR, PROJECTS_DIR, ASSET_STORAGE_DIR, DATA_DIR / "models"]:
    directory.mkdir(parents=True, exist_ok=True)


# Execution Provider Configuration Mapping
EXECUTION_PROVIDER_MAP = {
    "CUDA": "CUDAExecutionProvider",
    "DirectML": "DmlExecutionProvider",
    "CPU": "CPUExecutionProvider",
    "cuda": "CUDAExecutionProvider",
    "directml": "DmlExecutionProvider",
    "cpu": "CPUExecutionProvider",
    "CUDAExecutionProvider": "CUDAExecutionProvider",
    "DmlExecutionProvider": "DmlExecutionProvider",
    "CPUExecutionProvider": "CPUExecutionProvider",
}

def get_execution_providers(provider: str | None = None) -> list[str]:
    """
    Returns ONNX Runtime execution provider list mapped from execution provider selection
    ('CUDA', 'DirectML', 'CPU') dynamically filtered against ONNX Runtime available providers.
    """
    import onnxruntime as ort
    try:
        avail = set(ort.get_available_providers())
    except Exception:
        avail = {"CPUExecutionProvider"}

    if not provider:
        provider = os.environ.get("HOUMI_EXECUTION_PROVIDER")
    if not provider:
        try:
            from app.services.ai_provider_settings import _load_raw_settings
            raw_settings = _load_raw_settings()
            provider = raw_settings.get("execution_provider")
        except Exception:
            pass
    if not provider:
        provider = "DirectML"

    raw_ep = str(provider).strip()
    primary_ep = EXECUTION_PROVIDER_MAP.get(raw_ep, "DmlExecutionProvider")

    if primary_ep == "CPUExecutionProvider":
        return ["CPUExecutionProvider"]

    candidates = [primary_ep, "DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
    providers = []
    for ep in candidates:
        if ep in avail and ep not in providers:
            providers.append(ep)

    if not providers:
        providers = ["CPUExecutionProvider"]
    return providers


def create_onnx_session_options(thread_limit: int | None = None) -> Any:
    """Create CPU-optimized ONNX SessionOptions for high-performance inference."""
    try:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.enable_cpu_mem_arena = True
        opts.enable_mem_pattern = True
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.log_severity_level = 3

        cpu_cores = os.cpu_count() or 4
        if thread_limit is None:
            try:
                from app.services.ai_provider_settings import _load_raw_settings
                raw_settings = _load_raw_settings()
                thread_limit = raw_settings.get("optimal_thread_count")
            except Exception:
                pass

        target_threads = int(thread_limit) if thread_limit is not None else max(2, cpu_cores)
        opts.intra_op_num_threads = target_threads
        opts.inter_op_num_threads = 1
        return opts
    except Exception:
        return None


LEGACY_SETTING_FALLBACKS = {
    "ocr_engine": ["ocr_model"],
    "inpaint_engine": ["active_inpaint_engine", "default_image_inpaint_method"],
    "execution_provider": ["gpu_execution_provider"],
    "project_dictionary": ["thai_dictionary"],
}

def get_project_setting(settings: dict | None, canonical_key: str, default: Any = None) -> Any:
    """
    Unified helper to retrieve setting value using canonical key with legacy fallback keys.
    Canonical -> Legacy mappings:
    - ocr_engine -> ocr_model
    - inpaint_engine -> active_inpaint_engine, default_image_inpaint_method
    - execution_provider -> gpu_execution_provider
    - project_dictionary -> thai_dictionary
    """
    if not settings or not isinstance(settings, dict):
        return default

    val = settings.get(canonical_key)
    if val is not None and val != "":
        return val

    for fallback_key in LEGACY_SETTING_FALLBACKS.get(canonical_key, []):
        val = settings.get(fallback_key)
        if val is not None and val != "":
            return val

    return default

def get_ocr_engine(settings: dict | None, default: str = "glm") -> str:
    val = get_project_setting(settings, "ocr_engine", default=default)
    return str(val) if val else default

def get_inpaint_engine(settings: dict | None, default: str = "LamaInpaint") -> str:
    val = get_project_setting(settings, "default_image_inpaint_method", default=get_project_setting(settings, "inpaint_engine", default=default))
    return str(val) if val else default

def get_execution_provider_setting(settings: dict | None, default: str | None = None) -> str | None:
    val = get_project_setting(settings, "execution_provider", default=default)
    return str(val) if val else default

def get_project_dictionary(settings: dict | None) -> list:
    val = get_project_setting(settings, "project_dictionary", default=[])
    if isinstance(val, (list, tuple)):
        return list(val)
    return []

# Global Smart Balloon Auto-Resize toggle (default False: opt-in for smart balloon shape fitting)
ENABLE_SMART_BALLOON = False

def get_enable_smart_balloon(settings: dict | None = None) -> bool:
    if settings and isinstance(settings, dict):
        if "enable_smart_balloon" in settings:
            return bool(settings["enable_smart_balloon"])
    return ENABLE_SMART_BALLOON


def get_smart_balloon_inset_ratio(settings: dict | None = None) -> float:
    """Returns safe inset ratio (clamped between 0.05 and 0.25, default 0.075).

    Default moved 0.10 -> 0.075 after the typesetting-level A/B benchmark
    (952 paired configs, 120 records, glyph-pixel containment vs SAM GT):
    +1.4px mean font size (481 bigger / 0 smaller) at -0.0002 containment on
    audit-HIGH ground truth. See docs/reports/smart_balloon_v16_alignment_report.md.
    """
    if settings and isinstance(settings, dict):
        if "smart_balloon_inset_ratio" in settings:
            try:
                val = float(settings["smart_balloon_inset_ratio"])
                return max(0.05, min(0.25, val))
            except (ValueError, TypeError):
                pass
    return 0.075


def get_smart_balloon_adaptive_enabled(settings: dict | None = None) -> bool:
    """
    Enable Smart Balloon V16 Adaptive Enhancement for non-white backgrounds.

    V16 Features:
    - Adaptive white threshold based on local background analysis
    - Multi-seed flood fill for better coverage
    - Weak edge reinforcement for faint balloon strokes
    - Extended padding for protruding tails

    Default: False (opt-in). GT-scored benchmark (263 masks, SAM-generated)
    shows V15 wins IoU on 42 records vs 8 for V16 with ~+52ms median cost,
    so adaptive stays off unless a project has gray/gradient-heavy pages.
    Enable per project via {"smart_balloon_adaptive": true}.
    """
    if settings and isinstance(settings, dict):
        if "smart_balloon_adaptive" in settings:
            return bool(settings["smart_balloon_adaptive"])
    return False
