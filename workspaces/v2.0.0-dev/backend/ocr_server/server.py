"""
Hybrid OCR Direct Server

Primary target: deepseek-ai/DeepSeek-OCR-2
Safe fallback: zai-org/GLM-OCR

On this Windows + CUDA setup, DeepSeek-OCR-2 can crash inside its MoE CUDA path
with an illegal memory access. This server keeps the same HTTP API, but can
automatically fall back to GLM so ImageTrans still gets usable OCR output.
"""
import json
import logging
import os
import re
import time
import uuid
import threading
from typing import Any, Dict, Optional, Tuple

import torch
import transformers
from bottle import request, response, route, run, static_file
from PIL import Image
from transformers import (
    AutoConfig,
    AutoModel,
    AutoModelForImageTextToText,
    AutoProcessor,
    AutoTokenizer,
    BitsAndBytesConfig,
    GenerationConfig,
)
from transformers.generation import GenerationMixin


LOGGER = logging.getLogger("hybrid-ocr-direct")


def patch_deepseek_v2_rope() -> None:
    """Best-effort compatibility patches for DeepSeek remote code."""
    try:
        import sys

        for name, module in list(sys.modules.items()):
            if hasattr(module, "DeepseekV2RotaryEmbedding"):
                cls = getattr(module, "DeepseekV2RotaryEmbedding")
                if hasattr(cls, "forward") and not hasattr(cls, "_is_patched"):
                    old_forward = cls.forward

                    def new_forward(self, x, position_ids=None, seq_len=None, **kwargs):
                        if seq_len is None and position_ids is not None:
                            if torch.is_tensor(position_ids):
                                seq_len = position_ids.max().item() + 1
                            else:
                                seq_len = position_ids
                        return old_forward(self, x, seq_len=seq_len)

                    cls.forward = new_forward
                    cls._is_patched = True
                    LOGGER.info("Patched %s.DeepseekV2RotaryEmbedding", name)

            if hasattr(module, "apply_rotary_pos_emb"):
                old_apply = module.apply_rotary_pos_emb
                if not getattr(old_apply, "_deepseek_patched", False):

                    def new_apply(q, k, cos, sin, position_ids, unsqueeze_dim=1):
                        try:
                            if cos.dim() == 2:
                                cos = cos[position_ids].unsqueeze(unsqueeze_dim)
                                sin = sin[position_ids].unsqueeze(unsqueeze_dim)

                            if q.dim() >= 3 and cos.dim() >= 3:
                                q_len = q.shape[2]
                                cos_len = cos.shape[2]
                                if q_len != cos_len:
                                    cos = cos[:, :, :q_len, :]
                                    sin = sin[:, :, :q_len, :]

                            def rotate_half(x):
                                x1 = x[..., : x.shape[-1] // 2]
                                x2 = x[..., x.shape[-1] // 2 :]
                                return torch.cat((-x2, x1), dim=-1)

                            return (q * cos) + (rotate_half(q) * sin), (k * cos) + (
                                rotate_half(k) * sin
                            )
                        except Exception:
                            return old_apply(q, k, cos, sin, position_ids, unsqueeze_dim)

                    new_apply._deepseek_patched = True
                    module.apply_rotary_pos_emb = new_apply

            if hasattr(module, "repeat_kv"):
                old_repeat_kv = module.repeat_kv
                if not getattr(old_repeat_kv, "_deepseek_patched", False):

                    def new_repeat_kv(hidden_states, n_rep):
                        if len(hidden_states.shape) != 4:
                            if n_rep == 1:
                                return hidden_states
                            return hidden_states.repeat_interleave(n_rep, dim=1)
                        return old_repeat_kv(hidden_states, n_rep)

                    new_repeat_kv._deepseek_patched = True
                    module.repeat_kv = new_repeat_kv
    except Exception as exc:
        LOGGER.warning("Failed to patch DeepSeek RoPE: %s", exc)


def patch_transformers_for_deepseek() -> None:
    """Compatibility layer for newer transformers with DeepSeek remote code."""
    import transformers.models.llama.modeling_llama as modeling_llama
    import transformers.utils.import_utils as import_utils

    if not hasattr(modeling_llama, "LlamaFlashAttention2"):
        modeling_llama.LlamaFlashAttention2 = modeling_llama.LlamaAttention

    if not hasattr(import_utils, "is_torch_fx_available"):
        import_utils.is_torch_fx_available = lambda: True

    try:
        from transformers.cache_utils import DynamicCache

        if not hasattr(DynamicCache, "seen_tokens"):
            DynamicCache.seen_tokens = property(lambda self: self.get_seq_length())
        if not hasattr(DynamicCache, "get_max_length"):
            DynamicCache.get_max_length = lambda self: 4096
        if not hasattr(DynamicCache, "get_usable_length"):
            DynamicCache.get_usable_length = lambda self, seq_length=None: self.get_seq_length()
    except ImportError:
        pass

    old_repeat_kv = modeling_llama.repeat_kv
    if not getattr(old_repeat_kv, "_hybrid_patched", False):

        def new_repeat_kv(hidden_states, n_rep):
            if n_rep == 1:
                return hidden_states
            if len(hidden_states.shape) != 4:
                return hidden_states.repeat_interleave(n_rep, dim=1)
            return old_repeat_kv(hidden_states, n_rep)

        new_repeat_kv._hybrid_patched = True
        modeling_llama.repeat_kv = new_repeat_kv

    if hasattr(modeling_llama, "LlamaAttention"):
        old_forward = modeling_llama.LlamaAttention.forward
        if not getattr(old_forward, "_hybrid_patched", False):

            def new_forward(self, hidden_states, position_embeddings=None, **kwargs):
                position_ids = kwargs.get("position_ids")
                if position_embeddings is None and position_ids is not None and hasattr(self, "rotary_emb"):
                    try:
                        position_embeddings = self.rotary_emb(hidden_states, position_ids)
                    except TypeError:
                        seq_len = position_ids.max().item() + 1
                        position_embeddings = self.rotary_emb(hidden_states, seq_len=seq_len)

                past_key_value = kwargs.pop("past_key_value", None)
                if past_key_value is not None:
                    kwargs["past_key_values"] = past_key_value

                if position_embeddings is None:
                    dummy = torch.zeros(
                        1, 1, 1, 1, device=hidden_states.device, dtype=hidden_states.dtype
                    )
                    position_embeddings = (dummy, dummy)

                result = old_forward(
                    self,
                    hidden_states,
                    position_embeddings=position_embeddings,
                    **kwargs,
                )
                if isinstance(result, tuple) and len(result) == 2:
                    return result[0], result[1], past_key_value
                return result

            new_forward._hybrid_patched = True
            modeling_llama.LlamaAttention.forward = new_forward


class Config:
    DEEPSEEK_MODEL_ID = os.environ.get("DEEPSEEK_OCR_MODEL", "deepseek-ai/DeepSeek-OCR-2")
    GLM_MODEL_ID = os.environ.get("GLM_OCR_MODEL", "zai-org/GLM-OCR")
    OCR_BACKEND = os.environ.get("OCR_BACKEND", "auto").lower()
    HOST = "127.0.0.1"
    PORT = int(os.environ.get("SERVER_PORT", "2322"))
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploaded")
    STATIC_ROOT = os.environ.get("STATIC_ROOT", "./www")
    LOG_DIR = os.environ.get("LOG_DIR", "./logs")
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    HAS_BF16 = torch.cuda.is_available() and hasattr(torch.cuda, "is_bf16_supported") and torch.cuda.is_bf16_supported()
    LOAD_IN_4BIT = os.environ.get("LOAD_IN_4BIT", "true").lower() == "true"
    DEEPSEEK_DTYPE = (torch.bfloat16 if HAS_BF16 else torch.float16) if DEVICE == "cuda" and not LOAD_IN_4BIT else torch.float32
    GLM_DTYPE = (torch.bfloat16 if HAS_BF16 else torch.float16) if DEVICE == "cuda" else torch.float32
    DEEPSEEK_PROMPT = os.environ.get("DEEPSEEK_OCR_PROMPT", "<image>\n<|grounding|>OCR this image.")
    GLM_PROMPT = os.environ.get("GLM_OCR_PROMPT", "OCR the text in this image exactly as written.")


for directory in [Config.UPLOAD_DIR, Config.STATIC_ROOT, Config.LOG_DIR]:
    os.makedirs(directory, exist_ok=True)


logging.basicConfig(
    filename=os.path.join(Config.LOG_DIR, "server.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
LOGGER = logging.getLogger("hybrid-ocr-direct")
LOGGER.addHandler(logging.StreamHandler())
LOGGER.setLevel(logging.INFO)


def should_use_glm_by_default() -> bool:
    if Config.OCR_BACKEND == "glm":
        return True
    if Config.OCR_BACKEND == "deepseek":
        return False
    # Auto mode: Windows + CUDA + DeepSeek MoE has been unstable here, so prefer GLM.
    return os.name == "nt" and Config.DEVICE == "cuda"


class BaseBackend:
    name = "base"
    model_id = ""

    def load(self) -> None:
        raise NotImplementedError

    def unload(self) -> None:
        pass

    def run_inference(self, image_path: str, original_size: Tuple[int, int]) -> Dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def clean_text(text: str) -> str:
        return text.strip()

    @staticmethod
    def build_text_lines(text: str, original_size: Tuple[int, int]) -> Dict[str, Any]:
        if not text or not text.strip():
            return {"text_lines": [], "raw": "", "markdown": ""}

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            lines = [text.strip()]

        w, h = original_size
        line_height = max(h // max(len(lines), 1), 1)
        text_lines = []
        for idx, line_text in enumerate(lines):
            y_top = idx * line_height
            y_bottom = min(y_top + line_height, h)
            text_lines.append(
                {
                    "x0": 0,
                    "y0": y_top,
                    "x1": w,
                    "y1": y_top,
                    "x2": w,
                    "y2": y_bottom,
                    "x3": 0,
                    "y3": y_bottom,
                    "text": line_text,
                }
            )

        return {"text_lines": text_lines, "raw": text, "markdown": text}


class DeepSeekBackend(BaseBackend):
    name = "deepseek"
    model_id = Config.DEEPSEEK_MODEL_ID

    def __init__(self) -> None:
        self.model = None
        self.tokenizer = None
        self.processor = None

    def load(self) -> None:
        if self.model is not None:
            return

        patch_transformers_for_deepseek()
        LOGGER.info("Loading DeepSeek backend: %s", self.model_id)

        config = AutoConfig.from_pretrained(self.model_id, trust_remote_code=True)
        config_class = type(config)

        def patched_getattr(obj, item):
            defaults = {
                "pad_token_id": 0,
                "eos_token_id": 0,
                "bos_token_id": 0,
                "attention_dropout": 0.0,
                "hidden_dropout": 0.0,
                "dropout": 0.0,
                "pretraining_tp": 1,
                "attention_bias": False,
                "mlp_bias": False,
                "rope_scaling": None,
                "hidden_act": "silu",
                "rms_norm_eps": 1e-6,
                "num_key_value_heads": 1,
                "is_causal": True,
            }
            if item == "pad_token_id":
                return obj.__dict__.get("pad_token_id") or obj.__dict__.get("eos_token_id") or 0
            if item in defaults:
                return defaults[item]
            raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{item}'")

        config_class.__getattr__ = patched_getattr

        quantization_config = None
        if Config.LOAD_IN_4BIT:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )

        self.model = AutoModel.from_pretrained(
            self.model_id,
            config=config,
            torch_dtype=Config.DEEPSEEK_DTYPE,
            trust_remote_code=True,
            device_map={"": "cuda:0"} if Config.DEVICE == "cuda" else {"": "cpu"},
            quantization_config=quantization_config,
        )
        patch_deepseek_v2_rope()

        if not hasattr(self.model, "generate"):
            model_class = type(self.model)
            if GenerationMixin not in model_class.__bases__:
                model_class.__bases__ = (GenerationMixin,) + model_class.__bases__
            if not hasattr(self.model, "generation_config") or self.model.generation_config is None:
                try:
                    self.model.generation_config = GenerationConfig.from_model_config(self.model.config)
                except Exception:
                    self.model.generation_config = GenerationConfig()

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=True)
        try:
            self.processor = AutoProcessor.from_pretrained(self.model_id, trust_remote_code=True)
        except Exception:
            self.processor = None
            LOGGER.info("DeepSeek processor unavailable, using infer-only path.")

    def unload(self) -> None:
        self.model = None
        self.tokenizer = None
        self.processor = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def clean_text(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r"\[\[.*?\]\]", "", text)
        return text.strip()

    def run_inference(self, image_path: str, original_size: Tuple[int, int]) -> Dict[str, Any]:
        self.load()
        temp_out = os.path.abspath(os.path.join(Config.UPLOAD_DIR, "deepseek_tmp"))
        os.makedirs(temp_out, exist_ok=True)

        with torch.inference_mode():
            if hasattr(self.model, "infer"):
                output_text = self.model.infer(
                    self.tokenizer,
                    image_file=image_path,
                    prompt=Config.DEEPSEEK_PROMPT,
                    output_path=temp_out,
                )
            else:
                if self.processor is None:
                    raise RuntimeError("DeepSeek model has no processor and no infer method.")

                image = Image.open(image_path).convert("RGB")
                try:
                    messages = [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image", "image": image},
                                {"type": "text", "text": Config.DEEPSEEK_PROMPT},
                            ],
                        }
                    ]
                    text_prompt = self.processor.apply_chat_template(
                        messages, add_generation_prompt=True
                    )
                except Exception:
                    text_prompt = Config.DEEPSEEK_PROMPT

                inputs = self.processor(text=text_prompt, images=image, return_tensors="pt").to(
                    self.model.device
                )
                if "pixel_values" in inputs:
                    inputs["images"] = [[inputs["pixel_values"][0], inputs["pixel_values"][0]]]
                    inputs.pop("pixel_values")

                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=2048,
                    do_sample=False,
                )
                generated_ids = generated_ids[:, inputs.input_ids.shape[1] :]
                output_text = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

        cleaned = self.clean_text(output_text or "")
        return self.build_text_lines(cleaned, original_size)


