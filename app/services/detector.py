from typing import Any, Callable, Optional
from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode
import ast
import json
import logging
import math
import time
import numpy as np
try:
    import onnxruntime as ort
except ImportError:
    ort = None
import cv2
from pathlib import Path
from app.config import BALLOON_MODEL_PATH, BALLOON_CONFIG_PATH, ACTIVE_LEARNED_MODEL_PATH, MODELS_DIR, get_execution_providers

logger = logging.getLogger("houmi-detector")

def get_model_path(model_name: str | None = None) -> Path:
    """
    Resolves the requested balloon model setting/name to an ONNX model file path.
    Defaults to the original SAO Balloon model if omitted, unrecognized, or missing.
    """
    if not model_name:
        return BALLOON_MODEL_PATH

    model_str = str(model_name).strip()

    # SAO Default aliases
    if model_str in [
        "sao_balloon_beta",
        "korean_webtoon",
        "Korean Webtoon (YOLOv8)",
        "เวอร์ชั่นเบต้าเทสแอลฟ่าโอเมก้าแห่ง SAO",
        "Default SAO Balloon Model",
        "Default Manga Balloon-YOLO11",
    ]:
        return BALLOON_MODEL_PATH

    # Chinese Webtoon SQ Model
    if model_str in ["chinese_webtoon", "Chinese Webtoon (SQ)", "chinese_sq", "Manhua Chinese Model"]:
        p = MODELS_DIR / "chinese_webtoon" / "model.onnx"
        if p.exists():
            return p

    # Comic-Translate 8k Multi-Style Model
    if model_str in ["comic-speech-bubble", "comic_speech_bubble", "Comic-Translate (8k Multi-Style)", "comic_translate"]:
        p = MODELS_DIR / "comic-speech-bubble" / "model.onnx"
        if p.exists():
            return p

    # Manga Panel & Text YOLO26n Model
    if model_str in ["manga-panel", "manga_panel", "Manga Panel & Text (YOLO26n)", "manga_panel_yolo26"]:
        p = MODELS_DIR / "manga-panel" / "model.onnx"
        if p.exists():
            return p

    # RF-DETR Transformer Model
    if model_str in ["rfdetr", "RF-DETR (Transformer)", "rf_detr"]:
        p = MODELS_DIR / "rfdetr" / "model.onnx"
        if p.exists():
            return p

    # Japanese Manga & CG YOLO11s Model
    if model_str in ["japanese-manga", "japanese_manga", "Japanese Manga & CG (YOLO11s)"]:
        p = MODELS_DIR / "japanese-manga" / "model.onnx"
        if p.exists():
            return p

    # Active learned model alias
    if model_str in [
        "active_learned",
        "Active Learned Model",
        "Active Learned Model (โมเดลที่ปรับจูนจากระบบ)",
    ]:
        if ACTIVE_LEARNED_MODEL_PATH.exists():
            return ACTIVE_LEARNED_MODEL_PATH
        logger.warning(
            f"Active learned model requested ('{model_str}') but file not found at {ACTIVE_LEARNED_MODEL_PATH}. Falling back to default SAO model."
        )
        return BALLOON_MODEL_PATH

    # Custom folder or file paths under MODELS_DIR
    custom_subfolder = MODELS_DIR / model_str / "model.onnx"
    if custom_subfolder.exists():
        return custom_subfolder

    custom_file = MODELS_DIR / model_str
    if custom_file.exists():
        return custom_file

    logger.warning(f"Unrecognized balloon model '{model_str}'. Falling back to default SAO model.")
    return BALLOON_MODEL_PATH


def is_valid_text_bubble(img_crop) -> bool:
    """
    Checks if a cropped image of a speech balloon actually contains text.
    Uses Adaptive Thresholding, Contour area/aspect ratio analysis, contrast filtering, and edge density.
    """
    if img_crop is None or img_crop.size == 0:
        return False
        
    h, w = img_crop.shape[:2]
    # Small or extremely flat boxes are usually noise/garbage
    if w < 15 or h < 15:
        return False
        
    # Convert to grayscale
    gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY)
    mean_val = float(np.mean(gray))

    # Reject almost pure solid black (< 10) or pure solid white (> 248) areas
    if mean_val < 10.0 or mean_val > 248.0:
        return False

    # Calculate contrast range (max - min intensity)
    min_val, max_val, _, _ = cv2.minMaxLoc(gray)
    contrast = max_val - min_val
    if contrast < 45:
        # Too low contrast, likely empty/solid background
        return False
        
    # Edge density check using Canny
    edges = cv2.Canny(gray, 50, 150)
    edge_pixels = np.sum(edges == 255)
    edge_density = edge_pixels / float(h * w)
    
    # Empty bubbles have near 0 edge density, text-filled bubbles are higher
    # Extremely low edge density implies it is just white background or background noise
    if edge_density < 0.004:
        return False

    # Adaptive thresholding to detect high-contrast structures (text characters)
    # Binary inverse so that dark text characters become white (255) on black bg
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 3
    )
    
    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    text_like_elements = 0
    for cnt in contours:
        x_c, y_c, w_c, h_c = cv2.boundingRect(cnt)
        
        # Filter out extreme shapes
        # 1. Skip tiny noise pixels
        if w_c < 2 or h_c < 4:
            continue
            
        # 2. Skip excessively large contours (e.g. bubble outer borders)
        if w_c > w * 0.9 or h_c > h * 0.9:
            continue
            
        # 3. Skip flat panel dividers or horizontal mouth/shadow lines
        aspect_ratio = float(w_c) / h_c
        if aspect_ratio > 6.5 or aspect_ratio < 0.15:
            continue
            
        text_like_elements += 1
        
    # Speech bubbles with text should contain at least 2-3 characters (depending on size)
    min_elements = 3 if w > 50 else 2
    if text_like_elements < min_elements:
        return False
        
    return True


