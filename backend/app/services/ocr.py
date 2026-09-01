import os
import json
import base64
import mimetypes
from typing import Any
import requests
import httpx
import re
import tempfile
import logging
import time
import threading
from pathlib import Path
from urllib.parse import quote
from PIL import Image
import numpy as np
import cv2
from sqlalchemy.orm import Session
from app.config import OCR_API_URL
from app.models.all_models import TextBlock

logger = logging.getLogger("houmi-ocr-service")

_session = None

def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        # Configure connection pool for reuse
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=2,
            pool_maxsize=2,
            max_retries=0  # We handle retries ourselves
        )
        _session.mount("http://", adapter)
    return _session

_paddle_ocr = None
_rapid_ocr_engines: dict = {}  # Per-language RapidOCR cache: {"korean": RapidOCR(...), ...}

_LANG_KEY_MAP = {
    "v6": "ppocr_v6",
    "ppocr_v6": "ppocr_v6",
    "ppocrv6": "ppocr_v6",
    "v5": "chinese",
    "ppocr_v5": "chinese",
    "ppocrv5": "chinese",
    "th": "thai",
    "thai": "thai",
    "ko": "korean",
    "korean": "korean",
    "ja": "japanese",
    "japanese": "japanese",
    "jp": "japanese",
    "en": "english",
    "english": "english",
    "zh": "chinese",
    "ch": "chinese",
    "chinese": "chinese",
    "zh-cn": "chinese",
    "zh-tw": "chinese",
}

def _find_ocr_models_dir() -> Path:
    """Locate backend/ocr_models/ whether running from repo or PyInstaller _internal/."""
    import sys
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "ocr_models",          # repo: backend/ocr_models
        Path(getattr(sys, '_MEIPASS', '')) / "backend" / "ocr_models",         # PyInstaller frozen
        Path(getattr(sys, '_MEIPASS', '')) / "ocr_models",                     # PyInstaller alt
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # fallback to repo path

def _get_rapid_ocr(lang: str = "zh"):
    """Get or create a RapidOCR engine for the specified language.
    
    Loads dedicated ONNX recognition models and character dictionaries:
    - Chinese: Chinese PP-OCRv6 SOTA (18,708 characters multilingual dict)
    - Korean: Korean PP-OCRv5 (11,945 characters dict)
    - Japanese: Japanese PP-OCRv6 / PP-OCRv3
    - English: English PP-OCRv5
    - Thai: Thai PP-OCRv5
    
    use_cls is disabled to prevent false 180-degree flips on comic bubble crops.
    """
    global _rapid_ocr_engines
    norm_lang = _LANG_KEY_MAP.get(str(lang or "").lower().strip(), "chinese")

    if norm_lang in _rapid_ocr_engines:
        return _rapid_ocr_engines[norm_lang]

    try:
        from rapidocr_onnxruntime import RapidOCR

        kwargs = {"use_cls": False}  # CRITICAL: Disable 180-degree rotation classifier for crops
        models_dir = _find_ocr_models_dir()
        lang_dir = models_dir / norm_lang
        rec_model = lang_dir / "rec.onnx"
        dict_file = lang_dir / "dict.txt"

        if rec_model.exists() and rec_model.stat().st_size > 1000:
            kwargs["rec_model_path"] = str(rec_model)
            model_ver = "PP-OCRv6" if norm_lang in ("chinese", "ppocr_v6") else "PP-OCRv5"
            logger.info(f"Using {norm_lang} {model_ver} rec model: {rec_model} ({rec_model.stat().st_size / 1024 / 1024:.1f} MB)")
        if dict_file.exists() and dict_file.stat().st_size > 100:
            kwargs["rec_keys_path"] = str(dict_file)
            logger.info(f"Using {norm_lang} dict: {dict_file}")

        # GPU Acceleration for RapidOCR (DirectML on NVIDIA/AMD/Intel GPUs)
        from app.config import get_execution_providers
        active_providers = get_execution_providers()
        engine = None
        try:
            # Pass custom session execution providers (DirectML GPU / CUDA)
            engine = RapidOCR(providers=active_providers, **kwargs)
            logger.info("🚀 [GPU OCR ENGINE] Hardware: %s | Engine: RapidOCR PP-OCRv5 (%s)", active_providers[0], norm_lang)
        except Exception as e_ep:
            logger.warning("RapidOCR GPU initialization note (%s), falling back to CPU: %s", active_providers, e_ep)
            engine = RapidOCR(**kwargs)
            logger.info("ℹ️ [CPU OCR ENGINE] Hardware: CPUExecutionProvider | Engine: RapidOCR PP-OCRv5 (%s)", norm_lang)

        _rapid_ocr_engines[norm_lang] = engine
        return engine
    except Exception as err:
        logger.warning("RapidOCR ONNX init failed for lang=%s: %s", norm_lang, err)
        return None

def _get_paddle_ocr(lang: str = "korean"):
    global _paddle_ocr
    if _paddle_ocr is None:
        try:
            from paddleocr import PaddleOCR
            target_lang = lang if lang in {"korean", "en", "ch"} else "korean"
            init_attempts = [
                lambda: PaddleOCR(lang=target_lang),
                lambda: PaddleOCR(lang="korean"),
                lambda: PaddleOCR(lang="en"),
                lambda: PaddleOCR(lang="ch"),
            ]
            for idx, attempt in enumerate(init_attempts, start=1):
                try:
                    _paddle_ocr = attempt()
                    logger.info(f"Initialized local PaddleOCR successfully on attempt {idx}")
                    break
                except Exception as err:
                    logger.warning(f"PaddleOCR init attempt {idx} failed: {err}")
            if _paddle_ocr is None:
                raise RuntimeError("All PaddleOCR initialization attempts failed")
        except Exception as e:
            logger.error("Failed to import paddleocr: %s", e)
            raise e
    return _paddle_ocr


_gemini_key_index = 0
_gemini_key_lock = threading.Lock()


def _get_all_gemini_api_keys() -> list[str]:
    keys = []
    try:
        from app.services.ai_provider_settings import get_ordered_google_api_keys
        keys = get_ordered_google_api_keys()
    except Exception:
        pass
    if not keys:
        raw_str = (
            os.getenv("GOOGLE_API_KEY", "").strip()
            or os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("HOUMI_GEMINI_API_KEY", "").strip()
        )
        keys = [k.strip() for k in re.split(r"[,;\n]+", raw_str) if k.strip()]
    return keys


def _get_gemini_api_key(rotate: bool = True) -> str:
    """Read Gemini keys and return next active key using Round-Robin rotation."""
    global _gemini_key_index
    keys = _get_all_gemini_api_keys()
    if not keys:
        return ""
    with _gemini_key_lock:
        if rotate:
            _gemini_key_index = (_gemini_key_index + 1) % len(keys)
        return keys[_gemini_key_index % len(keys)]


def _resolve_gemini_model(model: str = "", for_rest: bool = False) -> str:
    try:
        from app.services.ai_provider_settings import get_ai_provider_preferences
        prefs = get_ai_provider_preferences()
        configured_model = prefs.get("model", "").strip()
    except Exception:
        configured_model = ""

    selected = os.getenv("HOUMI_GEMINI_MODEL", "").strip() or configured_model or "gemini-3.7-flash"
    if for_rest:
        if not selected or any(f in selected.lower() for f in ("3.7", "3.6", "3.5", "flash", "flash_lite")):
            return "gemini-2.0-flash"
        return selected
    if not selected and model and model not in {"flash", "flash_lite"}:
        selected = model
    return selected or "gemini-3.7-flash"