class GLMBackend(BaseBackend):
    name = "glm"
    model_id = Config.GLM_MODEL_ID

    def __init__(self) -> None:
        self.model = None
        self.processor = None

    def load(self) -> None:
        if self.model is not None:
            return

        LOGGER.info("Loading GLM fallback backend: %s", self.model_id)
        
        quantization_config = None
        if Config.LOAD_IN_4BIT:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16 if Config.HAS_BF16 else torch.float16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )

        self.model = AutoModelForImageTextToText.from_pretrained(
            self.model_id,
            torch_dtype=Config.GLM_DTYPE,
            trust_remote_code=True,
            device_map="auto" if Config.DEVICE == "cuda" else {"": "cpu"},
            quantization_config=quantization_config,
        )
        self.processor = AutoProcessor.from_pretrained(self.model_id, trust_remote_code=True)

    def unload(self) -> None:
        self.model = None
        self.processor = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def clean_text(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r"\[ACTUAL TEXT START\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(OCR|Text Recognition):\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"#{1,6}\s+", "", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        return text.strip()

    def run_inference(self, image_path: str, original_size: Tuple[int, int]) -> Dict[str, Any]:
        self.load()
        image = Image.open(image_path).convert("RGB")
        w, h = image.size
        min_dim = min(w, h)
        if min_dim < 256:
            scale = 256 / min_dim
            new_w, new_h = int(w * scale), int(h * scale)
            image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            LOGGER.info("Upscaled image from %sx%s to %sx%s", w, h, new_w, new_h)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": Config.GLM_PROMPT},
                ],
            }
        ]

        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.model.device)
        inputs.pop("token_type_ids", None)

        with torch.inference_mode():
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
                num_beams=1,
                use_cache=True,
            )

        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]

        cleaned = self.clean_text(output_text or "")
        result = self.build_text_lines(cleaned, original_size)
        result["raw"] = output_text or ""
        result["markdown"] = cleaned
        return result


