import io
import os
import sys
import time
import socket
import logging
from pathlib import Path
import cv2
import torch
import numpy as np
from bottle import Bottle, request, response, run

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("houmi-inpaint-server")

HOST = os.environ.get("INPAINT_HOST", "127.0.0.1")
PORT = int(os.environ.get("INPAINT_PORT", "2328"))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# Resolve model path exclusively inside Houmi backend directory
def _resolve_model_path() -> Path:
    server_dir = Path(__file__).resolve().parent
    backend_dir = server_dir.parent

    # Search directly in Houmi's official internal model paths
    candidates = [
        backend_dir / "models" / "inpainting" / "big-lama.pt",
        server_dir / "models" / "big-lama.pt",
        server_dir / "big-lama.pt",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "HoumiStudio" / "backend" / "models" / "inpainting" / "big-lama.pt",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "HoumiStudio" / "_internal" / "backend" / "models" / "inpainting" / "big-lama.pt",
        Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / "big-lama.pt",
    ]
    for c in candidates:
        if c.exists():
            return c
            
    # Default destination: Keep and store directly inside Houmi backend/models/inpainting/
    dest = backend_dir / "models" / "inpainting" / "big-lama.pt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest

MODEL_PATH = _resolve_model_path()

logger.info(f"Starting Houmi GPU Inpaint Server on device: {DEVICE.upper()} (PyTorch {torch.__version__})")
if DEVICE == "cuda":
    logger.info(f"NVIDIA GPU Active: {torch.cuda.get_device_name(0)}")

# Model singleton
_model = None

def get_or_load_model():
    global _model
    if _model is not None:
        return _model

    if not MODEL_PATH.exists():
        logger.info(f"Downloading Big-LaMa model to {MODEL_PATH}...")
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        torch.hub.download_url_to_file(
            "https://github.com/advimman/lama/releases/download/v0.1.0/big-lama.pt",
            str(MODEL_PATH),
            progress=True
        )

    logger.info(f"Loading TorchScript LaMa model from: {MODEL_PATH}")
    _model = torch.jit.load(str(MODEL_PATH), map_location=DEVICE)
    _model.eval()
    _model.to(DEVICE)
    logger.info(f"✅ LaMa model loaded into {DEVICE.upper()} VRAM successfully!")
    return _model


app = Bottle()


@app.route("/", method=["GET", "HEAD"])
def root():
    return {
        "status": "ready",
        "service": "Houmi GPU Inpaint Server",
        "device": DEVICE,
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "None",
        "port": PORT
    }


@app.route("/health", method="GET")
def health():
    return {
        "status": "ok",
        "device": DEVICE,
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "None"
    }


@app.route("/inpaint", method=["POST", "HEAD", "GET"])
def inpaint_endpoint():
    if request.method in ("HEAD", "GET"):
        return {"status": "ready", "endpoint": "/inpaint", "device": DEVICE}

    image_file = request.files.get("image") or request.files.get("file")
    mask_file = request.files.get("mask")

    if not image_file:
        response.status = 400
        return {"error": "Image file is required."}

    try:
        img_bytes = image_file.file.read()
        img_arr = np.frombuffer(img_bytes, np.uint8)
        img_bgr = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)

        if img_bgr is None:
            response.status = 400
            return {"error": "Invalid image data"}

        if not mask_file:
            _, enc = cv2.imencode('.png', img_bgr)
            response.content_type = "image/png"
            return enc.tobytes()

        mask_bytes = mask_file.file.read()
        mask_arr = np.frombuffer(mask_bytes, np.uint8)
        mask_gray = cv2.imdecode(mask_arr, cv2.IMREAD_GRAYSCALE)

        if mask_gray is None or np.count_nonzero(mask_gray) == 0:
            _, enc = cv2.imencode('.png', img_bgr)
            response.content_type = "image/png"
            return enc.tobytes()

        orig_h, orig_w = img_bgr.shape[:2]

        # Convert to RGB float32 tensor
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        img_tensor = torch.from_numpy(img_rgb.transpose(2, 0, 1)).float().unsqueeze(0) / 255.0
        mask_tensor = torch.from_numpy(mask_gray).float().unsqueeze(0).unsqueeze(0)
        mask_tensor = (mask_tensor > 0).float()

        # Pad to multiple of 8 if needed
        pad_h = (8 - orig_h % 8) % 8
        pad_w = (8 - orig_w % 8) % 8
        if pad_h > 0 or pad_w > 0:
            img_tensor = torch.nn.functional.pad(img_tensor, (0, pad_w, 0, pad_h), mode="reflect")
            mask_tensor = torch.nn.functional.pad(mask_tensor, (0, pad_w, 0, pad_h), mode="reflect")

        img_tensor = img_tensor.to(DEVICE)
        mask_tensor = mask_tensor.to(DEVICE)

        model = get_or_load_model()
        with torch.inference_mode():
            out_tensor = model(img_tensor, mask_tensor)

        # Remove padding
        if pad_h > 0 or pad_w > 0:
            out_tensor = out_tensor[:, :, :orig_h, :orig_w]

        out_img = (out_tensor[0].permute(1, 2, 0).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        out_bgr = cv2.cvtColor(out_img, cv2.COLOR_RGB2BGR)

        # Blend only inside mask
        mask_blur = cv2.GaussianBlur(mask_gray, (3, 3), 0).astype(np.float32) / 255.0
        mask_3d = np.expand_dims(mask_blur, axis=2)
        blended = (out_bgr.astype(np.float32) * mask_3d + img_bgr.astype(np.float32) * (1.0 - mask_3d)).astype(np.uint8)

        _, encoded = cv2.imencode(".png", blended)
        response.content_type = "image/png"
        return encoded.tobytes()

    except Exception as exc:
        logger.exception("Inpainting inference failed")
        response.status = 500
        return {"error": str(exc)}


if __name__ == "__main__":
    logger.info("⚡ Pre-warming PyTorch GPU Inpaint model...")
    try:
        get_or_load_model()
    except Exception as e_load:
        logger.warning("Startup model pre-load failed (will retry on first request): %s", e_load)
    logger.info(f"🚀 Houmi GPU Inpaint Server ready on http://{HOST}:{PORT}")
    run(app, host=HOST, port=PORT, reloader=False)