def is_high_quality_text(crop: np.ndarray, border_std_thresh: float = 25.0, laplacian_var_thresh: float = 15000.0) -> bool:
    """
    Checks if a cropped image contains high-contrast text using border uniformity (to reject
    busy background artwork/details) and Laplacian variance (to reject soft gradient/shading details).
    """
    if crop is None or crop.size == 0:
        return False
    h, w = crop.shape[:2]
    if w < 15 or h < 15:
        return False
        
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # 1. Check border uniformity (standard deviation of the outermost crop boundary)
    border_pixels = []
    border_pixels.extend(gray[0:2, :].flatten())
    border_pixels.extend(gray[-2:, :].flatten())
    border_pixels.extend(gray[:, 0:2].flatten())
    border_pixels.extend(gray[:, -2:].flatten())
    border_std = np.std(border_pixels) if len(border_pixels) > 0 else 0.0
    if border_std > border_std_thresh:
        return False
        
    # 2. Check Laplacian variance (high-frequency sharpness of edges)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian_var < laplacian_var_thresh:
        return False
        
    return True


class BalloonDetector:
    def __init__(self):
        self.session = None
        self.inp_width = 640
        self.inp_height = 640
        self.conf_threshold = 0.25
        self.nms_threshold = 0.5
        self.ratio = 1.0
        self.height_overlap = 20  # Percentage overlap for vertical sliding window
        self.classes = ["text", "bubble"]
        self._classes_explicit = False
        
        # Load configuration if exists
        if BALLOON_CONFIG_PATH.exists():
            try:
                with open(BALLOON_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.inp_width = cfg.get("width", 640)
                    self.inp_height = cfg.get("height", 640)
                    self.ratio = cfg.get("ratio", 1.0)
                    self.conf_threshold = float(cfg.get("conf_threshold", 0.25))
                    if isinstance(cfg.get("classes"), list) and cfg.get("classes"):
                        self.classes = [str(name) for name in cfg["classes"]]
                        self._classes_explicit = True
                    # Read overlap percentage from config (default 20%)
                    try:
                        self.height_overlap = int(cfg.get("height_overlap", 20))
                    except (ValueError, TypeError):
                        self.height_overlap = 20
                    logger.info(f"Loaded model config: {self.inp_width}x{self.inp_height}, ratio: {self.ratio}, height_overlap: {self.height_overlap}%, conf_threshold: {self.conf_threshold}")
            except Exception as e:
                logger.error(f"Error loading model config: {e}")
 
    def load_model(self, execution_provider: str = None, model_name: str = None):
        target_path = get_model_path(model_name)
        providers = get_execution_providers(execution_provider)
        if (
            self.session is not None
            and getattr(self, "current_providers", None) == providers
            and getattr(self, "current_model_path", None) == str(target_path)
        ):
            return
            
        logger.info(f"Loading ONNX Model from: {target_path} with providers={providers}")
        if not target_path.exists():
            raise FileNotFoundError(f"ONNX Model not found at {target_path}")
 
        from app.config import create_onnx_session_options
        opts = create_onnx_session_options() or ort.SessionOptions()

        try:
            self.session = ort.InferenceSession(str(target_path), sess_options=opts, providers=providers)
            active_providers = self.session.get_providers()
            self.current_providers = active_providers
            self.current_model_path = str(target_path)
            hw_str = active_providers[0] if active_providers else "CPUExecutionProvider"
            logger.info("🚀 [GPU DETECTOR ACTIVE] Hardware: %s | Model: %s", hw_str, target_path.name)
        except Exception as e:
            logger.warning(f"Failed to initialize {providers} Provider. Falling back to CPU: {e}")
            self.session = ort.InferenceSession(str(target_path), sess_options=opts, providers=["CPUExecutionProvider"])
            self.current_providers = ["CPUExecutionProvider"]
            self.current_model_path = str(target_path)
            logger.info("ℹ️ [CPU DETECTOR FALLBACK] Hardware: CPUExecutionProvider | Model: %s", target_path.name)

        # Prefer the class names embedded by Ultralytics when the model config
        # does not explicitly override them.  The bundled SAO model is named
        # ``{0: balloon, 1: other}``, not ``{0: text, 1: bubble}``; treating its
        # balloon class as text makes the full balloon bbox appear as a text box.
        if not self._classes_explicit:
            try:
                metadata_names = self.session.get_modelmeta().custom_metadata_map.get("names", "")
                try:
                    parsed_names = ast.literal_eval(metadata_names) if metadata_names else {}
                except (SyntaxError, ValueError):
                    parsed_names = json.loads(metadata_names) if metadata_names else {}
                if isinstance(parsed_names, dict):
                    ordered_names = [str(parsed_names[key]) for key in sorted(parsed_names, key=lambda key: int(key))]
                    if ordered_names:
                        self.classes = ordered_names
                        logger.info("Using model metadata classes: %s", self.classes)
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                logger.debug("Could not read detector class metadata: %s", exc)

        # Dynamically adapt input shape to model specs
        try:
            in_shape = self.session.get_inputs()[0].shape
            if len(in_shape) == 4:
                if isinstance(in_shape[2], int) and in_shape[2] > 0:
                    self.inp_height = in_shape[2]
                if isinstance(in_shape[3], int) and in_shape[3] > 0:
                    self.inp_width = in_shape[3]
            logger.info(f"BalloonDetector model input shape: {self.inp_width}x{self.inp_height}")
        except Exception as e:
            logger.warning(f"Could not parse model input shape: {e}")

    def unload_model(self):
        self.session = None
        self.current_providers = None
        self.current_model_path = None
        # Trigger garbage collection and clear CUDA cache if torch is available
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("Cleared CUDA Cache for model unload")
        except ImportError:
            pass

    def detect_high_contrast_text(self, img: np.ndarray) -> list:
        """
        Detects bubble-less, high-contrast stylized text/SFX using traditional computer vision:
        Morphological Gradient + Otsu thresholding + Morphological Close + is_valid_text_bubble contour filtering.
        Runs vertical and horizontal contour extraction separately to prevent bridging.
        """
        if img is None or img.size == 0:
            return []
            
        orig_h, orig_w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. Morphological Gradient to isolate edges/outlines
        grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
        
        # 2. Otsu thresholding to binarize
        _, grad_thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 3. Morphological closing to group characters into vertical and horizontal text lines separately
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 25))
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
        
        closed_v = cv2.morphologyEx(grad_thresh, cv2.MORPH_CLOSE, kernel_v)
        closed_h = cv2.morphologyEx(grad_thresh, cv2.MORPH_CLOSE, kernel_h)
        
        detections = []
        
        # 4a. Find vertical contours (vertical text/SFX)
        contours_v, _ = cv2.findContours(closed_v, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours_v:
            x, y, bw, bh = cv2.boundingRect(cnt)
            # Skip very small noise regions
            if bw > 25 and bh > 25:
                # Reject contours that span almost the entire page width (panel lines/borders)
                if bw > 0.75 * orig_w:
                    continue
                crop = img[y:y+bh, x:x+bw]
                if is_high_quality_text(crop) and is_valid_text_bubble(crop):
                    detections.append({
                        "x": float(x),
                        "y": float(y),
                        "width": float(bw),
                        "height": float(bh),
                        "rotation_deg": 0.0,
                        "confidence": 0.65,
                        "balloon_type": "bubble"
                    })
                    
        # 4b. Find horizontal contours (horizontal text/SFX)
        contours_h, _ = cv2.findContours(closed_h, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours_h:
            x, y, bw, bh = cv2.boundingRect(cnt)
            # Skip very small noise regions
            if bw > 25 and bh > 25:
                # Reject contours that span almost the entire page width (panel lines/borders)
                if bw > 0.75 * orig_w:
                    continue
                crop = img[y:y+bh, x:x+bw]
                if is_high_quality_text(crop) and is_valid_text_bubble(crop):
                    detections.append({
                        "x": float(x),
                        "y": float(y),
                        "width": float(bw),
                        "height": float(bh),
                        "rotation_deg": 0.0,
                        "confidence": 0.65,
                        "balloon_type": "bubble"
                    })
        return detections

    def detect(self, img_path: str, min_confidence: float = None, execution_provider: str = None, model_name: str = None, cancel_check: Any = None) -> list:
        if cancel_check and cancel_check():
            logger.info("Balloon detection cancelled before start by user cancel request.")
            return []

        self.load_model(execution_provider=execution_provider, model_name=model_name)
        
        # Load image via OpenCV
        img = cv2_imread_unicode(img_path)
        if img is None:
            raise ValueError(f"Could not load image at {img_path}")
            
        orig_h, orig_w = img.shape[:2]

        # === Pre-resize: Scale entire image to model input width, preserving aspect ratio ===
        # This matches ImageTrans's preprocessing strategy for the SAO model.
        # Instead of stretching arbitrary-sized tiles to 640x640 (distorting aspect ratio),
        # we resize the full image to 640px wide first, then slide 640x640 windows vertically.
        target_w = self.inp_width
        scale = target_w / orig_w
        target_h = int(orig_h * scale)
        img_resized = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        # Tiling: Slide inp_height-tall windows vertically on the resized image
        tile_h = self.inp_height
        stride = max(1, int(tile_h * (1 - self.height_overlap / 100)))

        ys = []
        y = 0
        while True:
            ys.append(y)
            if y + tile_h >= target_h:
                break
            y = min(target_h - tile_h, y + stride)

        # Determine confidence threshold to use for filtering
        conf_limit = min_confidence if min_confidence is not None else self.conf_threshold
        logger.info(f"Starting balloon detection. Image: {orig_w}x{orig_h}, Resized: {target_w}x{target_h}, Scale: {scale:.4f}, Tiles: {len(ys)}, Stride: {stride}, Confidence Limit: {conf_limit}")

        all_detections = []

        for tile_y in ys:
            if cancel_check and cancel_check():
                logger.info('Balloon detection cancelled early by user cancel request.')
                return []
            # Crop tile from resized image
            crop_end_y = min(target_h, tile_y + tile_h)
            crop = img_resized[tile_y:crop_end_y, 0:target_w]
            ch, cw = crop.shape[:2]

            # Pad with black if crop is smaller than tile size (bottom edge)
            if ch != tile_h or cw != target_w:
                padded = np.zeros((tile_h, target_w, 3), dtype=np.uint8)
                padded[:ch, :cw] = crop
                crop = padded

            # ImageTrans feeds the OpenCV/ONNX image buffer in BGR order.  Keeping
            # that contract matters: RGB produces valid detections, but selects a
            # different anchor as the highest-confidence text box.
            blob = crop.astype(np.float32) / 255.0
            blob = np.transpose(blob, (2, 0, 1))  # HWC to CHW
            blob = np.expand_dims(blob, axis=0)    # CHW to NCHW
            
            # Run inference
            input_name = self.session.get_inputs()[0].name
            outputs = self.session.run(None, {input_name: blob})
            
            output = np.squeeze(outputs[0])
            if output.shape[0] < output.shape[1]:
                output = output.T
                
            num_predictions, num_channels = output.shape
            num_classes = len(self.classes)
            has_theta = (num_channels == 4 + num_classes + 1)
            
            for i in range(num_predictions):
                row = output[i]
                x_c, y_c, bw, bh = row[0:4]
                
                if has_theta:
                    scores = row[4:-1]
                    theta = row[-1]
                    deg = float(np.degrees(theta))
                else:
                    scores = row[4:]
                    deg = 0.0
                    
                class_id = np.argmax(scores)
                score = scores[class_id]
                
                if score >= conf_limit:
                    # Coordinates are in tile space (640x640)
                    x1 = x_c - bw / 2.0
                    y1 = y_c - bh / 2.0
                    x2 = x_c + bw / 2.0
                    y2 = y_c + bh / 2.0
                    
                    # Clamp to actual content area (exclude black padding)
                    x1 = max(0.0, min(x1, float(cw)))
                    y1 = max(0.0, min(y1, float(ch)))
                    x2 = max(0.0, min(x2, float(cw)))
                    y2 = max(0.0, min(y2, float(ch)))
                    
                    if x2 <= x1 or y2 <= y1:
                        continue
                    
                    # Offset Y to resized-image space, then scale back to original space
                    detection_class = (
                        str(self.classes[class_id]).strip().lower()
                        if 0 <= class_id < len(self.classes)
                        else f"class_{class_id}"
                    )
                    all_detections.append({
                        "x": float(x1 / scale),
                        "y": float((y1 + tile_y) / scale),
                        "width": float((x2 - x1) / scale),
                        "height": float((y2 - y1) / scale),
                        "rotation_deg": deg,
                        "confidence": float(score),
                        # TextBlock.balloon_type is a semantic/typesetting value,
                        # not the detector class. Keep the two concepts separate.
                        "balloon_type": "bubble",
                        "detection_class": detection_class,
                    })

        # === Post-processing matching ImageTrans text-area semantics ===
        #
        # The model exposes separate `text` and `bubble` classes.  Houmi used to
        # union both kinds of overlapping predictions and then proximity-merge
        # them transitively.  That turned a tight text area into a balloon-sized
        # (or larger) rectangle.  Text layers must originate only from the text
        # class; balloon geometry is derived independently by layout_region.
        # NMS removes duplicate anchors without changing the geometry of the
        # strongest prediction.  Balloon-class models intentionally retain their
        # full balloon geometry here; TextBlock/layout semantics are resolved by
        # the caller.
        # Do not run a second union/merge pass here: two neighbouring speech
        # balloons can overlap in the artwork and a union would create one
        # oversized rectangle spanning both balloons.
        merged = class_aware_nms(all_detections, 0.30)
        configured_classes = {str(name).strip().lower() for name in self.classes}
        if "text" in configured_classes:
            merged = [box for box in merged if box.get("detection_class") == "text"]
        elif "balloon" in configured_classes:
            # SAO's positive class is ``balloon``.  ``other`` is background /
            # non-balloon and must not become a TextBlock candidate.
            merged = [box for box in merged if box.get("detection_class") == "balloon"]
        elif "bubble" in configured_classes:
            merged = [box for box in merged if box.get("detection_class") == "bubble"]

        # 2. Merge nearby text lines belonging to the same speech balloon (ImageTrans parity)
        # ONLY merge proximity for text-line models where each line is a separate detection.
        # For balloon models (where each detection is a full balloon), adjacent separate balloons must remain distinct!
        if "text" in configured_classes and "balloon" not in configured_classes and "bubble" not in configured_classes:
            proximity_merged = merge_proximity(merged, dist_thresh=15)
        else:
            proximity_merged = merged

        # 3. Size filter: remove garbage boxes that are too small (ImageTrans defaults)
        size_filtered = []
        for box in proximity_merged:
            bw = box["width"]
            bh = box["height"]
            if bw >= 30 and bh >= 25 and (bw * bh) >= 800:
                size_filtered.append(box)
            else:
                logger.info(f"Size filter: Removed small box w={bw:.0f}, h={bh:.0f}")

        # 4. Auto Safety Expansion:
        # For text models: +10px padding and 1.03x scale around center (ImageTrans formula).
        # For balloon models: subtle +2px padding to avoid over-inflating full balloon contours.
        final_boxes = []
        for box in size_filtered:
            if box.get("detection_class") in ("balloon", "bubble"):
                expanded = expand_bbox(box, ratio=1.00, pad=2.0, max_w=orig_w, max_h=orig_h)
            else:
                expanded = expand_bbox(box, ratio=1.03, pad=10.0, max_w=orig_w, max_h=orig_h)

            bx = int(expanded["x"])
            by = int(expanded["y"])
            bw = int(expanded["width"])
            bh = int(expanded["height"])

            # Clamp bounds
            bx = max(0, min(bx, orig_w - 1))
            by = max(0, min(by, orig_h - 1))
            bw = max(1, min(bw, orig_w - bx))
            bh = max(1, min(bh, orig_h - by))

            crop_area = img[by:by+bh, bx:bx+bw]
            if is_valid_text_bubble(crop_area):
                final_boxes.append(expanded)
            else:
                logger.info(f"Smart Filter: Removed empty/garbage balloon box at x={bx}, y={by}, w={bw}, h={bh}")

        # Sort left-to-right, top-to-bottom for natural reading order
        final_boxes.sort(key=lambda b: (b["y"] // 50, b["x"]))

        logger.info(f"Detected {len(final_boxes)} text region blocks after proximity merge & safety expansion.")
        return final_boxes


def overlap_percent(a, b):
    # a: [x1, y1, x2, y2], b: [x1, y1, x2, y2]
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(1.0, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / min(area_a, area_b)


def compute_smart_balloon_bounds(
    image: np.ndarray,
    text_bbox: dict,
    rival_boxes: list[dict] | None = None,
    inset_ratio: float = 0.10,
    settings: dict | None = None,
) -> dict:
    """
    Computes exact balloon mask bounds using Smart Balloon V15 Universal Engine
    with graceful fallback to SAM 2.1 / standard bbox.

    Pass project `settings` to honor the per-project `smart_balloon_adaptive`
    toggle (V16 adaptive background handling).
    """
    if text_bbox.get("balloon_type") == "sfx":
        return _smart_balloon_fallback(
            text_bbox["x"], text_bbox["y"],
            text_bbox["width"], text_bbox["height"],
            "sfx_fallback",
        )

    from app.config import get_smart_balloon_adaptive_enabled

    try:
        from app.services.smart_balloon import process_smart_balloon_v15
        v15_res = process_smart_balloon_v15(
            image, text_bbox,
            rival_boxes=rival_boxes,
            inset_ratio=inset_ratio,
            use_adaptive=get_smart_balloon_adaptive_enabled(settings),
        )
        if v15_res.get("success"):
            return v15_res
    except Exception as exc:
        logger.warning("Smart Balloon V15 encountered error: %s, trying SAM fallback", exc)

    try:
        sam_box_res = _sam_box_fallback_result(image, text_bbox, inset_ratio=inset_ratio)
    except Exception as exc:
        logger.warning("SAM box fallback failed: %s", exc)
        sam_box_res = None
    if sam_box_res is not None:
        return sam_box_res

    img_h, img_w = image.shape[:2]
    bx, by = float(text_bbox["x"]), float(text_bbox["y"])
    bw, bh = float(text_bbox["width"]), float(text_bbox["height"])

    # ------------------------------------------------------------------
    # Step 1: White connected component detection (severing connected balloon bridges)
    # ------------------------------------------------------------------
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
    open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    opened_thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, open_k)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        opened_thresh, connectivity=4,
    )

    box_labels = labels[int(by):int(by + bh), int(bx):int(bx + bw)]
    unique, counts = np.unique(box_labels, return_counts=True)
    best_label, best_count = 0, 0
    for lbl, cnt in zip(unique, counts):
        if lbl > 0 and cnt > best_count:
            best_label, best_count = lbl, cnt

    if best_label == 0:
        return _smart_balloon_fallback(bx, by, bw, bh, "skip_not_white")

    comp_x, comp_y, comp_w, comp_h, comp_area = stats[best_label]

    if comp_w > img_w * 0.9 and comp_h > img_h * 0.5:
        return _smart_balloon_fallback(bx, by, bw, bh, "fallback_page_bg")

    # ------------------------------------------------------------------
    # Step 2: Dynamic crop (union of text bbox + white component + padding)
    # ------------------------------------------------------------------
    union_x = min(bx, comp_x)
    union_y = min(by, comp_y)
    union_r = max(bx + bw, comp_x + comp_w)
    union_b = max(by + bh, comp_y + comp_h)
    pad = 100
    sx0 = max(0, int(union_x - pad))
    sy0 = max(0, int(union_y - pad))
    sx1 = min(img_w, int(union_r + pad))
    sy1 = min(img_h, int(union_b + pad))
    crop = image[sy0:sy1, sx0:sx1]
    if crop.size == 0:
        return _smart_balloon_fallback(bx, by, bw, bh, "fallback_empty_crop")

    local_bx = bx - sx0
    local_by = by - sy0
    crop_h, crop_w = crop.shape[:2]

    # ------------------------------------------------------------------
    # Step 3: SAM 2.1 inference (5 positive + 4 negative corner points)
    # ------------------------------------------------------------------
    pts_pos = [
        (local_bx + bw * 0.5, local_by + bh * 0.5),   # center
        (local_bx + bw * 0.2, local_by + bh * 0.2),
        (local_bx + bw * 0.8, local_by + bh * 0.2),
        (local_bx + bw * 0.2, local_by + bh * 0.8),
        (local_bx + bw * 0.8, local_by + bh * 0.8),
    ]

    pts_neg = [
        (10, 10),
        (crop_w - 10, 10),
        (10, crop_h - 10),
        (crop_w - 10, crop_h - 10),
    ]

    coords = []
    pt_labels = []
    for x, y in pts_pos:
        coords.append([x, y])
        pt_labels.append(1)
    for x, y in pts_neg:
        coords.append([x, y])
        pt_labels.append(0)

    from app.services.sam_segmenter import _get_sam, _SAM_INPUT_SIZE

    sam = _get_sam()
    if sam is None:
        return _smart_balloon_fallback(bx, by, bw, bh, "fallback_sam_unavailable")

    embeddings = sam.encode(crop)
    scale = sam._cached_scale
    sc_coords = [[x * scale, y * scale] for x, y in coords]

    outputs = sam.decoder.run(
        None,
        {
            "image_embed": embeddings["image_embed"],
            "high_res_feats_0": embeddings["high_res_feats_0"],
            "high_res_feats_1": embeddings["high_res_feats_1"],
            "point_coords": np.array([sc_coords], dtype=np.float32),
            "point_labels": np.array([pt_labels], dtype=np.float32),
            "mask_input": np.zeros((1, 1, 256, 256), dtype=np.float32),
            "has_mask_input": np.array([0.0], dtype=np.float32),
        },
    )

    mask_logits = outputs[0][0, int(np.argmax(outputs[1][0]))]
    out_h, out_w = mask_logits.shape[:2]
    valid_h = min(int(crop_h * scale / _SAM_INPUT_SIZE * out_h + 0.5), out_h)
    valid_w = min(int(crop_w * scale / _SAM_INPUT_SIZE * out_w + 0.5), out_w)
    sam_mask = (
        cv2.resize(
            mask_logits[:valid_h, :valid_w].astype(np.float32),
            (crop_w, crop_h),
        )
        > 0.0
    ).astype(np.uint8) * 255

    # Pick the SAM connected component that covers the text points
    num_labels2, cc_labels, stats2, _ = cv2.connectedComponentsWithStats(
        sam_mask, connectivity=8,
    )
    best_label2, best_count2 = 0, -1
    for i in range(1, num_labels2):
        count = sum(
            1 for px, py in pts_pos if cc_labels[int(py), int(px)] == i
        )
        if count > best_count2:
            best_count2, best_label2 = count, i

    if best_label2 == 0:
        return _smart_balloon_fallback(bx, by, bw, bh, "fallback_no_comp")

    comp_mask = (cc_labels == best_label2).astype(np.uint8) * 255
    contours, _ = cv2.findContours(
        comp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
    )
    filled_mask = np.zeros_like(comp_mask)
    cv2.drawContours(filled_mask, contours, -1, 255, -1)

    # Check if SAM mask covers too much of the crop (= background, not balloon)
    sam_area = cv2.countNonZero(filled_mask)
    crop_area = crop_h * crop_w
    if sam_area > crop_area * 0.70:
        return _smart_balloon_fallback(bx, by, bw, bh, "fallback_too_big")

    # ------------------------------------------------------------------
    # Step 4: Construct clean inner-white balloon mask (Seed-based + Strict Margin)
    # ------------------------------------------------------------------
    crop_gray = gray[sy0:sy1, sx0:sx1]

    # Find white seed pixel (> 180) inside text box ROI closest to center
    roi_y0 = max(0, int(local_by))
    roi_y1 = min(crop_h, int(local_by + bh))
    roi_x0 = max(0, int(local_bx))
    roi_x1 = min(crop_w, int(local_bx + bw))
    roi = crop_gray[roi_y0:roi_y1, roi_x0:roi_x1]

    yw, xw = np.where(roi > 180)
    if len(xw) > 0:
        roi_cx = (roi_x1 - roi_x0) / 2
        roi_cy = (roi_y1 - roi_y0) / 2
        dists = (xw - roi_cx) ** 2 + (yw - roi_cy) ** 2
        best_idx = np.argmin(dists)
        cx_seed = roi_x0 + int(xw[best_idx])
        cy_seed = roi_y0 + int(yw[best_idx])
    else:
        cx_seed = int(local_bx + bw / 2)
        cy_seed = int(local_by + bh / 2)

    _, white_bin = cv2.threshold(crop_gray, 195, 255, cv2.THRESH_BINARY)
    num_l, l_map, stats_map, _ = cv2.connectedComponentsWithStats(white_bin, connectivity=4)
    target_l = l_map[min(crop_h - 1, max(0, cy_seed)), min(crop_w - 1, max(0, cx_seed))]

    if target_l > 0:
        balloon_comp = (l_map == target_l).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(balloon_comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled_balloon = np.zeros_like(crop_gray)
        if cnts:
            cv2.drawContours(filled_balloon, cnts, -1, 255, -1)
        else:
            filled_balloon = balloon_comp
        # Intersect with SAM 2.1 mask to prevent leaking outside balloon boundaries
        filled_balloon = cv2.bitwise_and(filled_balloon, filled_mask)
    else:
        # Non-white text box (gradient/dark background) — fall back to standard text bbox
        return _smart_balloon_fallback(bx, by, bw, bh, "fallback_not_white")

    # Erode 9px inside to keep mask comfortably away from black border stroke
    erode_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    final_mask = cv2.erode(filled_balloon, erode_k, iterations=1)
    if cv2.countNonZero(final_mask) == 0:
        final_mask = filled_balloon

    nz = cv2.findNonZero(final_mask)
    if nz is None:
        return _smart_balloon_fallback(bx, by, bw, bh, "fallback_end")

    mx, my, mw, mh = cv2.boundingRect(nz)

    # Convert to page coordinates
    abs_x = float(sx0 + mx)
    abs_y = float(sy0 + my)
    abs_w = float(mw)
    abs_h = float(mh)

    mask_area = cv2.countNonZero(final_mask)
    return {
        "smart_x": abs_x,
        "smart_y": abs_y,
        "smart_width": abs_w,
        "smart_height": abs_h,
        "crop_mask": final_mask,
        "crop_offset": (sx0, sy0),
        "mask_area": mask_area,
        "method": "clean_seed_balloon",
    }


def _smart_balloon_fallback(bx, by, bw, bh, method) -> dict:
    return {
        "smart_x": float(bx), "smart_y": float(by),
        "smart_width": float(bw), "smart_height": float(bh),
        "mask_area": 0, "method": method,
    }


def _sam_box_fallback_result(
    image: np.ndarray,
    text_bbox: dict,
    inset_ratio: float = 0.10,
) -> dict | None:
    """
    SAM 2.1 box-prompt fallback for balloons/boxes without a white interior
    (textured system panels, gradient boxes, dark bubbles).

    Runs AFTER the V15 engine fails and BEFORE the legacy white-component
    path, because the legacy path is gated on whiteness twice and can never
    reach SAM for these cases. The box prompt runs on the FULL PAGE image —
    GT-scored comparisons showed crop-context prompts produce masks that
    miss the text bbox (cover 0.14-0.87) while full-page prompts pass gates
    on the same records. The per-page encoder cache keeps multi-balloon
    pages cheap.

    Returns a full V15-compatible result dict, or None when SAM is
    unavailable or the mask fails sanity gates (mirrors the GT bootstrap
    gates so scored behaviour matches production).
    """
    from app.services.sam_segmenter import smart_segment_box

    t0 = time.perf_counter()
    img_h, img_w = image.shape[:2]
    bx, by = float(text_bbox["x"]), float(text_bbox["y"])
    bw, bh = float(text_bbox["width"]), float(text_bbox["height"])

    x0 = max(0, int(bx))
    y0 = max(0, int(by))
    x1 = min(img_w, int(bx + bw))
    y1 = min(img_h, int(by + bh))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None

    raw = smart_segment_box(image, x0, y0, x1, y1)
    if raw is None or cv2.countNonZero((raw > 0).astype(np.uint8)) < (bw * bh * 1.15):
        cx, cy = bx + bw / 2.0, by + bh / 2.0
        expand_r = max(bw, bh) * 2.2
        sx0 = max(0, int(cx - expand_r))
        sy0 = max(0, int(cy - expand_r))
        sx1 = min(img_w, int(cx + expand_r))
        sy1 = min(img_h, int(cy + expand_r))
        raw_expanded = smart_segment_box(image, sx0, sy0, sx1, sy1)
        if raw_expanded is not None and cv2.countNonZero((raw_expanded > 0).astype(np.uint8)) >= (bw * bh * 1.15):
            raw = raw_expanded

    if raw is None:
        return None

    binary = (raw > 0).astype(np.uint8) * 255
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    if num_labels <= 1:
        return None
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    comp = (labels == best).astype(np.uint8) * 255
    cnts_h, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts_h:
        return None
    filled = np.zeros_like(comp)
    cv2.drawContours(filled, cnts_h, -1, 255, -1)

    roi = filled[y0:y1, x0:x1]
    cover = float(np.count_nonzero(roi)) / max(1, roi.size)
    if cover < 0.85:
        return None

    area_ratio = cv2.countNonZero(filled) / max(1.0, bw * bh)
    if area_ratio < 1.15 or area_ratio > 30.0:
        return None

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    interior = cv2.erode(filled, k)
    if cv2.countNonZero(interior) == 0:
        interior = filled

    cnts, _ = cv2.findContours(interior, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None
    main_cnt = max(cnts, key=cv2.contourArea)

    from app.services.smart_balloon import (
        apply_contour_inset,
        classify_balloon_archetype,
        _compute_row_width_constraints,
    )

    local_bbox = {"x": bx, "y": by, "width": bw, "height": bh}
    archetype, cls_meta = classify_balloon_archetype(
        main_cnt, local_bbox, crop_w=img_w, crop_h=img_h, raw_gray=cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    )

    safe_poly = apply_contour_inset(main_cnt, inset_ratio=inset_ratio)

    peri_raw = cv2.arcLength(main_cnt, True)
    poly_simple = cv2.approxPolyDP(main_cnt, 0.002 * peri_raw, True) if peri_raw > 0 else main_cnt
    peri_safe = cv2.arcLength(safe_poly, True)
    safe_poly_simple = cv2.approxPolyDP(safe_poly, 0.002 * peri_safe, True) if peri_safe > 0 else safe_poly

    abs_raw_cnt = poly_simple.reshape(-1, 2)
    abs_safe_cnt = safe_poly_simple.reshape(-1, 2)

    rx, ry, rw, rh = cv2.boundingRect(abs_raw_cnt)
    sx, sy, sw, sh = cv2.boundingRect(abs_safe_cnt)

    M = cv2.moments(safe_poly)
    if M["m00"] > 0:
        abs_cx = float(M["m10"] / M["m00"])
        abs_cy = float(M["m01"] / M["m00"])
    else:
        abs_cx = float(sx + sw / 2.0)
        abs_cy = float(sy + sh / 2.0)

    pad_x = max(60, int(bw * 0.15))
    pad_y = max(60, int(bh * 0.15))
    wx0 = max(0, int(rx - pad_x))
    wy0 = max(0, int(ry - pad_y))
    wx1 = min(img_w, int(rx + rw + pad_x))
    wy1 = min(img_h, int(ry + rh + pad_y))
    crop_mask = np.zeros((wy1 - wy0, wx1 - wx0), dtype=np.uint8)
    cv2.fillPoly(crop_mask, [(main_cnt - np.array([wx0, wy0])).astype(np.int32)], 255)

    elapsed = time.perf_counter() - t0
    meta = dict(cls_meta)
    meta.update({
        "elapsed_sec": round(elapsed, 4),
        "inset_ratio": inset_ratio,
        "confidence": round(min(0.99, max(0.80, float(cv2.contourArea(main_cnt) / max(1.0, float(bw * bh))))), 2),
        "bbox_cover": round(cover, 3),
        "source": "sam_box_fallback",
    })

    return {
        "success": True,
        "method": "sam_box_fallback",
        "archetype": archetype,
        "smart_x": float(sx),
        "smart_y": float(sy),
        "smart_width": float(sw),
        "smart_height": float(sh),
        "raw_bbox": {"x": float(rx), "y": float(ry), "width": float(rw), "height": float(rh)},
        "safe_bbox": {"x": float(sx), "y": float(sy), "width": float(sw), "height": float(sh)},
        "center": {"x": abs_cx, "y": abs_cy},
        "crop_mask": crop_mask,
        "crop_offset": (int(wx0), int(wy0)),
        "mask_area": int(cv2.countNonZero(crop_mask)),
        "contour_points": abs_safe_cnt.tolist(),
        "raw_contour_points": abs_raw_cnt.tolist(),
        "row_width_constraints": _compute_row_width_constraints(safe_poly, sx, sy, sw, sh),
        "metadata": meta,
    }


def _iou(a, b):
    ax1, ay1 = float(a["x"]), float(a["y"])
    ax2, ay2 = ax1 + float(a["width"]), ay1 + float(a["height"])
    bx1, by1 = float(b["x"]), float(b["y"])
    bx2, by2 = bx1 + float(b["width"]), by1 + float(b["height"])
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    intersection = iw * ih
    if intersection <= 0.0:
        return 0.0
    area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
    return intersection / max(1.0, area_a + area_b - intersection)


def class_aware_nms(boxes, threshold):
    """Keep the strongest box per class while merging partial balloon boxes across sliding window tiles."""
    boxes = sorted((dict(box) for box in boxes), key=lambda d: d["confidence"], reverse=True)
    kept = []
    for det in boxes:
        det_class = det.get("detection_class", det.get("balloon_type", "unknown"))
        suppressed = False
        for existing in kept:
            existing_class = existing.get(
                "detection_class", existing.get("balloon_type", "unknown")
            )
            if existing_class != det_class:
                continue
            det_bbox = [
                det["x"],
                det["y"],
                det["x"] + det["width"],
                det["y"] + det["height"],
            ]
            existing_bbox = [
                existing["x"],
                existing["y"],
                existing["x"] + existing["width"],
                existing["y"] + existing["height"],
            ]
            # IoU handles ordinary duplicate anchors. Smaller-area coverage
            # removes a nested single-line prediction without union-growing the
            # retained multi-line text box.
            iou_val = _iou(det, existing)
            ov_val = overlap_percent(det_bbox, existing_bbox)
            if iou_val > threshold or ov_val > 0.30:
                # For balloon/bubble classes: if one box is truncated by a sliding-window tile boundary
                # or if the other box spans further vertically while sharing the same column,
                # merge vertical extent so large speech balloons are never truncated across tiles.
                if det_class in ("balloon", "bubble"):
                    x_inter = max(0.0, min(det_bbox[2], existing_bbox[2]) - max(det_bbox[0], existing_bbox[0]))
                    x_min_w = min(det["width"], existing["width"])
                    det_c = det.get("confidence", 0)
                    ext_c = existing.get("confidence", 0)
                    if x_min_w > 0 and (x_inter / x_min_w) > 0.75 and det_c >= 0.25 and ext_c >= 0.25:
                        nx1 = min(det_bbox[0], existing_bbox[0])
                        ny1 = min(det_bbox[1], existing_bbox[1])
                        nx2 = max(det_bbox[2], existing_bbox[2])
                        ny2 = max(det_bbox[3], existing_bbox[3])
                        existing["x"] = nx1
                        existing["y"] = ny1
                        existing["width"] = nx2 - nx1
                        existing["height"] = ny2 - ny1
                        existing["confidence"] = max(ext_c, det_c)
                suppressed = True
                break
        if not suppressed:
            kept.append(det)
    return kept


def merge_overlapping_30percent(boxes, threshold=0.10, dist_thresh=30.0):
    """
    If any 2 detected balloon/text boxes overlap by > 10% of the smaller box's area
    or share horizontal/vertical alignment within the same balloon bubble,
    automatically merge them into 1 unified balloon box.
    """
    if len(boxes) < 2:
        return boxes
    
    merged = []
    used = [False] * len(boxes)
    for i in range(len(boxes)):
        if used[i]:
            continue
        curr = dict(boxes[i])
        changed = True
        while changed:
            changed = False
            curr_bbox = [curr["x"], curr["y"], curr["x"] + curr["width"], curr["y"] + curr["height"]]
            for j in range(len(boxes)):
                if j == i or used[j]:
                    continue
                b2 = boxes[j]
                b2_bbox = [b2["x"], b2["y"], b2["x"] + b2["width"], b2["y"] + b2["height"]]
                
                x_inter = max(0.0, min(curr_bbox[2], b2_bbox[2]) - max(curr_bbox[0], b2_bbox[0]))
                y_inter = max(0.0, min(curr_bbox[3], b2_bbox[3]) - max(curr_bbox[1], b2_bbox[1]))
                w1 = max(1.0, curr_bbox[2] - curr_bbox[0])
                w2 = max(1.0, b2_bbox[2] - b2_bbox[0])
                h1 = max(1.0, curr_bbox[3] - curr_bbox[1])
                h2 = max(1.0, b2_bbox[3] - b2_bbox[1])

                x_ov = x_inter / min(w1, w2)
                y_ov = y_inter / min(h1, h2)
                area_min = min(w1 * h1, w2 * h2)
                ov_ratio = (x_inter * y_inter) / max(1.0, area_min)
                iou_val = _iou(curr, b2)

                dx = max(0.0, max(curr_bbox[0] - b2_bbox[2], b2_bbox[0] - curr_bbox[2]))
                dy = max(0.0, max(curr_bbox[1] - b2_bbox[3], b2_bbox[1] - curr_bbox[3]))

                # Merge ONLY if actual bounding boxes overlap significantly (> 25% area)
                should_merge = (
                    ov_ratio >= max(0.25, threshold)
                    or iou_val >= max(0.25, threshold)
                )

                if should_merge:
                    nx1 = min(curr_bbox[0], b2_bbox[0])
                    ny1 = min(curr_bbox[1], b2_bbox[1])
                    nx2 = max(curr_bbox[2], b2_bbox[2])
                    ny2 = max(curr_bbox[3], b2_bbox[3])
                    curr["x"] = nx1
                    curr["y"] = ny1
                    curr["width"] = nx2 - nx1
                    curr["height"] = ny2 - ny1
                    curr_bbox = [nx1, ny1, nx2, ny2]
                    if b2.get("confidence", 0) > curr.get("confidence", 0):
                        curr["confidence"] = b2["confidence"]
                        curr["balloon_type"] = b2.get("balloon_type", curr.get("balloon_type", "text"))
                    used[j] = True
                    changed = True
        merged.append(curr)
        used[i] = True
    return merged


def nms_merge(boxes, threshold):
    """Backward-compatible name for callers/tests; no longer union-grows boxes."""
    return class_aware_nms(boxes, threshold)


def merge_proximity(boxes, dist_thresh):
    if len(boxes) < 2:
        return boxes
    boxes = sorted(boxes, key=lambda d: (d["y"], d["x"]))
    final_merged = []
    used = [False] * len(boxes)
    for i in range(len(boxes)):
        if used[i]:
            continue
        curr = dict(boxes[i])
        changed = True
        while changed:
            changed = False
            curr_bbox = [curr["x"], curr["y"], curr["x"] + curr["width"], curr["y"] + curr["height"]]
            for j in range(len(boxes)):
                if j == i or used[j]:
                    continue
                b2 = boxes[j]
                b2_bbox = [b2["x"], b2["y"], b2["x"] + b2["width"], b2["y"] + b2["height"]]
                
                dx = max(0.0, max(curr_bbox[0] - b2_bbox[2], b2_bbox[0] - curr_bbox[2]))
                dy = max(0.0, max(curr_bbox[1] - b2_bbox[3], b2_bbox[1] - curr_bbox[3]))
                
                if dx <= dist_thresh and dy <= dist_thresh:
                    nx1 = min(curr_bbox[0], b2_bbox[0])
                    ny1 = min(curr_bbox[1], b2_bbox[1])
                    nx2 = max(curr_bbox[2], b2_bbox[2])
                    ny2 = max(curr_bbox[3], b2_bbox[3])
                    curr["x"] = nx1
                    curr["y"] = ny1
                    curr["width"] = nx2 - nx1
                    curr["height"] = ny2 - ny1
                    curr_bbox = [nx1, ny1, nx2, ny2]
                    if b2["confidence"] > curr["confidence"]:
                        curr["confidence"] = b2["confidence"]
                        curr["balloon_type"] = b2["balloon_type"]
                    used[j] = True
                    changed = True
        final_merged.append(curr)
        used[i] = True
    return final_merged


def expand_bbox(box, ratio, pad, max_w, max_h):
    x = box["x"]
    y = box["y"]
    w = box["width"]
    h = box["height"]
    cx = x + w / 2.0
    cy = y + h / 2.0
    nw = w * ratio + pad
    nh = h * ratio + pad
    nx1 = max(0.0, min(cx - nw / 2.0, max_w))
    ny1 = max(0.0, min(cy - nh / 2.0, max_h))
    nx2 = max(0.0, min(cx + nw / 2.0, max_w))
    ny2 = max(0.0, min(cy + nh / 2.0, max_h))
    return {
        "x": float(nx1),
        "y": float(ny1),
        "width": float(max(4.0, nx2 - nx1)),
        "height": float(max(4.0, ny2 - ny1)),
        "rotation_deg": box.get("rotation_deg", 0.0),
        "confidence": box["confidence"],
        "balloon_type": box["balloon_type"],
        "detection_class": box.get("detection_class", "text"),
    }


# Global detector instance
balloon_detector = BalloonDetector()