class PaddleOCRBackend(BaseBackend):
    name = "paddleocr"
    model_id = "paddleocr_ko"

    def __init__(self) -> None:
        self.ocr = None

    def load(self) -> None:
        if self.ocr is not None:
            return

        LOGGER.info("Loading PaddleOCR backend (Korean)...")
        try:
            from paddleocr import PaddleOCR
            use_gpu = torch.cuda.is_available()
            self.ocr = PaddleOCR(lang='ko', use_angle_cls=True, use_gpu=use_gpu, show_log=False)
            LOGGER.info("PaddleOCR (Korean) loaded successfully. use_gpu=%s", use_gpu)
        except ImportError as exc:
            LOGGER.error("Failed to import paddleocr or paddlepaddle: %s", exc)
            raise RuntimeError("PaddleOCR is not installed. Please install it using: pip install paddlepaddle paddleocr")

    def unload(self) -> None:
        self.ocr = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def run_inference(self, image_path: str, original_size: Tuple[int, int]) -> Dict[str, Any]:
        self.load()
        try:
            res = self.ocr.ocr(image_path, cls=True)
        except Exception as exc:
            LOGGER.error("PaddleOCR inference failed: %s", exc)
            raise exc

        texts = []
        if res and isinstance(res, list):
            for page in res:
                if page:
                    for line in page:
                        if line and len(line) > 1 and line[1]:
                            text_val = line[1][0]
                            if text_val:
                                texts.append(text_val)

        cleaned = "\n".join(texts)
        cleaned = self.clean_text(cleaned)
        result = self.build_text_lines(cleaned, original_size)
        result["raw"] = cleaned
        result["markdown"] = cleaned
        return result