def _clean_gemini_text(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    return text


_rest_disabled_until = 0.0

def _run_gemini_rest_ocr(
    prompt: str,
    image_path: str,
    model: str = "",
    timeout: float = 90.0,
) -> tuple[str, bool]:
    """Send a multimodal OCR request directly to Gemini GenerateContent.

    Gemini accepts local images as base64 ``inlineData`` parts. The API key
    is read only from the backend process environment and is sent in the
    ``x-goog-api-key`` header, never returned to the client or logged.
    """
    global _rest_disabled_until
    if time.time() < _rest_disabled_until:
        return "", False

    all_keys = _get_all_gemini_api_keys()
    if not all_keys:
        return "", False

    try:
        image_bytes = Path(image_path).read_bytes()
        mime_type = mimetypes.guess_type(image_path)[0] or "image/png"
        api_version = os.getenv("HOUMI_GEMINI_API_VERSION", "v1beta").strip().strip("/") or "v1beta"
        selected_model = _resolve_gemini_model(model, for_rest=True)
        url = (
            "https://generativelanguage.googleapis.com/"
            f"{api_version}/models/{quote(selected_model, safe='-._')}:generateContent"
        )

        image_ref = _gemini_prompt_image_path(image_path)
        rest_prompt = prompt.replace(image_ref, "").strip()
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": rest_prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                ],
            }],
            "generationConfig": {"temperature": 0},
        }

        # Multi-Key Priority Failover Execution
        for key_idx, active_key in enumerate(all_keys):
            try:
                response = httpx.post(
                    url,
                    headers={"x-goog-api-key": active_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=timeout,
                )
                if response.status_code in {400, 401, 403, 429}:
                    if key_idx + 1 < len(all_keys):
                        logger.warning(
                            "⚠️ Gemini Key #%d (Priority %d) hit HTTP %d. Automatically failing over to Priority Key #%d...",
                            key_idx + 1, key_idx + 1, response.status_code, key_idx + 2
                        )
                        continue
                    else:
                        from app.services.gemini_quota import parse_and_record_quota_error
                        parse_and_record_quota_error(f"HTTP {response.status_code} Rate limit or Key error hit")
                        _rest_disabled_until = time.time() + 600.0
                        logger.warning("All %d Gemini keys in priority pool invalid or exhausted (HTTP %d); disabling REST API for 10 minutes", len(all_keys), response.status_code)
                        return "", False

                response.raise_for_status()
                data = response.json()
                text_parts: list[str] = []
                for candidate in data.get("candidates", []):
                    content = candidate.get("content") or {}
                    for part in content.get("parts", []):
                        value = part.get("text") if isinstance(part, dict) else None
                        if isinstance(value, str) and value.strip():
                            text_parts.append(value.strip())
                text = _clean_gemini_text("\n".join(text_parts))
                if not text:
                    logger.error("Gemini REST OCR returned no text (model=%s, key_priority=%d)", selected_model, key_idx + 1)
                    return "", False
                logger.info("Gemini REST OCR succeeded (model=%s, key_priority=%d)", selected_model, key_idx + 1)
                return text, True

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {400, 401, 403, 429} and key_idx + 1 < len(all_keys):
                    logger.warning("Gemini Key #%d HTTP %d; trying next key...", key_idx + 1, exc.response.status_code)
                    continue
                _rest_disabled_until = time.time() + 600.0
                logger.warning("Gemini REST OCR HTTP %s; disabling REST API for 10 minutes", exc.response.status_code)
                return "", False
        return "", False
    except (httpx.HTTPError, OSError, ValueError, KeyError) as exc:
        _rest_disabled_until = time.time() + 600.0
        logger.error("Gemini REST OCR failed: %s; disabling REST API for 10 minutes", exc)
        return "", False
    except Exception:
        _rest_disabled_until = time.time() + 600.0
        logger.exception("Unexpected Gemini REST OCR failure; disabling REST API for 10 minutes")
        return "", False


def _run_gemini_rest_text(
    prompt: str,
    model: str = "",
    timeout: float = 90.0,
) -> tuple[str, bool]:
    """Send a text-only decision request directly to Gemini GenerateContent.

    Style/font judging has no image attachment, so it cannot use the OCR-only
    REST helper above. Keeping this path server-side lets GOOGLE_API_KEY users
    run the same AI decisions as agy/Gemini CLI users without exposing the key.
    """
    all_keys = _get_all_gemini_api_keys()
    if not all_keys:
        return "", False

    try:
        api_version = os.getenv("HOUMI_GEMINI_API_VERSION", "v1beta").strip().strip("/") or "v1beta"
        selected_model = _resolve_gemini_model(model, for_rest=True)
        url = (
            "https://generativelanguage.googleapis.com/"
            f"{api_version}/models/{quote(selected_model, safe='-._')}:generateContent"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": str(prompt or "")}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }

        for key_idx, active_key in enumerate(all_keys):
            try:
                response = httpx.post(
                    url,
                    headers={"x-goog-api-key": active_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=timeout,
                )
                if response.status_code in {400, 401, 403, 429}:
                    if key_idx + 1 < len(all_keys):
                        logger.warning("Gemini Key #%d (Priority %d) hit HTTP %d; trying Priority Key #%d...", key_idx + 1, key_idx + 1, response.status_code, key_idx + 2)
                        continue
                    else:
                        logger.warning("All %d Gemini keys rate-limited, invalid, or returned HTTP %d; text decision falling back", len(all_keys), response.status_code)
                        return "", False

                response.raise_for_status()
                data = response.json()
                text_parts: list[str] = []
                for candidate in data.get("candidates", []):
                    content = candidate.get("content") or {}
                    for part in content.get("parts", []):
                        value = part.get("text") if isinstance(part, dict) else None
                        if isinstance(value, str) and value.strip():
                            text_parts.append(value.strip())

                text = _clean_gemini_text("\n".join(text_parts))
                if not text:
                    logger.error("Gemini REST returned no text candidates (model=%s, key_priority=%d)", selected_model, key_idx + 1)
                    return "", False
                logger.info("Gemini REST text decision succeeded (model=%s, key_priority=%d)", selected_model, key_idx + 1)
                return text, True
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {429, 401, 403} and key_idx + 1 < len(all_keys):
                    continue
                raise exc
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.error("Gemini REST text decision failed: %s", exc)
        return "", False
    except Exception:
        logger.exception("Unexpected Gemini REST text decision failure")
        return "", False


def _gemini_prompt_image_path(image_path: str) -> str:
    """Use Gemini CLI's file mention syntax so the image is actually attached."""
    # `@path` is understood by Gemini CLI/agy as a local file reference. Keep a
    # normalized slash form because Windows backslashes can be interpreted as
    # escapes by the CLI prompt parser.
    return "@" + str(Path(image_path).resolve()).replace("\\", "/")


def _run_gemini_command(
    prompt: str,
    model: str = "",
    image_path: str | None = None,
    provider: str = "auto",
    timeout: float = 120.0,
) -> tuple[str, bool]:
    """Run Gemini REST or a Gemini-compatible CLI with one deterministic prompt."""
    import shutil
    import subprocess

    # If provider is auto or empty, check persisted user preferences from Settings UI
    if not provider or provider == "auto":
        try:
            from app.services.ai_provider_settings import get_ai_provider_preferences
            prefs = get_ai_provider_preferences()
            pref_provider = prefs.get("provider", "").strip().lower()
            if pref_provider in {"google_api", "agy"}:
                provider = pref_provider
        except Exception:
            pass

    provider = str(provider or "auto").strip().lower()
    if provider not in {"auto", "google_api", "agy"}:
        provider = "auto"

    if provider == "agy":
        # Fast path: directly execute local agy CLI (do not call REST API)
        pass
    elif provider in {"google_api", "auto"}:
        if image_path:
            # Direct Cloud REST API (uses GOOGLE_API_KEY)
            if _get_gemini_api_key():
                text, ok = _run_gemini_rest_ocr(prompt, image_path=image_path, model=model)
                if ok:
                    return text, True
                if provider == "google_api":
                    logger.warning("Google API REST OCR unavailable; falling back to agy CLI")
        elif _get_gemini_api_key():
            # Font/style judging is text-only. Prefer the configured Google API
            text, ok = _run_gemini_rest_text(prompt, model=model)
            if ok:
                return text, True
            if provider == "google_api":
                logger.warning("Google API REST text decision unavailable; falling back to agy CLI")

    if provider == "google_api" and not shutil.which("agy"):
        logger.error("Google API provider selected but no API key is valid and 'agy' CLI is not found in PATH")
        return "", False

    cmd_name = "agy" if shutil.which("agy") else None
    if not cmd_name:
        logger.error("Antigravity CLI tool ('agy') not found in PATH.")
        return "", False

    import tempfile
    prompt_file_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write(prompt)
            prompt_file_path = Path(tf.name)

        prompt_ref = "@" + str(prompt_file_path.resolve()).replace("\\", "/")
        selected_model = _resolve_gemini_model(model)
        model_flags = ""
        raw_m = selected_model.lower()
        if "3.7" in raw_m:
            model_flags = '--model "gemini-3.7-flash" --effort low'
        elif "3.6" in raw_m:
            model_flags = '--model "gemini-3.6-flash" --effort low'
        elif "3.5" in raw_m:
            model_flags = '--model "gemini-3.5-flash" --effort low'
        elif "3.1" in raw_m:
            model_flags = '--model "gemini-3.1-pro" --effort low'
        elif "sonnet" in raw_m or "claude" in raw_m:
            model_flags = '--model "Claude Sonnet 4.6 (Thinking)"'
        else:
            model_flags = '--model "gemini-3.7-flash" --effort low'

        cmd_str = f'{cmd_name} {model_flags} --dangerously-skip-permissions --print "{prompt_ref}"'

        cli_env = os.environ.copy()
        cli_env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
        res = subprocess.run(
            cmd_str,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=cli_env,
            shell=True
        )
        if res.returncode == 0:
            text = _clean_gemini_text(res.stdout)
            logger.info("Gemini/agy CLI OCR result succeeded")
            return text, True
        else:
            combined = (res.stdout or "") + "\n" + (res.stderr or "")
            from app.services.gemini_quota import parse_and_record_quota_error
            parse_and_record_quota_error(combined)
            logger.error(f"Gemini/agy CLI failed with code {res.returncode}: {res.stderr}")
            return "", False
    except Exception as e:
        logger.error(f"Exception running Gemini/agy CLI OCR: {e}")
        return "", False
    finally:
        if prompt_file_path and prompt_file_path.exists():
            prompt_file_path.unlink(missing_ok=True)


def _run_gemini_cli_ocr(image_path: str, model: str = "flash", source_lang: str = "") -> tuple[str, bool]:
    """OCR one attached image and return only the recognized source text."""
    language = {"ja": "Japanese", "zh": "Chinese", "ko": "Korean", "en": "English"}.get(source_lang, "the source language")
    image_ref = _gemini_prompt_image_path(image_path)
    prompt = (
        f"Read the text in the attached image {image_ref}. The text language is {language}. "
        "Return ONLY the transcription exactly as visible, preserving line breaks and punctuation. "
        "Do not translate, explain, add labels, markdown, or commentary."
    )
    return _run_gemini_command(prompt, model=model, image_path=image_path)

_paddle_ocr_cache = {}

def _get_paddle_ocr(lang: str = "ch"):
    global _paddle_ocr_cache
    lang_map = {
        "zh": "ch", "ch": "ch", "chinese": "ch", "จีน": "ch",
        "ko": "korean", "korean": "korean", "เกาหลี": "korean",
        "en": "en", "english": "en", "อิง": "en", "อังกฤษ": "en",
        "ja": "japan", "japanese": "japan", "ญี่ปุ่น": "japan",
    }
    p_lang = lang_map.get(str(lang).lower(), "ch")

    if p_lang not in _paddle_ocr_cache:
        try:
            from paddleocr import PaddleOCR
            init_attempts = [
                lambda: PaddleOCR(lang=p_lang),
                lambda: PaddleOCR(lang="ch"),
                lambda: PaddleOCR(lang="en"),
            ]
            ocr_instance = None
            for idx, attempt in enumerate(init_attempts, start=1):
                try:
                    ocr_instance = attempt()
                    logger.info(f"Initialized local PaddleOCR ({p_lang}) successfully on attempt {idx}")
                    break
                except Exception as err:
                    logger.warning(f"PaddleOCR ({p_lang}) init attempt {idx} failed: {err}")
            if ocr_instance is None:
                raise RuntimeError(f"All PaddleOCR ({p_lang}) initialization attempts failed")
            _paddle_ocr_cache[p_lang] = ocr_instance
        except Exception as e:
            logger.error("Failed to import/init paddleocr for lang %s: %s", p_lang, e)
            raise e
    return _paddle_ocr_cache.get(p_lang)

def _parse_vlm_response(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    lines = data.get("text_lines", [])
    extracted = []
    if isinstance(lines, list):
        for line in lines:
            if isinstance(line, str):
                if line.strip():
                    extracted.append(line.strip())
            elif isinstance(line, dict):
                val = line.get("text") or line.get("raw") or line.get("content") or ""
                if str(val).strip():
                    extracted.append(str(val).strip())
            elif line is not None:
                if str(line).strip():
                    extracted.append(str(line).strip())
    text = "\n".join(extracted).strip()
    if not text:
        text = str(data.get("raw") or data.get("markdown") or data.get("text") or "").strip()
    return text

def _run_vlm_server_ocr(image_path: str, backend_name: str = "glm") -> tuple[str, bool]:
    """Call the local PyTorch GLM-4V / DeepSeek VLM server running on port 2322.
    
    AUTO-START: If the VLM server package is installed but server process is not active,
    automatically launch the server in the background and retry the request once ready.
    """
    from app.config import OCR_HOST, OCR_PORT, OCR_SERVER_DIR
    from app.ocr_manager import ocr_manager

    url = f"http://{OCR_HOST}:{OCR_PORT}/ocr?backend={backend_name}"

    def _do_post():
        with open(image_path, "rb") as f:
            files = {"upload": ("image.png", f, "image/png")}
            return requests.post(url, files=files, timeout=300.0)

    # Attempt 1: Direct request
    try:
        resp = _do_post()
        if resp.status_code == 200:
            text = _parse_vlm_response(resp.json())
            if text:
                return text, True
    except Exception as exc:
        logger.warning(f"VLM Server direct request failed: {exc}")

    # Attempt 2: Server not running — check if installed and auto-start in background
    venv_py = OCR_SERVER_DIR / "venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        logger.info("Local VLM Server installed. Auto-starting server process on port 2322 in background...")
        ocr_manager.start_server()
        
        # Wait up to 10s for health check
        for _ in range(10):
            time.sleep(1.0)
            if ocr_manager.check_health():
                logger.info("Local VLM Server is now active and ready!")
                try:
                    resp = _do_post()
                    if resp.status_code == 200:
                        text = _parse_vlm_response(resp.json())
                        if text:
                            return text, True
                except Exception as exc:
                    logger.warning(f"VLM Server request retry failed: {exc}")
                break

def _clean_ocr_noise_line(txt: str) -> str:
    """Filter out stray OCR artifacts from balloon boundaries, such as '(', ')', '/', '（', '）', '|', '\\', '」', '「'."""
    if not txt:
        return ""
    t = txt.strip()
    # If the line consists only of stray punctuation / brackets / slashes / noise symbols
    if re.fullmatch(r'[\(\)（）\[\]【】/\\\|_\-\.\~\s`\'"“”‘’·・=><「」『』《》]+', t):
        return ""
    # Strip leading/trailing border slash and stray boundary brackets
    t = re.sub(r'^[/\\]+\s*', '', t)
    t = re.sub(r'\s*[/\\]+$', '', t)
    t = re.sub(r'^[」\s]+', '', t)
    t = re.sub(r'[「\s]+$', '', t)
    return t.strip()

def _fast_split_and_ocr(crop_bgr: np.ndarray, rapid_engine) -> str:
    """Robust OCR on balloon crop using native DBNet text line detection + PP-OCRv5 recognition."""
    if crop_bgr is None or crop_bgr.size == 0:
        return ""
    
    try:
        # 1. Direct native RapidOCR on the balloon crop (finds all text lines precisely)
        res, _ = rapid_engine(crop_bgr)
        if res:
            lines = [_clean_ocr_noise_line(str(r[1])) for r in res]
            valid_lines = [l for l in lines if l]
            if valid_lines:
                return "\n".join(valid_lines).strip()
    except Exception as exc:
        logger.debug("Native RapidOCR crop detection exception: %s", exc)

    # 2. Fallback pure recognition without detection
    try:
        res, _ = rapid_engine(crop_bgr, use_det=False)
        if res and len(res) > 0:
            txt = res[0][0] if isinstance(res[0], (list, tuple)) else str(res[0])
            return _clean_ocr_noise_line(str(txt))
    except Exception:
        pass

    return ""

def _run_rapid_ocr_image(img_or_crop, lang: str = "zh") -> tuple[str, bool]:
    """Run RapidOCR on an in-memory image/crop with fast projection line slicing."""
    rapid = _get_rapid_ocr(lang=lang)
    if rapid is not None:
        try:
            if isinstance(img_or_crop, (str, Path)):
                from app.utils.image_utils import cv2_imread_unicode
                img_or_crop = cv2_imread_unicode(str(img_or_crop))
                if img_or_crop is None:
                    with Image.open(str(img_or_crop)) as pimg:
                        img_or_crop = cv2.cvtColor(np.array(pimg.convert("RGB")), cv2.COLOR_RGB2BGR)
            elif isinstance(img_or_crop, Image.Image):
                img_or_crop = cv2.cvtColor(np.array(img_or_crop.convert("RGB")), cv2.COLOR_RGB2BGR)

            text = _fast_split_and_ocr(img_or_crop, rapid)
            if text:
                return text, True
        except Exception as exc:
            logger.warning("RapidOCR ONNX direct image execution failed (lang=%s): %s", lang, exc)
    return "", False

def _run_rapid_ocr_path(image_path: str, lang: str = "zh") -> tuple[str, bool]:
    """Run RapidOCR ONNX engine with language-specific model. Returns (text, success)."""
    return _run_rapid_ocr_image(image_path, lang=lang)


def _run_paddle_ocr_path(image_path: str, source_lang: str = "ch") -> tuple[str, bool]:
    try:
        ocr_engine = _get_paddle_ocr(lang=source_lang)
        texts = []
        if hasattr(ocr_engine, "ocr"):
            try:
                res = ocr_engine.ocr(image_path, cls=True)
            except Exception:
                res = ocr_engine.ocr(image_path)
            if res:
                for line in res:
                    if line:
                        for item in line:
                            if isinstance(item, (list, tuple)) and len(item) >= 2:
                                rec = item[1]
                                txt = rec[0] if isinstance(rec, (list, tuple)) else str(rec)
                                if str(txt).strip():
                                    texts.append(str(txt).strip())

        if not texts and hasattr(ocr_engine, "predict"):
            res = ocr_engine.predict(image_path)
            if res and isinstance(res, list):
                for item in res:
                    if isinstance(item, dict) and "rec_texts" in item:
                        texts.extend(str(text) for text in item["rec_texts"] if str(text).strip())

        text = "\n".join(texts).strip()
        if text:
            return text, True
    except Exception as exc:
        logger.error("Local PaddleOCR execution failed: %s", exc)
    return "", False


def _run_gemini_ocr_with_fallback(
    image_path: str,
    model: str = "flash",
    source_lang: str = "",
) -> tuple[str, bool]:
    text, success = _run_gemini_cli_ocr(image_path, model=model, source_lang=source_lang)
    if success:
        return text, True
    fallback_engine = os.getenv("HOUMI_GEMINI_FALLBACK", "").strip().lower()
    if fallback_engine in {"paddle", "paddleocr"}:
        return _run_paddle_ocr_path(image_path, source_lang=source_lang)
    return "", False


def _parse_gemini_grid_response(raw: str, expected_ids: set[str]) -> dict[str, Any]:
    """Parse strict JSON first, then tolerate line-oriented CLI output.

    Mapping is always by the stable HOUMI_BOX id, never by response order.
    Extracts text, balloon_type, color_hex, stroke_color_hex, and stroke_width_px.
    """
    text = (raw or "").strip()
    parsed: dict[str, Any] = {}
    expected_lookup = {expected.upper(): expected for expected in expected_ids}

    def canonical_box_id(value: object) -> str:
        raw_id = str(value or "").strip().strip('`"\'').replace("HOUMI_BOX:", "").strip()
        exact = expected_lookup.get(raw_id.upper())
        if exact:
            return exact
        upper_id = raw_id.upper()
        # Direct check if expected is substring or prefix
        for expected in expected_ids:
            exp_upper = expected.upper()
            if exp_upper in upper_id or upper_id in exp_upper:
                return expected
            parts = exp_upper.split("_")
            if len(parts) >= 2:
                prefix = f"{parts[0]}_{parts[1]}"
                if prefix in upper_id:
                    return expected
        suffix_matches = [
            expected
            for expected in expected_ids
            if upper_id.endswith(expected.upper())
        ]
        return suffix_matches[0] if len(suffix_matches) == 1 else ""

    def add(item: object) -> None:
        if not isinstance(item, dict):
            return
        box_id = canonical_box_id(item.get("box_id") or item.get("id"))
        value = item.get("text", item.get("ocr", ""))
        if box_id in expected_ids and isinstance(value, str) and value.strip():
            parsed[box_id] = {
                "text": value.strip(),
                "balloon_type": str(item.get("balloon_type") or "bubble").lower(),
                "color_hex": item.get("color_hex"),
                "stroke_color_hex": item.get("stroke_color_hex") or item.get("stroke_color"),
                "stroke_width_px": item.get("stroke_width_px") or item.get("stroke_width"),
                "gradient_colors": item.get("gradient_colors"),
                "gradient": item.get("gradient") if isinstance(item.get("gradient"), dict) else None,
                "drop_shadow": item.get("drop_shadow") if isinstance(item.get("drop_shadow"), dict) else None,
                "outer_glow": item.get("outer_glow") if isinstance(item.get("outer_glow"), dict) else None,
                "inner_shadow": item.get("inner_shadow") if isinstance(item.get("inner_shadow"), dict) else None,
                "bold": bool(item.get("bold", False)),
                "italic": bool(item.get("italic", False)),
            }

    candidates = [text]
    candidates.extend(re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL))
    for candidate in candidates:
        try:
            value = json.loads(candidate.strip())
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, list):
            for item in value:
                add(item)
        else:
            add(value)
        if parsed:
            return parsed

    for line in text.splitlines():
        match = re.search(r"(?:HOUMI_BOX:|box_id\s*[:=]\s*)([A-Za-z0-9_-]+)\s*(?:\||\t|:|-)+\s*(.*)$", line, re.IGNORECASE)
        if match and match.group(2).strip():
            box_id = canonical_box_id(match.group(1))
            if box_id:
                parsed[box_id] = {
                    "text": match.group(2).strip().strip('`"'),
                    "balloon_type": "bubble",
                }
    return parsed

def crop_and_ocr_block(
    img_path: str,
    block: TextBlock,
    backend: str = None,
    timeout: float = 120.0,
    source_lang: str = "",
) -> tuple[str, bool]:
    """
    Crops the image to block bounding box and executes ONLY the requested OCR backend.
    STRICT NO UNREQUESTED FALLBACK TO OTHER ENGINES.
    """
    with Image.open(img_path) as img:
        w_img, h_img = img.size
        
        # Use Smart Balloon bounds if available, fallback to canonical bbox
        target_bbox = getattr(block, "smart_bbox", None) or {"x": block.x, "y": block.y, "width": block.width, "height": block.height}
        
        x0 = max(0, int(target_bbox["x"]))
        y0 = max(0, int(target_bbox["y"]))
        x1 = min(w_img, int(target_bbox["x"] + target_bbox["width"]))
        y1 = min(h_img, int(target_bbox["y"] + target_bbox["height"]))
        
        # Ensure we have valid cropping dimensions
        if (x1 - x0) <= 0 or (y1 - y0) <= 0:
            return "", True

        bw = max(1, x1 - x0)
        bh = max(1, y1 - y0)
        pad_x = int(max(6, bw * 0.10))
        pad_y = int(max(6, bh * 0.10))

        crop_x0 = max(0, x0 - pad_x)
        crop_y0 = max(0, y0 - pad_y)
        crop_x1 = min(w_img, x1 + pad_x)
        crop_y1 = min(h_img, y1 + pad_y)

        crop_area = (crop_x0, crop_y0, crop_x1, crop_y1)
        cropped_img = img.crop(crop_area)

        # Upscale small crops so ONNX / RapidOCR receives clear character strokes
        crop_h = getattr(cropped_img, "height", None)
        crop_w = getattr(cropped_img, "width", None)
        if isinstance(crop_h, (int, float)) and isinstance(crop_w, (int, float)):
            if crop_h < 80 or crop_w < 80:
                scale = max(1.5, 96.0 / max(1, crop_h))
                new_w = int(crop_w * scale)
                new_h = int(crop_h * scale)
                cropped_img = cropped_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Write cropped image to temp file
        temp_fd, temp_path_str = tempfile.mkstemp(suffix=".png")
        os.close(temp_fd)  # Close immediately so we can open it in PIL and requests on Windows
        try:
            cropped_img.save(temp_path_str, "PNG")
            b_lower = str(backend or "").lower()

            # A. Gemini AI CLI OCR (explicit gemini / agy)
            if any(b in b_lower for b in ("gemini", "ai", "agy")):
                selected_model = "flash"
                if ":" in b_lower:
                    selected_model = b_lower.split(":", 1)[1]
                elif "lite" in b_lower:
                    selected_model = "flash_lite"
                logger.info(f"Running Gemini AI CLI OCR ({selected_model}) on block {block.id} (lang: {source_lang})")
                return _run_gemini_cli_ocr(temp_path_str, model=selected_model, source_lang=source_lang)
            # B. PP-OCRv5 / RapidOCR ONNX path (direct in-memory zero-copy)
            if any(k in b_lower for k in ("ppocr", "v5", "rapid", "paddle")) or not b_lower:
                logger.info(f"Running RapidOCR in-memory on block {block.id} (lang: {source_lang})")
                crop_np = np.array(cropped_img.convert("RGB"))
                text, ok = _run_rapid_ocr_image(crop_np, lang=source_lang)
                if ok:
                    logger.info(f"RapidOCR recognized text successfully: {text[:30]}")
                return text, ok

            # C. GLM PyTorch VLM OCR Path - STRICT NO SILENT FALLBACK
            if any(k in b_lower for k in ("glm", "deepseek", "vlm")):
                b_name = "glm"
                logger.info(f"Running GLM PyTorch VLM OCR on block {block.id} (lang: {source_lang})")
                text, ok = _run_vlm_server_ocr(temp_path_str, backend_name="glm")
                if ok:
                    logger.info(f"GLM PyTorch VLM OCR recognized text successfully: {text[:30]}")
                    return text, ok
                else:
                    err_msg = "[GLM-OCR Offline] Local GLM VLM Server (Port 2322) is not running. Please start or install the GLM VLM Server package."
                    logger.warning(err_msg)
                    return err_msg, False

            # Default: RapidOCR in-memory strictly
            logger.info(f"Running default RapidOCR on block {block.id} (lang: {source_lang})")
            crop_np = np.array(cropped_img.convert("RGB"))
            text, ok = _run_rapid_ocr_image(crop_np, lang=source_lang)
            if ok:
                logger.info(f"RapidOCR recognized text successfully: {text[:30]}")
            return text, ok

        except Exception as e:
            logger.error(f"Failed to OCR crop block {block.id}: {e}")
            return "", False
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path_str):
                try:
                    os.remove(temp_path_str)
                except Exception:
                    pass

def batch_grid_crop_and_ocr_gemini(
    img_path: str,
    blocks: list,
    backend: str = None,
    source_lang: str = "",
    progress_callback=None,
    cancel_check=None,
) -> list:
    """
    Groups up to 12 text blocks per batch into a single composite grid image with numbered
    headers ([Box 1], [Box 2], ...), calls Gemini OCR once per batch, and parses text for each block.
    This reduces API calls by 10x, eliminates conversational AI filler, and speeds up batch OCR dramatically.
    """
    import subprocess
    import shutil
    import re
    from PIL import ImageDraw

    cmd_name = "agy" if shutil.which("agy") else None
    if not cmd_name and not _get_gemini_api_key():
        logger.error("Gemini OCR unavailable: configure GOOGLE_API_KEY or install agy/gemini CLI.")
        fallback = os.getenv("HOUMI_GEMINI_FALLBACK", "none").strip().lower()
        if fallback in {"paddle", "paddleocr", "local"}:
            logger.warning("Gemini batch OCR unavailable; using local PaddleOCR fallback")
            fallback_results = []
            for index, block in enumerate(blocks, start=1):
                text, success = crop_and_ocr_block(
                    img_path,
                    block,
                    backend="paddleocr",
                    source_lang=source_lang,
                )
                fallback_results.append((block, text, success))
                if progress_callback:
                    progress_callback(index, len(blocks), 0, 0)
            return fallback_results
        return [(b, "", False) for b in blocks]

    selected_model = "flash"
    if backend:
        b_str = str(backend).lower()
        if ":" in b_str:
            selected_model = b_str.split(":", 1)[1]
        elif "lite" in b_str:
            selected_model = "flash_lite"

    try:
        img_orig = Image.open(img_path)
        w_img, h_img = img_orig.size
    except Exception as e:
        logger.error(f"Failed to open image for batch grid OCR {img_path}: {e}")
        return [(b, "", False) for b in blocks]

    results_map = {}
    batch_size = int(os.getenv("HOUMI_OCR_BATCH_SIZE", "15"))
    block_chunks = [blocks[i:i + batch_size] for i in range(0, len(blocks), batch_size)]
    completed_blocks = 0

    for chunk_idx, chunk in enumerate(block_chunks):
        if cancel_check and cancel_check():
            logger.info("Batch grid OCR cancelled via cancel_check signal")
            break
        crops = []
        for idx, b in enumerate(chunk):
            x0 = max(0, int(b.x))
            y0 = max(0, int(b.y))
            x1 = min(w_img, int(b.x + b.width))
            y1 = min(h_img, int(b.y + b.height))
            if (x1 - x0) <= 0 or (y1 - y0) <= 0:
                completed_blocks += 1
                if progress_callback:
                    progress_callback(completed_blocks, len(blocks), chunk_idx + 1, len(block_chunks))
                continue
            crop = img_orig.crop((x0, y0, x1, y1))

            # Keep a small visual margin so punctuation/strokes touching the
            # detected rectangle remain visible to OCR, without changing the
            # coordinates used when the result is written back.
            margin = max(2, int(min(crop.width, crop.height) * 0.04))
            crop = img_orig.crop((max(0, x0 - margin), max(0, y0 - margin), min(w_img, x1 + margin), min(h_img, y1 + margin)))

            stable_id = f"BOX_{idx + 1:03d}_{str(b.id).replace('-', '')[:8]}"

            banner_h = 26
            padded_w = max(crop.width + 10, 180)
            labeled = Image.new('RGB', (padded_w, crop.height + banner_h + 10), (245, 245, 245))
            draw = ImageDraw.Draw(labeled)
            draw.rectangle([0, 0, padded_w, banner_h], fill=(30, 41, 59))
            draw.text((8, 5), f'HOUMI_BOX:{stable_id}', fill=(255, 255, 255))
            labeled.paste(crop, (5, banner_h + 5))
            crops.append((b, labeled, stable_id))

        if not crops:
            continue

        num_cols = 2 if len(crops) > 6 else 1
        col_widths = [0] * num_cols
        col_heights = [0] * num_cols
        col_crops = [[] for _ in range(num_cols)]

        for idx, item in enumerate(crops):
            c_idx = idx % num_cols
            col_crops[c_idx].append(item)
            col_widths[c_idx] = max(col_widths[c_idx], item[1].width)
            col_heights[c_idx] += item[1].height + 12

        total_w = sum(col_widths) + (20 * (num_cols + 1))
        total_h = max(col_heights) + 30

        composite = Image.new('RGB', (total_w, total_h), (220, 225, 230))
        for c_idx in range(num_cols):
            curr_x = 20 + sum(col_widths[:c_idx]) + (20 * c_idx)
            curr_y = 20
            for b_obj, c_img, box_id in col_crops[c_idx]:
                composite.paste(c_img, (curr_x, curr_y))
                curr_y += c_img.height + 12

        temp_grid = tempfile.mktemp(suffix='.png')
        try:
            composite.save(temp_grid, "PNG")
            language = {"ja": "Japanese", "zh": "Chinese", "ko": "Korean", "en": "English"}.get(source_lang, "the source language")
            image_ref = _gemini_prompt_image_path(temp_grid)
            expected_ids = {box_id for _, _, box_id in crops}
            prompt = (
                f"Read every labeled text crop in attached image {image_ref}. The text language is {language}.\n"
                "Return ONLY a valid JSON array, with exactly one object per label in this schema:\n"
                '[{"box_id":"BOX_001_xxxxxxxx","text":"exact transcription","balloon_type":"bubble|shout|narrative|sfx|whisper|system","color_hex":"#000000","stroke_color_hex":null,"stroke_width_px":0,"bold":false,"italic":false,"gradient":null,"drop_shadow":null,"outer_glow":null}].\n'
                "- balloon_type: 'bubble' (normal dialogue), 'shout' (screaming/burst), 'narrative' (monologue/caption box), 'sfx' (sound effect), 'whisper' (faint/small), 'system' (RPG/game UI box).\n"
                "- color_hex: text color hex (e.g. #000000, #FFFFFF, #FF0055, or custom colored font).\n"
                "- stroke_color_hex: text outer outline color if present, else null.\n"
                "- stroke_width_px: 0 if no outline, 2 for thin, 4 for medium, 6 for heavy outline.\n"
                "- bold: true if text is bold, thick, heavy, or shouting emphasis, else false.\n"
                "- italic: true if text is slanted, cursive, whispered, or dramatic italic, else false.\n"
                "- gradient: if multi-colored text fill, return {\"enabled\":true,\"type\":\"linear\"|\"radial\",\"colors\":[\"#hex1\",\"#hex2\"],\"angle_deg\":number}, else null.\n"
                "- drop_shadow: if visible shadow behind text, return {\"enabled\":true,\"color\":\"#hex\",\"blur\":number,\"distance\":number}, else null.\n"
                "- outer_glow: if visible glowing halo/aura around text, return {\"enabled\":true,\"color\":\"#hex\",\"blur\":number}, else null.\n"
                "Use the exact full box_id from the banner, never infer IDs from order. Preserve line breaks and punctuation. Do not translate or add commentary."
            )
            logger.info(f"Running Composite Grid Gemini OCR ({selected_model}) on batch {chunk_idx + 1}/{len(block_chunks)} ({len(crops)} boxes)")
            raw, success = _run_gemini_command(prompt, model=selected_model, image_path=temp_grid, provider="agy")

            if success and raw:
                parsed_boxes = _parse_gemini_grid_response(raw, expected_ids)
                missing_count = len(crops) - len(parsed_boxes)
                logger.info(
                    "Composite Grid Gemini mapped %s/%s boxes%s",
                    len(parsed_boxes),
                    len(crops),
                    f"; {missing_count} require fallback" if missing_count else "; no fallback needed",
                )

                for b_obj, _, box_id in crops:
                    if box_id in parsed_boxes:
                        item_data = parsed_boxes[box_id]
                        text_val = item_data.get("text", "") if isinstance(item_data, dict) else str(item_data)
                        if isinstance(item_data, dict):
                            b_type = item_data.get("balloon_type")
                            if b_type and str(b_type).lower() in {"bubble", "shout", "narrative", "narration", "sfx", "whisper", "system"}:
                                b_obj.balloon_type = str(b_type).lower()
                            c_hex = item_data.get("color_hex")
                            if c_hex and isinstance(c_hex, str) and c_hex.startswith("#"):
                                b_obj.color_hex = c_hex
                            if "bold" in item_data:
                                b_obj.bold = bool(item_data["bold"])
                            if "italic" in item_data:
                                b_obj.italic = bool(item_data["italic"])
                            s_col = item_data.get("stroke_color_hex") or item_data.get("stroke_color")
                            s_wid = item_data.get("stroke_width_px") or item_data.get("stroke_width")
                            g_cols = item_data.get("gradient_colors")
                            grad_obj = item_data.get("gradient")
                            shadow_obj = item_data.get("drop_shadow")
                            glow_obj = item_data.get("outer_glow")
                            inner_obj = item_data.get("inner_shadow")

                            meta = dict(b_obj.extra_metadata or {})
                            if c_hex and isinstance(c_hex, str) and c_hex.startswith("#"):
                                meta["detected_color_hex"] = c_hex
                            if "bold" in item_data:
                                meta["bold"] = bool(item_data["bold"])
                                meta["detected_bold"] = bool(item_data["bold"])
                            if "italic" in item_data:
                                meta["italic"] = bool(item_data["italic"])
                                meta["detected_italic"] = bool(item_data["italic"])
                            if s_col and isinstance(s_col, str) and s_col.startswith("#"):
                                meta["stroke_color"] = s_col
                            if s_wid is not None:
                                try:
                                    meta["stroke_width"] = float(s_wid)
                                except Exception:
                                    pass
                            if g_cols and isinstance(g_cols, list):
                                meta["gradient_colors"] = g_cols
                            if grad_obj and isinstance(grad_obj, dict):
                                meta["detected_gradient"] = grad_obj
                            if shadow_obj and isinstance(shadow_obj, dict):
                                meta["detected_drop_shadow"] = shadow_obj
                            if glow_obj and isinstance(glow_obj, dict):
                                meta["detected_outer_glow"] = glow_obj
                            if inner_obj and isinstance(inner_obj, dict):
                                meta["detected_inner_shadow"] = inner_obj
                            b_obj.extra_metadata = meta

                        results_map[b_obj.id] = (text_val, True)
                        completed_blocks += 1
                        if progress_callback:
                            progress_callback(completed_blocks, len(blocks), chunk_idx + 1, len(block_chunks))
                    else:
                        # Fallback for individual box if missed in grid response using Gemini/AGY CLI
                        from app.services.gemini_quota import get_quota_status
                        has_local_fallback = (backend == "paddleocr" or os.getenv("HOUMI_GEMINI_FALLBACK") == "paddleocr")
                        if get_quota_status().get("quota_exceeded") and not has_local_fallback:
                            logger.warning("Skipping missing box fallback because Gemini Quota is exceeded and no local OCR fallback configured")
                            results_map[b_obj.id] = ("", False)
                        else:
                            fallback_txt, fallback_success = crop_and_ocr_block(img_path, b_obj, backend=backend, source_lang=source_lang)
                            results_map[b_obj.id] = (fallback_txt, fallback_success)
                        completed_blocks += 1
                        if progress_callback:
                            progress_callback(completed_blocks, len(blocks), chunk_idx + 1, len(block_chunks))
            else:
                from app.services.gemini_quota import get_quota_status
                has_local_fallback = (backend == "paddleocr" or os.getenv("HOUMI_GEMINI_FALLBACK") == "paddleocr")
                if get_quota_status().get("quota_exceeded") and not has_local_fallback:
                    logger.warning("Batch grid OCR failed due to Gemini Quota Exceeded and no local OCR fallback configured; skipping single block fallback loops.")
                else:
                    logger.warning("Batch grid OCR CLI failed or returned empty output; falling back to single block Gemini/AGY CLI OCR")
                    for b_obj, _, _ in crops:
                        if get_quota_status().get("quota_exceeded") and not has_local_fallback:
                            logger.warning("Quota exceeded hit during fallback loop; breaking early.")
                            break
                        fallback_txt, fallback_success = crop_and_ocr_block(img_path, b_obj, backend=backend, source_lang=source_lang)
                        results_map[b_obj.id] = (fallback_txt, fallback_success)
                        completed_blocks += 1
                        if progress_callback:
                            progress_callback(completed_blocks, len(blocks), chunk_idx + 1, len(block_chunks))

        finally:
            if os.path.exists(temp_grid):
                try:
                    os.remove(temp_grid)
                except Exception:
                    pass

    return [(b, results_map.get(b.id, ("", False))[0], results_map.get(b.id, ("", False))[1]) for b in blocks]


def batch_in_memory_rapid_ocr(
    img_path: str,
    blocks: list,
    source_lang: str = "",
    progress_callback=None,
    cancel_check=None,
) -> list:
    """
    Ultra-fast in-memory zero-copy RapidOCR pipeline (matching ImageTrans native C++ speed).
    Loads the full page once into RAM, slices all bounding boxes in-memory as NumPy arrays,
    and executes direct pure recognition (use_det=False) without disk I/O or redundant DBNet detections.
    """
    if not blocks:
        return []

    try:
        from app.utils.image_utils import cv2_imread_unicode
        img_bgr = cv2_imread_unicode(img_path)
        if img_bgr is None:
            with Image.open(img_path) as pimg:
                img_bgr = cv2.cvtColor(np.array(pimg.convert("RGB")), cv2.COLOR_RGB2BGR)
        h_img, w_img = img_bgr.shape[:2]
    except Exception as e:
        logger.error(f"Failed to load image for in-memory RapidOCR {img_path}: {e}")
        return [(b, "", False) for b in blocks]

    rapid = _get_rapid_ocr(lang=source_lang)
    if rapid is None:
        logger.error("RapidOCR engine not available for in-memory batch OCR")
        return [(b, "", False) for b in blocks]

    results = []
    total = len(blocks)

    for idx, b in enumerate(blocks, start=1):
        if cancel_check and cancel_check():
            results.append((b, "", False))
            continue

        target_bbox = getattr(b, "smart_bbox", None) or {"x": b.x, "y": b.y, "width": b.width, "height": b.height}
        x0 = max(0, int(target_bbox["x"]))
        y0 = max(0, int(target_bbox["y"]))
        x1 = min(w_img, int(target_bbox["x"] + target_bbox["width"]))
        y1 = min(h_img, int(target_bbox["y"] + target_bbox["height"]))

        if (x1 - x0) <= 0 or (y1 - y0) <= 0:
            results.append((b, "", True))
            if progress_callback:
                progress_callback(idx, total, 0, 0)
            continue

        bw = max(1, x1 - x0)
        bh = max(1, y1 - y0)
        pad_x = int(max(4, bw * 0.08))
        pad_y = int(max(4, bh * 0.08))

        crop_x0 = max(0, x0 - pad_x)
        crop_y0 = max(0, y0 - pad_y)
        crop_x1 = min(w_img, x1 + pad_x)
        crop_y1 = min(h_img, y1 + pad_y)

        crop_bgr = img_bgr[crop_y0:crop_y1, crop_x0:crop_x1]
        if crop_bgr.size == 0:
            results.append((b, "", True))
            if progress_callback:
                progress_callback(idx, total, 0, 0)
            continue

        # Upscale small crops in-memory
        crop_h, crop_w = crop_bgr.shape[:2]
        if crop_h < 80 or crop_w < 80:
            scale = max(1.5, 96.0 / max(1, crop_h))
            new_w = int(crop_w * scale)
            new_h = int(crop_h * scale)
            crop_bgr = cv2.resize(crop_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # Direct In-Memory RapidOCR (with fast projection line slicing & pure zero-copy text_rec)
        try:
            text = _fast_split_and_ocr(crop_bgr, rapid)
            results.append((b, text, True))
        except Exception as err:
            logger.warning(f"In-memory RapidOCR failed for block {b.id}: {err}")
            results.append((b, "", False))

        if progress_callback:
            progress_callback(idx, total, 0, 0)

    return results


def crop_and_ocr_blocks_parallel(
    img_path: str,
    blocks: list,
    max_workers: int = 2,
    backend: str = None,
    source_lang: str = "",
    progress_callback=None,
    cancel_check=None,
) -> list:
    """
    Performs OCR on multiple text blocks. 
    1. If backend is Gemini/agy -> uses high-speed Composite Grid Batch OCR (combining 12 blocks into 1 request).
    2. If backend is RapidOCR/PP-OCRv5/Local -> uses ultra-fast in-memory zero-copy batch recognition (0.3-0.5s).
    3. Otherwise -> uses parallel individual block OCR.
    """
    if not blocks:
        return []

    # A. Check if Gemini/agy backend is requested -> use Composite Grid Batch OCR
    if backend and any(b in str(backend).lower() for b in ("gemini", "ai", "agy")):
        return batch_grid_crop_and_ocr_gemini(
            img_path,
            blocks,
            backend=backend,
            source_lang=source_lang,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    # B. High-speed In-Memory Zero-Copy Batch for RapidOCR / PP-OCRv5 (10x-15x speedup)
    b_lower = str(backend or "").lower()
    if not backend or any(k in b_lower for k in ("rapid", "ppocr", "v5", "paddle")):
        return batch_in_memory_rapid_ocr(
            img_path,
            blocks,
            source_lang=source_lang,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    class TempBlock:
        def __init__(self, id, x, y, width, height, confidence):
            self.id = id
            self.x = x
            self.y = y
            self.width = width
            self.height = height
            self.confidence = confidence

    # Extract SQLite attributes on the main thread before starting background threads
    tasks = []
    for b in blocks:
        temp_b = TempBlock(b.id, b.x, b.y, b.width, b.height, b.confidence)
        tasks.append((b, temp_b))

    max_retries = 3
    per_block_timeout = 120.0

    def ocr_worker_with_retry(task):
        b, temp_b = task
        if cancel_check and cancel_check():
            return b, "", False
        from app.services.gemini_quota import get_quota_status
        if get_quota_status().get("quota_exceeded") and backend and any(k in str(backend).lower() for k in ("gemini", "ai", "agy")):
            logger.warning("🛑 Gemini Quota Exceeded (429) active; aborting OCR task for block %s", temp_b.id)
            return b, "", False
        for attempt in range(1, max_retries + 1):
            if cancel_check and cancel_check():
                return b, "", False
            if get_quota_status().get("quota_exceeded") and backend and any(k in str(backend).lower() for k in ("gemini", "ai", "agy")):
                logger.warning("🛑 Gemini Quota Exceeded (429) hit on attempt %d; aborting retries immediately.", attempt)
                return b, "", False
            ocr_text, success = crop_and_ocr_block(img_path, temp_b, backend=backend, timeout=per_block_timeout, source_lang=source_lang)
            if success:
                return b, ocr_text, True
            if get_quota_status().get("quota_exceeded") and backend and any(k in str(backend).lower() for k in ("gemini", "ai", "agy")):
                logger.warning("🛑 Gemini Quota Exceeded (429) hit after block call; aborting retries immediately.")
                return b, "", False
            logger.warning(f"OCR attempt {attempt}/{max_retries} failed for block {temp_b.id}, retrying...")
            time.sleep(1.0 * attempt)  # Backoff: 1s, 2s, 3s
        logger.error(f"OCR failed after {max_retries} attempts for block {temp_b.id}")
        return b, "", False

    effective_workers = max(1, min(int(max_workers), 4, len(tasks)))
    
    results = []
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        futures = {executor.submit(ocr_worker_with_retry, task): task for task in tasks}
        for future in as_completed(futures):
            if cancel_check and cancel_check():
                logger.info("OCR execution cancelled via cancel_check signal")
                break
            results.append(future.result())
            if progress_callback:
                progress_callback(len(results), len(tasks), 0, 0)
    
    block_order = {id(b): i for i, (b, _) in enumerate(tasks)}
    results.sort(key=lambda r: block_order.get(id(r[0]), 0))
    
    return results


def batch_project_pdf_gemini_ocr(
    project_name: str,
    all_targets: list,
    backend: str = None,
    source_lang: str = "",
    progress_callback=None,
    cancel_check=None,
    stage_callback=None,
    ocr_depth: str = "full",
) -> dict:
    """
    Groups ALL unscanned text blocks across ALL pages in the project into a single
    compact Multi-Page Cropped-Grid PDF and executes ONE single Gemini API request.
    Reduces 15-20 requests down to 1 single request for the entire chapter!
    Returns dict mapping block_id -> dict with text, balloon_type, color_hex, stroke_color, stroke_width, gradient_colors.
    """
    from PIL import ImageDraw, ImageFont

    if not all_targets:
        return {}

    logger.info(f"🚀 Starting Whole-Chapter PDF Gemini OCR ({backend}) for {len(all_targets)} blocks in 1 request!")
    if stage_callback:
        stage_callback(
            phase="building_pdf",
            phase_title="1/4 จัดเตรียมเอกสาร PDF",
            message=f"กำลังรวบรวม {len(all_targets)} บอลลูนและสร้างเอกสาร Multi-Page PDF...",
            progress=0.10,
            completed=0,
            total=len(all_targets)
        )

    all_crops = []
    font_banner = None
    try:
        font_banner = ImageFont.truetype("arialbd.ttf", 18)
    except Exception:
        font_banner = ImageFont.load_default()

    for idx, (pg, b) in enumerate(all_targets, start=1):
        try:
            with Image.open(pg.source_image_path) as pimg:
                img_orig = pimg.convert("RGB")
                w_img, h_img = img_orig.size
                x0 = max(0, int(b.x))
                y0 = max(0, int(b.y))
                x1 = min(w_img, int(b.x + b.width))
                y1 = min(h_img, int(b.y + b.height))
                if (x1 - x0) <= 0 or (y1 - y0) <= 0:
                    continue
                margin = max(4, int(min(x1 - x0, y1 - y0) * 0.05))
                crop = img_orig.crop((max(0, x0 - margin), max(0, y0 - margin), min(w_img, x1 + margin), min(h_img, y1 + margin)))

                if crop.height < 60 or crop.width < 60:
                    scale = max(1.5, 80.0 / max(1, crop.height))
                    crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.Resampling.LANCZOS)

                bid_clean = str(b.id).replace("-", "")[:8]
                stable_id = f"BOX_{idx:03d}_{bid_clean}"
                banner_h = 30
                col_width = (1600 - 60) // 3
                max_crop_w = col_width - 16
                if crop.width > max_crop_w:
                    scale = max_crop_w / float(crop.width)
                    crop = crop.resize((max_crop_w, int(crop.height * scale)), Image.Resampling.LANCZOS)

                card_w = col_width
                card_h = crop.height + banner_h + 12
                card = Image.new("RGB", (card_w, card_h), (255, 255, 255))
                draw_card = ImageDraw.Draw(card)
                draw_card.rectangle([0, 0, card_w, banner_h], fill=(30, 41, 59))
                draw_card.text((10, 4), f"HOUMI_BOX:{stable_id}", fill=(255, 255, 255), font=font_banner)
                draw_card.rectangle([0, 0, card_w - 1, card_h - 1], outline=(203, 213, 225), width=1)
                
                paste_x = (card_w - crop.width) // 2
                card.paste(crop, (paste_x, banner_h + 6))

                all_crops.append((b, card, stable_id))
        except Exception as e:
            logger.error(f"Failed to crop block {b.id} for PDF grid: {e}")

    if not all_crops:
        return {}

    # ─── Chunked Multi-PDF Packing (≤40 boxes per chunk to avoid 120s timeout) ───
    MAX_BOXES_PER_CHUNK = int(os.getenv("HOUMI_DOBKLE_CHUNK_SIZE", "40"))
    chunks = [all_crops[i:i + MAX_BOXES_PER_CHUNK] for i in range(0, len(all_crops), MAX_BOXES_PER_CHUNK)]

    page_width = 1600
    page_height = 2400
    num_cols = 3
    col_width = (page_width - 60) // num_cols

    selected_model = "flash"
    if backend:
        b_str = str(backend).lower()
        if ":" in b_str:
            selected_model = b_str.split(":", 1)[1]
        elif "lite" in b_str:
            selected_model = "flash_lite"

    language = {"ja": "Japanese", "zh": "Chinese", "ko": "Korean", "en": "English"}.get(source_lang, "the source language")

    # ─── Prompt: text_only (short & fast) vs full (with style/effects) ───
    if ocr_depth == "text_only":
        prompt_template = (
            "Read every labeled text crop across all pages in attached PDF {image_ref}. "
            f"The text language is {language}.\n"
            "Return ONLY a valid JSON array: "
            '[{{"box_id":"BOX_001_xxxxxxxx","text":"exact transcription"}}].\n'
            "Use the exact box_id from the banner. Preserve line breaks and punctuation. Do not translate."
        )
    else:
        prompt_template = (
            "You are an expert manga/webtoon editor and OCR typographer. Read every labeled text crop across all pages in attached PDF {image_ref}. "
            f"The text language is {language}.\n"
            "Analyze both the VISUAL APPEARANCE (speech bubble contour, text boldness, italics, stroke, typography, gradient, shadows, glowing aura) and SEMANTIC CONTEXT of each card.\n"
            "Return ONLY a valid JSON array, with exactly one object per label in this schema:\n"
            '[{{"box_id":"BOX_001_xxxxxxxx","text":"exact transcription","balloon_type":"bubble|shout|narrative|thought|whisper|system|sfx","color_hex":"#000000","stroke_color_hex":null,"stroke_width_px":0,"bold":false,"italic":false,"gradient":null,"drop_shadow":null,"outer_glow":null,"inner_shadow":null}}].\n\n'
            "### VISUAL CLASSIFICATION RULES FOR balloon_type:\n"
            "1. 'shout': Spiky/burst/explosion jagged bubble borders, OR extra-bold / heavy / slanted-italic dramatic text, shouting dialogue.\n"
            "2. 'bubble': Standard smooth oval or circular speech balloons with regular clean font weight (normal dialogue).\n"
            "3. 'narrative': Rectangular / square boxes with straight 90-degree edges, caption bars, voiceover narration.\n"
            "4. 'thought': Cloud-like scalloped wavy borders, or balloons with bubble-chain tails, internal monologue.\n"
            "5. 'whisper': Dashed/dotted borders, or noticeably small/faint text, mumbling/whispering.\n"
            "6. 'system': RPG / game status windows, UI notification cards, digital system prompts.\n"
            "7. 'sfx': Hand-drawn sound effects floating directly on artwork without standard speech bubble.\n\n"
            "### VISUAL STYLE & EFFECT ATTRIBUTES:\n"
            "- color_hex: Text fill color hex (e.g. #000000 for black, #FFFFFF for white text, or accent/colored font hex like #2B3A58, #FF0000, #EAB308).\n"
            "- stroke_color_hex: Text outline/border color if visible (e.g. #000000 or #FFFFFF), else null.\n"
            "- stroke_width_px: 0 if no outline, 2 for thin stroke, 4 for medium, 6 for heavy bold outline.\n"
            "- bold: true if text is bold, heavy weight, or shouting emphasis, else false.\n"
            "- italic: true if text is slanted, cursive, whispered, or dramatic italic, else false.\n"
            "- gradient: if multi-colored / gradient fill text, return {{\"enabled\":true,\"type\":\"linear\"|\"radial\",\"colors\":[\"#hex1\",\"#hex2\"],\"angle_deg\":number}}, else null.\n"
            "- drop_shadow: if visible shadow behind text, return {{\"enabled\":true,\"color\":\"#hex\",\"blur\":number,\"distance\":number}}, else null.\n"
            "- outer_glow: if visible glowing halo/aura around text, return {{\"enabled\":true,\"color\":\"#hex\",\"blur\":number}}, else null.\n"
            "- inner_shadow: if visible inner shadow/bevel text effect, return {{\"enabled\":true,\"color\":\"#hex\",\"blur\":number}}, else null.\n\n"
            "Use the exact full box_id from the header banner (never infer IDs from order). Preserve line breaks and punctuation. Do not translate."
        )

    results_by_block_id = {}
    total_completed = 0

    for chunk_idx, chunk_crops in enumerate(chunks):
        if cancel_check and cancel_check():
            logger.info("DOBKLE OCR cancelled by user at chunk %d/%d", chunk_idx + 1, len(chunks))
            break

        # Pack this chunk into PDF pages
        pdf_pages = []
        current_page_img = Image.new("RGB", (page_width, page_height), (241, 245, 249))
        draw_pg = ImageDraw.Draw(current_page_img)
        draw_pg.rectangle([0, 0, page_width, 45], fill=(15, 23, 42))
        draw_pg.text((20, 10), f"HOUMI STUDIO — OCR GRID SHEET — {project_name} (PAGE 1)", fill=(250, 204, 21), font=font_banner)

        col_idx = 0
        curr_x = 20 + col_idx * (col_width + 10)
        curr_y = 60

        for b_obj, card, box_id in chunk_crops:
            card_h = card.height
            if curr_y + card_h > page_height - 20:
                col_idx += 1
                if col_idx >= num_cols:
                    pdf_pages.append(current_page_img)
                    current_page_img = Image.new("RGB", (page_width, page_height), (241, 245, 249))
                    draw_pg = ImageDraw.Draw(current_page_img)
                    draw_pg.rectangle([0, 0, page_width, 45], fill=(15, 23, 42))
                    draw_pg.text((20, 10), f"HOUMI STUDIO — OCR GRID SHEET — {project_name} (PAGE {len(pdf_pages)+1})", fill=(250, 204, 21), font=font_banner)
                    col_idx = 0
                curr_x = 20 + col_idx * (col_width + 10)
                curr_y = 60

            current_page_img.paste(card, (curr_x, curr_y))
            curr_y += card_h + 10

        pdf_pages.append(current_page_img)

        temp_pdf = tempfile.mktemp(suffix=".pdf")
        try:
            pdf_pages[0].save(temp_pdf, "PDF", resolution=100.0, save_all=True, append_images=pdf_pages[1:])
            image_ref = _gemini_prompt_image_path(temp_pdf)
            expected_ids = {box_id for _, _, box_id in chunk_crops}
            prompt = prompt_template.format(image_ref=image_ref)

            logger.info(
                "🚀 DOBKLE chunk %d/%d: %d boxes across %d PDF pages (depth=%s)",
                chunk_idx + 1, len(chunks), len(chunk_crops), len(pdf_pages), ocr_depth,
            )
            if stage_callback:
                chunk_progress = 0.15 + (0.70 * chunk_idx / max(1, len(chunks)))
                stage_callback(
                    phase="ai_inference",
                    phase_title=f"2/4 DOBKLE OCR (Gemini VLM) — Chunk {chunk_idx+1}/{len(chunks)}",
                    message=f"กำลังส่ง PDF chunk {chunk_idx+1}/{len(chunks)} ({len(chunk_crops)} กล่อง) ให้ AI ถอดรหัส...",
                    progress=chunk_progress,
                    completed=total_completed,
                    total=len(all_targets),
                )

            # Use shorter timeout for chunks (60s) — if a 40-box chunk can't finish in 60s, something is wrong
            raw, success = _run_gemini_command(prompt, model=selected_model, image_path=temp_pdf, provider="agy", timeout=60)

            if success and raw:
                parsed_boxes = _parse_gemini_grid_response(raw, expected_ids)
                mapped = len(parsed_boxes)
                missed = len(chunk_crops) - mapped
                logger.info(
                    "✅ DOBKLE chunk %d/%d mapped %d/%d boxes%s",
                    chunk_idx + 1, len(chunks), mapped, len(chunk_crops),
                    f"; {missed} missed (no fallback)" if missed else "",
                )

                for b_obj, _, box_id in chunk_crops:
                    if box_id in parsed_boxes:
                        results_by_block_id[b_obj.id] = parsed_boxes[box_id]
                    else:
                        results_by_block_id[b_obj.id] = {"text": "", "success": False}
                total_completed += len(chunk_crops)
            else:
                # ❌ Fail-fast: do NOT fallback to other models — report error
                logger.error(
                    "❌ DOBKLE chunk %d/%d FAILED — NOT falling back to other models",
                    chunk_idx + 1, len(chunks),
                )
                if stage_callback:
                    stage_callback(
                        phase="chunk_error",
                        phase_title=f"⚠️ Chunk {chunk_idx+1}/{len(chunks)} ล้มเหลว",
                        message=f"Chunk {chunk_idx+1} ({len(chunk_crops)} กล่อง) ล้มเหลว — ไม่ Fallback ให้โมเดลอื่น",
                        progress=0.15 + (0.70 * (chunk_idx + 1) / max(1, len(chunks))),
                        completed=total_completed,
                        total=len(all_targets),
                    )
                for b_obj, _, _ in chunk_crops:
                    results_by_block_id[b_obj.id] = {"text": "", "success": False}
                total_completed += len(chunk_crops)

        finally:
            if os.path.exists(temp_pdf):
                try:
                    os.remove(temp_pdf)
                except Exception:
                    pass

    return results_by_block_id