class OCRService:
    def __init__(self) -> None:
        self.backend_name = "glm" if should_use_glm_by_default() else "deepseek"
        self.backend = self._create_backend(self.backend_name)
        self.last_error: Optional[str] = None
        self._lock = threading.RLock()

    @staticmethod
    def _create_backend(name: str) -> BaseBackend:
        if name == "deepseek":
            return DeepSeekBackend()
        if name == "glm":
            return GLMBackend()
        if name == "paddleocr":
            return PaddleOCRBackend()
        raise ValueError(f"Unsupported backend: {name}")

    def switch_backend(self, name: str, reason: str) -> None:
        with self._lock:
            if self.backend_name == name:
                return

            LOGGER.warning("Switching OCR backend from %s to %s: %s", self.backend_name, name, reason)
            try:
                self.backend.unload()
            except Exception as exc:
                LOGGER.warning("Failed to unload %s backend cleanly: %s", self.backend_name, exc)

            if torch.cuda.is_available():
                try:
                    torch.cuda.synchronize()
                except Exception:
                    pass
                torch.cuda.empty_cache()

            self.backend_name = name
            self.backend = self._create_backend(name)

    def load_model(self) -> None:
        self.backend.load()

    def current_model_id(self) -> str:
        return self.backend.model_id

    def run_inference(self, image_path: str, original_size: Tuple[int, int]) -> Dict[str, Any]:
        start_time = time.time()
        with self._lock:
            try:
                result = self.backend.run_inference(image_path, original_size)
                elapsed = time.time() - start_time
                LOGGER.info(
                    "OCR completed in %.2fs using %s, lines=%s",
                    elapsed,
                    self.backend_name,
                    len(result.get("text_lines", [])),
                )
                return result
            except Exception as exc:
                self.last_error = str(exc)
                LOGGER.exception("OCR backend %s failed", self.backend_name)
    
                if self.backend_name == "deepseek":
                    reason = str(exc)
                    if "illegal memory access" in reason.lower() or "cuda error" in reason.lower():
                        self.switch_backend("glm", reason)
                        retry_result = self.backend.run_inference(image_path, original_size)
                        elapsed = time.time() - start_time
                        LOGGER.info(
                            "OCR recovered in %.2fs using GLM fallback, lines=%s",
                            elapsed,
                            len(retry_result.get("text_lines", [])),
                        )
                        return retry_result
    
                return {"text_lines": [], "raw": f"OCR error: {exc}", "markdown": ""}


ocr_service = OCRService()

PRELOAD_MODEL = os.environ.get("PRELOAD_MODEL", "true").lower() == "true"
if PRELOAD_MODEL:
    try:
        LOGGER.info("Pre-loading OCR backend: %s", ocr_service.backend_name)
        ocr_service.load_model()
        LOGGER.info("Backend ready: %s", ocr_service.current_model_id())
    except Exception as exc:
        LOGGER.exception("Primary backend preload failed")
        if ocr_service.backend_name != "glm":
            ocr_service.switch_backend("glm", f"preload failed: {exc}")
            ocr_service.load_model()
            LOGGER.info("Fallback backend ready: %s", ocr_service.current_model_id())


@route("/ocr", method=["POST", "HEAD", "GET"])
@route("/ocr_direct", method=["POST", "HEAD", "GET"])
def ocr_endpoint():
    if request.method in ("HEAD", "GET"):
        requested_backend = (request.query.get("backend") or "").lower()
        if requested_backend in ("deepseek", "glm", "paddleocr"):
            ocr_service.switch_backend(requested_backend, "requested by HOUZI settings")
        return {
            "status": "ready",
            "endpoint": "/ocr",
            "backend": ocr_service.backend_name,
            "model": ocr_service.current_model_id(),
        }

    requested_backend = (request.query.get("backend") or request.forms.get("backend") or "").lower()
    if requested_backend in ("deepseek", "glm", "paddleocr"):
        ocr_service.switch_backend(requested_backend, "requested by HOUZI settings")

    upload = request.files.get("upload")
    if not upload:
        return {"error": "No file uploaded."}

    _, ext = os.path.splitext(upload.filename)
    if ext.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"):
        return {"error": "File extension not allowed."}

    unique_id = uuid.uuid4().hex
    file_path = os.path.join(Config.UPLOAD_DIR, f"{unique_id}{ext}")

    try:
        upload.save(file_path)
        with Image.open(file_path) as img:
            original_size = img.size

        result = ocr_service.run_inference(file_path, original_size)
        return {
            "text_lines": result["text_lines"],
            "raw": result.get("raw", ""),
            "markdown": result.get("markdown", ""),
            "backend": ocr_service.backend_name,
            "model": ocr_service.current_model_id(),
        }
    except Exception as exc:
        LOGGER.exception("OCR request failed")
        response.status = 500
        return {"error": str(exc)}
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass


@route("/api/ocr/glm", method=["POST"])
def ocr_glm_direct_endpoint():
    """Dedicated GLM-OCR direct endpoint with grounding and coordinate support."""
    image_file = request.files.get("file") or request.files.get("image")
    if not image_file:
        response.status = 400
        return {"error": "Missing image file in form data (key: 'file' or 'image')."}

    file_id = str(uuid.uuid4())
    file_path = os.path.abspath(os.path.join(Config.UPLOAD_DIR, f"glm_{file_id}.png"))
    try:
        image_file.save(file_path)
        prompt = request.forms.get("prompt") or "OCR the text in this comic image. Return exact lines."
        
        from ocr_server.glm_comic_pipeline import GLMComicPipeline
        pipeline = GLMComicPipeline(model_id=Config.GLM_MODEL_ID, load_in_4bit=Config.LOAD_IN_4BIT)
        result = pipeline.infer_image(file_path, prompt=prompt)
        
        return {
            "status": "success",
            "backend": "glm",
            "model": Config.GLM_MODEL_ID,
            "raw_text": result["raw_text"],
            "grounded_boxes": result["grounded_boxes"],
            "latency_ms": result["latency_ms"],
            "image_size": result["image_size"]
        }
    except Exception as exc:
        LOGGER.exception("GLM direct OCR failed")
        response.status = 500
        return {"error": str(exc)}
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass


@route("/api/ocr/glm/batch_grid", method=["POST"])
def ocr_glm_batch_grid_endpoint():
    """Dobkle-style batch collage OCR: Packs multiple uploaded balloons and processes in 1 call."""
    files = request.files.getall("images") or request.files.getall("files")
    if not files:
        response.status = 400
        return {"error": "Missing image files in form data (key: 'images' or 'files')."}

    saved_paths = []
    batch_id = str(uuid.uuid4())[:8]
    try:
        for idx, f in enumerate(files):
            p = os.path.abspath(os.path.join(Config.UPLOAD_DIR, f"batch_{batch_id}_{idx}_{f.filename}"))
            f.save(p)
            saved_paths.append(p)

        grid_size = int(request.forms.get("grid_size", "3"))
        prompt = request.forms.get("prompt")

        from ocr_server.glm_comic_pipeline import GLMComicPipeline
        pipeline = GLMComicPipeline(model_id=Config.GLM_MODEL_ID, load_in_4bit=Config.LOAD_IN_4BIT)
        batch_results = pipeline.process_grid_batch(saved_paths, grid_size=grid_size, prompt=prompt)

        return {
            "status": "success",
            "backend": "glm-grid-collage",
            "batch_count": len(batch_results),
            "results": batch_results
        }
    except Exception as exc:
        LOGGER.exception("GLM batch grid OCR failed")
        response.status = 500
        return {"error": str(exc)}
    finally:
        for p in saved_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@route("/inpaint", method=["POST", "HEAD", "GET"])
def inpaint_endpoint():
    if request.method in ("HEAD", "GET"):
        return {"status": "ready", "endpoint": "/inpaint", "device": Config.DEVICE}

    image_file = request.files.get("image")
    mask_file = request.files.get("mask")
    if not image_file or not mask_file:
        response.status = 400
        return {"error": "Both image and mask files required."}

    import io
    from PIL import Image
    import numpy as np

    try:
        img_bytes = image_file.file.read()
        mask_bytes = mask_file.file.read()

        import cv2
        img_arr = np.frombuffer(img_bytes, np.uint8)
        mask_arr = np.frombuffer(mask_bytes, np.uint8)

        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        mask = cv2.imdecode(mask_arr, cv2.IMREAD_GRAYSCALE)

        if img is None or mask is None:
            response.status = 400
            return {"error": "Invalid image or mask data"}

        # Telea high-speed inpaint on server
        inpainted = cv2.inpaint(img, mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
        _, encoded = cv2.imencode(".png", inpainted)

        response.content_type = "image/png"
        return encoded.tobytes()
    except Exception as exc:
        LOGGER.exception("Inpaint request failed")
        response.status = 500
        return {"error": str(exc)}


@route("/health", method="GET")
def healthcheck():
    return json.dumps(
        {
            "status": "ok",
            "backend": ocr_service.backend_name,
            "model": ocr_service.current_model_id(),
            "device": Config.DEVICE,
            "model_loaded": getattr(ocr_service.backend, "model", None) is not None,
            "last_error": ocr_service.last_error,
        }
    )


@route("/<filepath:path>")
def serve_static(filepath):
    return static_file(filepath, root=Config.STATIC_ROOT)


if __name__ == "__main__":
    print("=" * 70)
    print("Hybrid OCR Direct Server")
    print(f"Server: http://{Config.HOST}:{Config.PORT}")
    print(f"Backend mode: {Config.OCR_BACKEND} -> active {ocr_service.backend_name}")
    print(f"Model: {ocr_service.current_model_id()}")
    print(f"Device: {Config.DEVICE}")
    print("=" * 70)
    
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer
    
    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True
        
    run(host=Config.HOST, port=Config.PORT, reloader=False, server_class=ThreadingWSGIServer)
