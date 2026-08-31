"""High-quality, text-detection-guided masks for textured text regions.

The normal adaptive mask has to reason about an entire balloon/block.  That is
the right fast default, but it is deliberately not used here: a text detector
first supplies tight line polygons and the pixel refinement is constrained to
those polygons (plus a very small safety halo).
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import logging
import multiprocessing
import threading
from typing import Any, Iterable

import cv2
import numpy as np

from app.services.performance import resolve_performance_settings


logger = logging.getLogger("houmi-text-mask")


MASK_MODE_MONOCHROME_FLAT = "monochrome_flat"
MASK_MODE_COLOR_OR_COMPLEX = "color_or_complex"


@dataclass(frozen=True)
class TextDetection:
    """A text-line polygon in image-local coordinates."""

    polygon: np.ndarray
    confidence: float | None = None
    source: str = "paddle"
    char_count: int = 1

    def as_response(self) -> dict[str, Any]:
        x, y, width, height = cv2.boundingRect(self.polygon.astype(np.float32))
        return {
            "x": int(x),
            "y": int(y),
            "width": int(width),
            "height": int(height),
            "polygon": self.polygon.astype(float).round(2).tolist(),
            "confidence": self.confidence,
            "source": self.source,
        }


_paddle_ocr: Any | None = None
_paddle_lock = threading.Lock()
_worker_pool: ProcessPoolExecutor | None = None
_worker_pool_lock = threading.Lock()


def high_quality_text_mask_allowed(project_settings: dict | None) -> bool:
    """Keep this costly model path out of Eco/Balanced profiles.

    Custom is allowed only when the user explicitly opted into GPU work and
    gave OCR enough parallel-work budget.  The model itself still falls back
    to CPU if a CUDA provider is not actually available.
    """
    settings = project_settings or {}
    performance = resolve_performance_settings(settings)
    if performance.profile == "performance":
        return True
    return (
        performance.profile == "custom"
        and performance.prefer_gpu
        and performance.ocr_workers >= 3
    )


def _get_text_detector() -> Any:
    """Load the detector-only Paddle model used by HQ Text Mask.

    Recognition is intentionally omitted: this workflow needs polygons, not
    transcriptions. PP-OCRv6 small detected the difficult multi-colour comic
    sample while avoiding the medium recognition model's load and inference
    cost. The process boundary still protects the desktop UI from model init.
    """
    global _paddle_ocr
    with _paddle_lock:
        if _paddle_ocr is not None:
            return _paddle_ocr

        try:
            # Paddle GPU and the CPU-only torch package both ship runtime DLLs.
            # On Windows, importing Paddle first can make torch's shm.dll fail
            # when PaddleOCR lazily imports ModelScope. Loading torch first
            # establishes the compatible DLL order in the isolated worker.
            import torch  # noqa: F401
            import paddle
            from paddleocr import TextDetection
        except ImportError as exc:  # pragma: no cover - depends on local install
            raise RuntimeError(
                "High Quality Text Mask requires paddleocr and paddlepaddle. "
                "Install the backend requirements, then restart Houmi."
            ) from exc

        # PaddleOCR uses Paddle's CUDA runtime, not PyTorch's.  Checking torch
        # here previously forced a CPU device whenever the optional PyTorch
        # package was CPU-only, even on machines with a compatible RTX GPU.
        try:
            device = "gpu:0" if paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
        _paddle_ocr = TextDetection(
            model_name="PP-OCRv6_small_det",
            device=device,
            limit_side_len=1024,
            limit_type="max",
            thresh=0.18,
            box_thresh=0.32,
            unclip_ratio=1.6,
        )
        logger.info(
            "Loaded PP-OCRv6_small_det for high-quality text masks on %s (Paddle CUDA=%s)",
            device,
            paddle.is_compiled_with_cuda(),
        )
        return _paddle_ocr


def _prediction_mapping(prediction: Any) -> dict[str, Any]:
    """Normalize PaddleOCR v3 result objects without binding to one release."""
    if isinstance(prediction, dict):
        return prediction
    if hasattr(prediction, "keys"):
        try:
            return {key: prediction[key] for key in prediction.keys()}
        except Exception:
            pass
    if hasattr(prediction, "to_dict"):
        try:
            value = prediction.to_dict()
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    return {}


def _valid_polygon(value: Any, width: int, height: int) -> np.ndarray | None:
    try:
        polygon = np.asarray(value, dtype=np.float32).reshape(-1, 2)
    except (TypeError, ValueError):
        return None
    if len(polygon) < 3:
        return None
    polygon[:, 0] = np.clip(polygon[:, 0], 0, max(0, width - 1))
    polygon[:, 1] = np.clip(polygon[:, 1], 0, max(0, height - 1))
    if cv2.contourArea(polygon) < 6:
        return None
    return polygon


def _deduplicate_text_detections(detections: Iterable[TextDetection]) -> list[TextDetection]:
    """Keep complementary line boxes but discard near-identical duplicates."""
    deduplicated: list[TextDetection] = []
    for candidate in detections:
        cx, cy, cw, ch = cv2.boundingRect(candidate.polygon.astype(np.float32))
        candidate_area = max(1, cw * ch)
        duplicate = False
        for existing_index, existing in enumerate(deduplicated):
            ex, ey, ew, eh = cv2.boundingRect(existing.polygon.astype(np.float32))
            intersection = max(0, min(cx + cw, ex + ew) - max(cx, ex)) * max(0, min(cy + ch, ey + eh) - max(cy, ey))
            if intersection / min(candidate_area, max(1, ew * eh)) > 0.88:
                # Detector evidence is authoritative. A palette-derived box
                # must never replace a Paddle polygon merely because it is
                # smaller; decorative highlights often produce exactly that
                # shape on comic system panels.
                if existing.source == "paddle" and candidate.source != "paddle":
                    duplicate = True
                    break
                if candidate.source == "paddle" and existing.source != "paddle":
                    deduplicated[existing_index] = candidate
                    duplicate = True
                    break
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(candidate)
    return deduplicated


from app.services.mask import (
    MASK_MODE_COLOR_OR_COMPLEX,
    MASK_MODE_MONOCHROME_FLAT,
    classify_text_mask_mode,
    generate_monochrome_flat_text_mask,
    clamp_mask_to_balloon_interior,
)


def detect_text_lines(image_bgr: np.ndarray, predictor: Any | None = None) -> list[TextDetection]:
    """Return real Paddle text-line polygons, not OCR's synthetic full crop rows."""
    if image_bgr is None or image_bgr.size == 0:
        return []
    engine = predictor or _get_text_detector()
    height, width = image_bgr.shape[:2]
    predictions = engine.predict(image_bgr)
    detections: list[TextDetection] = []

    for prediction in predictions:
        result = _prediction_mapping(prediction)
        # TextDetection returns {"res": {"dt_polys": ..., "dt_scores": ...}},
        # while the full PaddleOCR pipeline returns those fields at the top
        # level. Supporting both keeps this helper easy to test and resilient
        # to PaddleOCR result-format changes.
        nested = result.get("res") if isinstance(result.get("res"), dict) else result
        polygons = nested.get("rec_polys")
        if polygons is None:
            polygons = nested.get("dt_polys")
        if polygons is None:
            polygons = []
        scores = nested.get("rec_scores")
        if scores is None:
            scores = nested.get("dt_scores")
        if scores is None:
            scores = []
        for index, value in enumerate(polygons):
            polygon = _valid_polygon(value, width, height)
            if polygon is None:
                continue
            score: float | None = None
            if index < len(scores):
                try:
                    score = float(scores[index])
                except (TypeError, ValueError):
                    pass
            detections.append(TextDetection(polygon=polygon, confidence=score, source="paddle"))
    return _deduplicate_text_detections(detections)


def _merge_nearby_line_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Join character clusters that lie on the same visual text line."""
    pending = sorted(boxes, key=lambda box: (box[1], box[0]))
    merged: list[tuple[int, int, int, int]] = []
    while pending:
        x, y, width, height = pending.pop(0)
        x1, y1 = x + width, y + height
        changed = True
        while changed:
            changed = False
            for index, (other_x, other_y, other_w, other_h) in enumerate(pending):
                other_x1, other_y1 = other_x + other_w, other_y + other_h
                vertical_overlap = max(0, min(y1, other_y1) - max(y, other_y))
                min_height = max(1, min(y1 - y, other_y1 - other_y))
                horizontal_gap = max(other_x - x1, x - other_x1, 0)
                if vertical_overlap / min_height >= 0.35 and horizontal_gap <= max(24, int(min_height * 1.8)):
                    x, y = min(x, other_x), min(y, other_y)
                    x1, y1 = max(x1, other_x1), max(y1, other_y1)
                    pending.pop(index)
                    changed = True
                    break
        if x1 - x >= 14 and y1 - y >= 8:
            merged.append((x, y, x1 - x, y1 - y))
    return merged


def detect_colored_text_lines(image_bgr: np.ndarray) -> tuple[np.ndarray, list[TextDetection]]:
    """Find saturated/light text missed by document-oriented OCR detection.

    Comic system text is often orange, purple, cyan, or white over a textured
    panel.  DB/Paddle detection can recognise the line's content but still
    refuse to emit a polygon.  This pass clusters Lab colours, removes the
    dominant panel palette, then groups surviving glyph components into lines.
    It is deliberately a *candidate* generator; Paddle remains the primary
    detector for normal black/white dialogue.
    """
    height, width = image_bgr.shape[:2]
    if height < 12 or width < 12:
        return np.zeros((height, width), dtype=np.uint8), []

    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    pixels = lab.reshape((-1, 3)).astype(np.float32)
    cluster_count = min(8, max(3, pixels.shape[0] // 160))
    cv2.setRNGSeed(9817)
    _, labels, centers = cv2.kmeans(
        pixels,
        cluster_count,
        None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 32, 0.45),
        2,
        cv2.KMEANS_PP_CENTERS,
    )
    label_image = labels.reshape((height, width))
    counts = np.bincount(labels.ravel(), minlength=cluster_count)
    background_label = int(np.argmax(counts))
    distances = np.linalg.norm(centers - centers[background_label], axis=1)
    max_cluster_ratio = 0.10
    selected_labels = [
        index
        for index in range(cluster_count)
        if index != background_label
        and counts[index] < pixels.shape[0] * max_cluster_ratio
        and (distances[index] >= 40 or centers[index][0] >= 200 or centers[index][0] <= 80)
    ]
    if not selected_labels:
        return np.zeros((height, width), dtype=np.uint8), []

    seed = np.where(np.isin(label_image, selected_labels), 255, 0).astype(np.uint8)
    seed = cv2.medianBlur(seed, 3)

    # Eliminate large panel borders / highlights that touch a crop edge. Text
    # near an edge is retained unless it is itself a broad edge-connected mass.
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(seed, connectivity=8)
    cleaned = np.zeros_like(seed)
    min_component_area = max(4, int(height * width * 0.00005))
    for label in range(1, component_count):
        x, y, component_w, component_h, area = stats[label]
        touches_edge = x == 0 or y == 0 or x + component_w >= width or y + component_h >= height
        broad_edge_mass = touches_edge and (
            area > height * width * 0.0025
            or component_w > width * 0.45
            or component_h > height * 0.45
        )
        if area >= min_component_area and not broad_edge_mass:
            cleaned[labels == label] = 255

    # Bridge pieces of individual glyphs, then merge horizontal neighbours into
    # one detection box per line. The actual saved mask uses `cleaned`, not the
    # broadened bridge, so no panel details are added to the inpaint mask.
    bridge = cv2.morphologyEx(
        cleaned,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (11, 5)),
    )

    boxes: list[tuple[int, int, int, int]] = []
    bridge_count, bridge_labels, bridge_stats, _ = cv2.connectedComponentsWithStats(
        bridge, connectivity=8
    )
    for label in range(1, bridge_count):
        x, y, component_w, component_h, area = bridge_stats[label]
        if area >= min_component_area and component_w >= 4 and component_h >= 4:
            boxes.append((x, y, component_w, component_h))

    detections: list[TextDetection] = []
    for x, y, component_w, component_h in _merge_nearby_line_boxes(boxes):
        polygon = np.array(
            [
                [x, y],
                [x + component_w, y],
                [x + component_w, y + component_h],
                [x, y + component_h],
            ],
            dtype=np.int32,
        )
        detections.append(
            TextDetection(
                polygon=polygon,
                confidence=0.85,
                source="color",
                char_count=max(1, component_w // 12),
            )
        )
    return cleaned, _deduplicate_text_detections(detections)


def _expanded_polygon_mask(
    shape: tuple[int, int], polygon: np.ndarray, padding: int
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Create a tight binary mask covering the proposed line polygon."""
    height, width = shape[:2]
    x, y, w, h = cv2.boundingRect(polygon)
    x0 = max(0, x - padding)
    y0 = max(0, y - padding)
    x1 = min(width, x + w + padding)
    y1 = min(height, y + h + padding)

    local_poly = polygon.copy()
    local_poly[:, 0] -= x0
    local_poly[:, 1] -= y0
    local_poly = np.round(local_poly).astype(np.int32)

    mask = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    cv2.fillPoly(mask, [local_poly], 255)
    if padding > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (padding * 2 + 1, padding * 2 + 1)
        )
        mask = cv2.dilate(mask, kernel, iterations=1)
    return mask, (x0, y0, x1, y1)


def _refine_line_mask(gray: np.ndarray, allowed: np.ndarray, dilation_kernel: int,
                      color_crop: np.ndarray | None = None) -> tuple[np.ndarray, float]:
    """Select the contrasting text pixels *inside* one detected line polygon.

    When *color_crop* (BGR) is provided the function also considers LAB colour
    distance from the surrounding background.  This catches coloured manga text
    (red, orange, white-on-dark) that a single Otsu threshold on the grayscale
    channel would miss entirely.
    """
    values = gray[allowed > 0]
    if values.size < 8:
        return np.zeros_like(gray), 0.0

    # cv2.threshold returns the scalar threshold as its first result. Calling
    # it on a one-column array works consistently across OpenCV builds.
    otsu_threshold = int(cv2.threshold(values.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[0])

    ring_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    ring = cv2.subtract(cv2.dilate(allowed, ring_kernel), allowed)
    ring_values = gray[ring > 0]
    reference = float(np.median(ring_values)) if ring_values.size else float(np.median(values))

    bright_cutoff = max(otsu_threshold, int(np.percentile(values, 76)))
    dark_cutoff = min(otsu_threshold, int(np.percentile(values, 24)))
    bright_strength = float(np.percentile(values, 92)) - reference
    dark_strength = reference - float(np.percentile(values, 8))

    # Check for dual-contrast outlined text (e.g. black text core with thick white outline on skin/color artwork)
    has_bright_stroke = bool(np.count_nonzero((values >= reference + 20) & (values > 200)) >= max(4, int(values.size * 0.025)))
    has_dark_core = bool(np.count_nonzero((values <= reference - 25) & (values < 90)) >= max(4, int(values.size * 0.025)))
    is_dual_contrast_outlined = has_bright_stroke and has_dark_core and (35.0 <= reference <= 220.0)

    if is_dual_contrast_outlined:
        b_cut = max(205, int(reference + 18))
        d_cut = min(85, int(reference - 22))
        candidate = ((gray >= b_cut) | (gray <= d_cut)) & (allowed > 0)
        candidate = np.where(candidate, 255, 0).astype(np.uint8)
    else:
        select_bright = bright_strength >= dark_strength
        candidate = (gray >= bright_cutoff) if select_bright else (gray <= dark_cutoff)
        candidate = np.where((candidate & (allowed > 0)), 255, 0).astype(np.uint8)

    # --- Adaptive threshold rescue ------------------------------------------
    # Otsu alone uses a single global threshold; adaptive thresholding picks up
    # strokes that cross a brightness gradient (common with coloured text on
    # textured manga panels).  Only used as a rescue when Otsu captured very
    # little, to avoid inflating coverage on noisy textured backgrounds.
    otsu_capture = float(np.count_nonzero(candidate)) / max(1, int(np.count_nonzero(allowed)))
    if not is_dual_contrast_outlined and otsu_capture < 0.05 and gray.shape[0] >= 12 and gray.shape[1] >= 12:
        block = max(11, (min(gray.shape[:2]) // 4) | 1)  # ensure odd
        adaptive_mode = cv2.THRESH_BINARY if select_bright else cv2.THRESH_BINARY_INV
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                         adaptive_mode, block, 4)
        adaptive = np.where((adaptive > 0) & (allowed > 0), 255, 0).astype(np.uint8)
        candidate = cv2.bitwise_or(candidate, adaptive)

    # --- LAB colour distance (multi-color / contrast union) -------------------
    # For coloured text (red/orange/cyan on dark or light backgrounds), grayscale-only
    # thresholding may miss colored words in mixed-color sentences. Measure colour distance
    # in LAB space between each pixel and the surrounding ring to find coloured glyphs.
    if color_crop is not None and color_crop.shape[:2] == gray.shape[:2]:
        lab = cv2.cvtColor(color_crop, cv2.COLOR_BGR2LAB).astype(np.float32)
        ring_lab = lab[ring > 0]
        if ring_lab.size >= 9:
            bg_lab = np.median(ring_lab, axis=0)
            dist = np.sqrt(np.sum((lab - bg_lab) ** 2, axis=2))
            dist_vals = dist[allowed > 0]
            if dist_vals.size > 0:
                colour_thresh = max(28.0, float(np.percentile(dist_vals, 75)))
                colour_mask = np.where((dist >= colour_thresh) & (allowed > 0), 255, 0).astype(np.uint8)
                candidate = cv2.bitwise_or(candidate, colour_mask)

    # Retain small glyph pieces and punctuation dots, but reject isolated noise and needle rays.
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    cleaned = np.zeros_like(candidate)
    min_component_area = max(2, int(values.size * 0.0004))
    max_component_area = int(values.size * 0.95)  # allow large text strokes in dark boxes
    for label in range(1, component_count):
        x, y, component_w, component_h, area = stats[label]
        is_radial_ray = min(component_w, component_h) <= 2 and max(component_w, component_h) >= 28
        if min_component_area <= area <= max_component_area and not is_radial_ray:
            cleaned[labels == label] = 255

    if dilation_kernel > 0 and np.any(cleaned):
        size = dilation_kernel * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        cleaned = cv2.dilate(cleaned, kernel, iterations=1)
        cleaned = cv2.bitwise_and(cleaned, allowed)

    coverage = float(np.count_nonzero(cleaned)) / max(1, int(np.count_nonzero(allowed)))
    return cleaned, coverage


def refine_detected_text_mask(
    image_bgr: np.ndarray,
    detections: Iterable[TextDetection],
    dilation_kernel: int = 3,
    color_seed: np.ndarray | None = None,
) -> tuple[np.ndarray, list[dict[str, Any]], list[str]]:
    """Create a binary mask by refining each detected line independently."""
    height, width = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    result = np.zeros((height, width), dtype=np.uint8)
    regions: list[dict[str, Any]] = []
    warnings: list[str] = []
    padding = max(2, min(45, int(dilation_kernel) + 6))

    for detection in detections:
        allowed, (x0, y0, x1, y1) = _expanded_polygon_mask((height, width), detection.polygon, padding)
        line_mask, coverage = _refine_line_mask(
            gray[y0:y1, x0:x1], allowed, max(0, int(dilation_kernel)),
            color_crop=image_bgr[y0:y1, x0:x1],
        )
        quality_coverage = coverage
        if detection.source == "color" and color_seed is not None:
            seed_crop = cv2.bitwise_and(color_seed[y0:y1, x0:x1], allowed)
            # Judge the Color Ink candidate before applying the user's mask
            # expansion. Dense/outlined comic glyphs legitimately occupy most
            # of a line box and a 5px kernel can push their expanded mask over
            # the generic 60% safety limit even though the seed is accurate.
            quality_coverage = float(np.count_nonzero(seed_crop)) / max(1, int(np.count_nonzero(allowed)))
            if dilation_kernel > 0 and np.any(seed_crop):
                size = dilation_kernel * 2 + 1
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
                seed_crop = cv2.bitwise_and(cv2.dilate(seed_crop, kernel, iterations=1), allowed)
            line_mask = cv2.bitwise_or(line_mask, seed_crop)
            coverage = float(np.count_nonzero(line_mask)) / max(1, int(np.count_nonzero(allowed)))
        coverage_limit = 0.94 if detection.source in {"color", "dark_box"} else 0.90
        if quality_coverage > coverage_limit:
            warnings.append("A detected line mask was clamped to avoid over-coverage.")
            line_mask = cv2.bitwise_and(line_mask, allowed)
        result[y0:y1, x0:x1] = cv2.bitwise_or(result[y0:y1, x0:x1], line_mask)
        region = detection.as_response()
        region["mask_coverage"] = round(coverage, 4)
        regions.append(region)

    overall_coverage = float(np.count_nonzero(result)) / max(1, height * width)
    if overall_coverage > 0.45:
        warnings.append("The generated mask is unusually large; inspect it before cleaning.")
    return result, regions, warnings


_manga_unet_model: Any | None = None
_manga_unet_lock = threading.Lock()


def get_manga_unet_model() -> tuple[Any, str] | None:
    """Load Manga-Text-Segmentation-2025 UNet++ model lazily (ONNX or PyTorch)."""
    global _manga_unet_model
    with _manga_unet_lock:
        if _manga_unet_model is not None:
            return _manga_unet_model

        try:
            from app.config import MODELS_DIR, MANGA_TEXT_SEG_MODEL_PATH
            onnx_path = MODELS_DIR / "manga_text_segmentation" / "manga_unet.onnx"

            # 1. Prefer ONNX Runtime (Universal GPU/DirectML/CPU acceleration for NVIDIA, AMD, Intel)
            if onnx_path.exists():
                try:
                    import onnxruntime as ort
                    available = ort.get_available_providers()
                    providers = []
                    if "CUDAExecutionProvider" in available:
                        providers.append("CUDAExecutionProvider")
                    if "DmlExecutionProvider" in available:
                        providers.append("DmlExecutionProvider")
                    providers.append("CPUExecutionProvider")

                    session = ort.InferenceSession(str(onnx_path), providers=providers)
                    active_provider = session.get_providers()[0]
                    _manga_unet_model = (session, f"onnx_{active_provider}")
                    logger.info("🚀 [GPU MASK SEGMENTATION ACTIVE] Hardware: %s | Model: Manga UNet++ ONNX", active_provider)
                    return _manga_unet_model
                except Exception as exc:
                    logger.warning("Failed to load Manga UNet++ ONNX model, trying PyTorch fallback: %s", exc)

            # 2. Fallback to PyTorch .pth model if ONNX is missing or failed
            if not MANGA_TEXT_SEG_MODEL_PATH.exists():
                return None

            import torch
            import torch.nn as nn
            import segmentation_models_pytorch as smp

            device = "cuda" if torch.cuda.is_available() else "cpu"
            encoder = "tu-efficientnetv2_rw_m"

            def convert_batchnorm_to_groupnorm(module):
                for name, child in module.named_children():
                    if isinstance(child, nn.BatchNorm2d):
                        num_channels = child.num_features
                        num_groups = 8
                        if num_channels < num_groups or num_channels % num_groups != 0:
                            for i in range(min(num_channels, 8), 1, -1):
                                if num_channels % i == 0:
                                    num_groups = i
                                    break
                            else:
                                num_groups = 1
                        setattr(module, name, nn.GroupNorm(num_groups=num_groups, num_channels=num_channels))
                    else:
                        convert_batchnorm_to_groupnorm(child)

            net = smp.UnetPlusPlus(
                encoder_name=encoder,
                encoder_weights=None,
                in_channels=3,
                classes=1,
                activation=None,
                decoder_attention_type="scse",
            )
            convert_batchnorm_to_groupnorm(net.decoder)
            state_dict = torch.load(str(MANGA_TEXT_SEG_MODEL_PATH), map_location=device)
            net.load_state_dict(state_dict)
            net.to(device)
            net.eval()
            _manga_unet_model = (net, device)
            logger.info("Loaded Manga-Text-Segmentation-2025 UNet++ PyTorch model on %s", device)
            return _manga_unet_model
        except Exception as exc:
            logger.warning("Failed to load Manga-Text-Segmentation-2025 UNet++ model: %s", exc)
            return None


def generate_manga_unet_text_mask(image_bgr: np.ndarray, dilation_kernel: int = 1, threshold: float = 0.40) -> np.ndarray | None:
    """High-precision UNet++ text mask for colored/textured Manga & Webtoon balloons."""
    if image_bgr is None or image_bgr.size == 0:
        return None
    try:
        loaded = get_manga_unet_model()
        if loaded is None:
            return None
        model_obj, device = loaded

        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        h, w = image_rgb.shape[:2]
        pad_h = (32 - h % 32) % 32
        pad_w = (32 - w % 32) % 32

        if device.startswith("onnx_"):
            session = model_obj
            padded_img = cv2.copyMakeBorder(image_rgb, 0, pad_h, 0, pad_w, cv2.BORDER_CONSTANT, value=[0, 0, 0])
            normalized = (padded_img.astype(np.float32) / 255.0 - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
            input_tensor = np.transpose(normalized, (2, 0, 1))[np.newaxis, :, :, :].astype(np.float32)

            try:
                with _manga_unet_lock:
                    outputs = session.run(["output"], {"input": input_tensor})
            except Exception as exc:
                if "suspended" in str(exc).lower() or "device_removed" in str(exc).lower() or "887a0005" in str(exc).lower() or "cuda failure" in str(exc).lower():
                    logger.warning("GPU device error in UNet! Invalidating ONNX session and switching to CPU fallback: %s", exc)
                    global _manga_unet_model
                    with _manga_unet_lock:
                        _manga_unet_model = None
                        import onnxruntime as ort
                        from app.config import MODELS_DIR
                        onnx_path = MODELS_DIR / "manga_text_segmentation" / "manga_unet.onnx"
                        cpu_session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
                        _manga_unet_model = (cpu_session, "onnx_CPUExecutionProvider")
                        outputs = cpu_session.run(["output"], {"input": input_tensor})
                else:
                    raise exc

            logits = outputs[0]
            probs = 1.0 / (1.0 + np.exp(-logits))
            prob_map = probs[0, 0, :h, :w]
        else:
            net = model_obj
            import torch
            import torch.nn.functional as F
            import albumentations as A
            from albumentations.pytorch import ToTensorV2

            transform = A.Compose([
                A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
                ToTensorV2(),
            ])

            augmented = transform(image=image_rgb)
            tensor = augmented["image"].unsqueeze(0).to(device)

            if pad_h > 0 or pad_w > 0:
                tensor = F.pad(tensor, (0, pad_w, 0, pad_h), mode="constant", value=0)

            with torch.no_grad():
                logits = net(tensor)
                probs = logits.sigmoid()

            prob_map = probs[0, 0, :h, :w].cpu().numpy()
        # Keep a moderate threshold: 0.30 made low-confidence balloon texture
        # merge with glyphs. Thin punctuation is recovered by the component
        # pass without making the whole interior a positive region.
        effective_thresh = float(threshold if threshold is not None and threshold != 0.40 else 0.18)
        binary_raw = (prob_map > effective_thresh).astype(np.uint8) * 255

        # Component-wise adaptive dilation based on stroke area
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_raw, connectivity=8)
        vision_mask = np.zeros_like(binary_raw)
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 3:
                continue
            comp = (labels == i).astype(np.uint8) * 255
            ksize = max(5, min(23, int(np.sqrt(area) * 0.36)))
            if ksize % 2 == 0:
                ksize += 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
            vision_mask = cv2.bitwise_or(vision_mask, cv2.dilate(comp, kernel))

        # High-pass gradient edge absorption (swallows outer 2-color stroke halos)
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr.copy()
        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad_norm = cv2.normalize(np.sqrt(grad_x**2 + grad_y**2), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        search_halo = cv2.dilate(vision_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        edges_inside = cv2.bitwise_and((grad_norm > 32).astype(np.uint8) * 255, search_halo)

        final_mask = cv2.bitwise_or(vision_mask, edges_inside)
        final_mask = cv2.morphologyEx(final_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

        # Protect large dark outer frame/balloon borders
        dark_borders = (gray < 40).astype(np.uint8) * 255
        b_labels, b_out, b_stats, _ = cv2.connectedComponentsWithStats(dark_borders)
        for b in range(1, b_labels):
            if b_stats[b, cv2.CC_STAT_AREA] > (h * w * 0.05) or b_stats[b, cv2.CC_STAT_WIDTH] > (w * 0.7) or b_stats[b, cv2.CC_STAT_HEIGHT] > (h * 0.7):
                outline = (b_out == b).astype(np.uint8) * 255
                final_mask = cv2.bitwise_and(final_mask, cv2.bitwise_not(cv2.dilate(outline, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))))

        final_mask = clamp_mask_to_balloon_interior(final_mask, image_bgr, margin_px=2)
        return final_mask
    except Exception as exc:
        logger.warning("Manga UNet++ text mask execution failed: %s", exc)
        return None


def generate_routed_text_mask(
    image_bgr: np.ndarray,
    dilation_kernel: int = 1,
) -> tuple[np.ndarray | None, str, dict[str, float]]:
    """Generate a mask with the engine selected from measurable crop traits.
    
    1. Speech Balloons (Monochrome Flat): ImageTrans-style mathematical contrast with balloon interior clamping.
    2. UI Glass Status Panels: Glow-encompassing contour mask without solid box.
    3. Complex Art / SFX: Pure AI Vision (Manga UNet++) with multi-tone stroke absorption.
    """
    if image_bgr is None or image_bgr.size == 0:
        return None, MASK_MODE_COLOR_OR_COMPLEX, {}

    height, width = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr.copy()
    mode, diagnostics = classify_text_mask_mode(image_bgr)

    # Route 1: UI Glass Status Boxes (dark cyan/blue panel with glowing text and side neon lines)
    if width >= 200 and height >= 40:
        left_strip = gray[:, :10]
        right_strip = gray[:, width - 10:]
        has_neon_border = (np.max(left_strip) > 220) and (np.max(right_strip) > 220)
        has_glowing_text = np.count_nonzero(gray > 200) > (height * width * 0.03) and np.median(gray) < 120
        if has_neon_border and has_glowing_text:
            bright_text = (gray > 160).astype(np.uint8) * 255
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bright_text)
            contour_mask = np.zeros_like(gray)
            for i in range(1, num_labels):
                lx, ly, lw, lh, area = stats[i]
                if area < 3:
                    continue
                if (lx <= 8 or (lx + lw) >= width - 8) and lh > (height * 0.40):
                    continue
                comp = (labels == i).astype(np.uint8) * 255
                k_glow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
                comp_dilated = cv2.dilate(comp, k_glow)
                contour_mask = cv2.bitwise_or(contour_mask, comp_dilated)

            k_bridge = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3))
            contour_mask = cv2.morphologyEx(contour_mask, cv2.MORPH_CLOSE, k_bridge)
            contour_mask[:, :8] = 0
            contour_mask[:, width - 8:] = 0
            return contour_mask, "ui_glass_box", diagnostics

    # Route 2: Speech Balloons (Monochrome Flat)
    if mode == MASK_MODE_MONOCHROME_FLAT:
        mask = generate_monochrome_flat_text_mask(image_bgr, dilation_kernel=max(1, dilation_kernel))
        if mask is not None and np.count_nonzero(mask) >= 12:
            mask = clamp_mask_to_balloon_interior(mask, image_bgr, margin_px=2)
            return mask, MASK_MODE_MONOCHROME_FLAT, diagnostics

    # Route 3: Color Hard / SFX on Complex Art (Pure AI Vision UNet++)
    unet_mask = generate_manga_unet_text_mask(image_bgr, dilation_kernel)
    if unet_mask is not None and np.count_nonzero(unet_mask) >= 12:
        unet_mask = clamp_mask_to_balloon_interior(unet_mask, image_bgr, margin_px=2)
        return unet_mask, MASK_MODE_COLOR_OR_COMPLEX, diagnostics

    # Fallback to adaptive SFX / multi-tone extraction
    sfx_fallback = generate_adaptive_sfx_mask(image_bgr, dilation_kernel=max(1, dilation_kernel))
    if sfx_fallback is not None and np.count_nonzero(sfx_fallback) >= 12:
        sfx_fallback = clamp_mask_to_balloon_interior(sfx_fallback, image_bgr, margin_px=2)
        return sfx_fallback, MASK_MODE_COLOR_OR_COMPLEX, diagnostics

    return unet_mask, mode, diagnostics


def generate_adaptive_sfx_mask(image_bgr: np.ndarray, dilation_kernel: int = 3) -> np.ndarray:
    """Adaptive rescue mask generator for Webtoon Sound Effects (SFX) & Calligraphy text."""
    if image_bgr is None or image_bgr.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)

    # Primary: Use Hugging Face Manga-Text-Segmentation-2025 UNet++ Model
    unet_mask = generate_manga_unet_text_mask(image_bgr, dilation_kernel=max(1, dilation_kernel))
    if unet_mask is not None and np.any(unet_mask):
        return unet_mask

    h, w = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    bg_is_light = bool(np.median(border) > 127)

    otsu_flag = cv2.THRESH_BINARY_INV if bg_is_light else cv2.THRESH_BINARY
    _, mask_otsu = cv2.threshold(blurred, 0, 255, otsu_flag + cv2.THRESH_OTSU)

    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    border_lab = np.concatenate([lab[0, :, :], lab[-1, :, :], lab[:, 0, :], lab[:, -1, :]])
    bg_lab = np.median(border_lab, axis=0)
    color_dist = np.sqrt(np.sum((lab - bg_lab) ** 2, axis=2))
    mask_color = np.where(color_dist > 22.0, 255, 0).astype(np.uint8)

    # For light/skin backgrounds, also check for white-fill text with dark outline (e.g. whisper/thought text)
    _, mask_white = cv2.threshold(gray, 215, 255, cv2.THRESH_BINARY)
    has_white_text = (np.count_nonzero(mask_white) >= 16 and np.count_nonzero(mask_white) < (h * w * 0.70))

    if not bg_is_light:
        combined = cv2.bitwise_or(mask_otsu, cv2.bitwise_or(mask_color, mask_white))
    elif has_white_text:
        # Fuse dark outline (mask_otsu) + white glyph interior (mask_white)
        combined = cv2.bitwise_or(mask_otsu, mask_white)
    else:
        combined = mask_otsu

    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, k_close)

    # Zero out outer 2px boundary to prevent edge bleeding
    combined[0:2, :] = 0
    combined[-2:, :] = 0
    combined[:, 0:2] = 0
    combined[:, -2:] = 0

    num_l, labels_l, stats_l, centroids_l = cv2.connectedComponentsWithStats(combined, connectivity=8)
    sfx_mask = np.zeros((h, w), dtype=np.uint8)
    cx_box, cy_box = w / 2.0, h / 2.0
    diag_box = max(1.0, np.sqrt(w ** 2 + h ** 2))

    for l in range(1, num_l):
        lx = stats_l[l, cv2.CC_STAT_LEFT]
        ly = stats_l[l, cv2.CC_STAT_TOP]
        lw = stats_l[l, cv2.CC_STAT_WIDTH]
        lh = stats_l[l, cv2.CC_STAT_HEIGHT]
        area = stats_l[l, cv2.CC_STAT_AREA]
        
        if area < 8 or area > (h * w * 0.90):
            continue

        touches_border = (lx <= 2 or ly <= 2 or (lx + lw) >= w - 2 or (ly + lh) >= h - 2)
        dist_center = np.sqrt((centroids_l[l][0] - cx_box) ** 2 + (centroids_l[l][1] - cy_box) ** 2)
        rel_dist = dist_center / diag_box

        # Filter out perimeter radial dashed spikes and outer blush borders
        if touches_border and (rel_dist > 0.35 or lw > (w * 0.40) or lh > (h * 0.40)):
            continue
        if rel_dist > 0.46 and area < max(150, int(h * w * 0.02)):
            continue

        sfx_mask[labels_l == l] = 255

    if dilation_kernel > 0 and np.any(sfx_mask):
        k_size = max(1, min(56, int(dilation_kernel)) * 2 + 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        sfx_mask = cv2.dilate(sfx_mask, kernel, iterations=1)

    return clamp_mask_to_balloon_interior(sfx_mask, image_bgr, margin_px=2)


def generate_imagetrans_text_mask(image_bgr: np.ndarray, dilation_kernel: int = 3) -> np.ndarray:
    """
    ImageTrans & MangaToolPlus Hybrid Polygon Binarization Mask Engine.
    Uses local adaptive thresholding + Convex Hull polygon stroke isolation
    with safe distance-transform border protection to produce crisp, leak-free text masks.
    """
    if image_bgr is None or image_bgr.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)

    height, width = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr.copy()

    # Determine background polarity from center region
    cy0, cy1 = max(0, int(height * 0.20)), min(height, int(height * 0.80))
    cx0, cx1 = max(0, int(width * 0.20)), min(width, int(width * 0.80))
    center_region = gray[cy0:cy1, cx0:cx1] if (cy1 > cy0 and cx1 > cx0) else gray
    center_median = float(np.median(center_region))

    # Compute outer dark border perimeter map for safe distance transform protection
    dark_pixels = (gray < 80).astype(np.uint8) * 255
    dark_border_perimeter = dark_pixels.copy()
    dark_border_perimeter[cy0:cy1, cx0:cx1] = 0
    dist_from_border = cv2.distanceTransform(cv2.bitwise_not(dark_border_perimeter), cv2.DIST_L2, 5)

    # Adaptive contrast thresholding
    block_size = max(11, min(31, int(min(width, height) * 0.25) | 1))
    if block_size % 2 == 0:
        block_size += 1

    if center_median >= 120:  # Light background with dark text
        bin_mask = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block_size, 10
        )
        local_bg = cv2.boxFilter(gray, -1, (21, 21))
        bin_mask[gray > (local_bg - 8)] = 0
        bin_mask[dist_from_border <= 3] = 0
    else:  # Dark background with light text
        bin_mask = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, 10
        )
        local_bg = cv2.boxFilter(gray, -1, (21, 21))
        bin_mask[gray < (local_bg + 8)] = 0

    # Fill components and produce convex hulls
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bin_mask, connectivity=8)
    poly_mask = np.zeros_like(bin_mask)
    for l in range(1, num_labels):
        area = stats[l, cv2.CC_STAT_AREA]
        if area < 3 or area > (height * width * 0.85):
            continue
        pts = np.argwhere(labels == l)
        if len(pts) >= 3:
            pts_xy = np.column_stack([pts[:, 1], pts[:, 0]]).astype(np.int32)
            hull = cv2.convexHull(pts_xy)
            cv2.fillPoly(poly_mask, [hull], 255)
        else:
            poly_mask[labels == l] = 255

    # Dilation per user-defined kernel
    eff_kernel = max(1, int(dilation_kernel))
    if eff_kernel > 0:
        ksize = eff_kernel * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        poly_mask = cv2.dilate(poly_mask, kernel, iterations=1)

    # Apply Safe Distance Transform Border Clamping
    if center_median >= 120:
        poly_mask[dist_from_border <= 2] = 0

    return clamp_mask_to_balloon_interior(poly_mask, image_bgr, margin_px=2)


def generate_contour_morphology_text_mask(
    image_bgr: np.ndarray, dilation_kernel: int = 3
) -> np.ndarray:
    """
    Pure OpenCV Adaptive Morphology & Contour Text Mask Engine.
    Fast deterministic B&W edge/contour segmentation for comic balloons and SFX
    without requiring neural AI inference.
    """
    if image_bgr is None or image_bgr.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)

    height, width = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr.copy()

    # Border median to determine text/background polarity
    border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    bg_is_light = bool(np.median(border) > 127)

    # Adaptive threshold to isolate stroke edges
    block_size = max(11, min(31, int(min(width, height) * 0.25) | 1))
    if block_size % 2 == 0:
        block_size += 1

    adaptive_method = cv2.THRESH_BINARY_INV if bg_is_light else cv2.THRESH_BINARY
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, adaptive_method, block_size, 7
    )

    # Morphological opening to remove isolated noise specks
    k_open = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, k_open)

    # Find contours and filter components that are inside the text area
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    contour_mask = np.zeros_like(gray)
    min_area = max(4, int(width * height * 0.0005))
    max_area = int(width * height * 0.85)

    for i in range(1, num_labels):
        lx, ly, lw, lh, area = stats[i]
        if area < min_area or area > max_area:
            continue
        # Avoid balloon border edges touching the outer margin
        if (lx <= 1 or ly <= 1 or lx + lw >= width - 1 or ly + lh >= height - 1) and area > (width * height * 0.15):
            continue
        contour_mask[labels == i] = 255

    # Dilation per user-configured kernel
    eff_kernel = max(0, int(dilation_kernel))
    if eff_kernel > 0:
        ksize = eff_kernel * 2 + 1
        kelem = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        contour_mask = cv2.dilate(contour_mask, kelem, iterations=1)

    return clamp_mask_to_balloon_interior(contour_mask, image_bgr, margin_px=2)


def generate_high_quality_text_mask(
    image_bgr: np.ndarray,
    dilation_kernel: int = 3,
    predictor: Any | None = None,
) -> tuple[np.ndarray, list[dict[str, Any]], list[str]]:
    """Detect text lines, then refine a safe mask inside trusted proposals."""
    height, width = image_bgr.shape[:2]

    # 1. Route simple monochrome balloons to deterministic background sampling;
    # keep coloured/textured crops on Manga-Text-Segmentation-2025 UNet++.
    if predictor is None:
        routed_mask, mode, diagnostics = generate_routed_text_mask(
            image_bgr, dilation_kernel=max(1, dilation_kernel // 2)
        )
        if routed_mask is not None and np.any(routed_mask):
            unet_cov = float(np.count_nonzero(routed_mask)) / max(1, routed_mask.size)
            if 0 < unet_cov <= 0.92:
                unet_region = {
                    "polygon": [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                    "mask_coverage": round(unet_cov, 4),
                    "source": mode,
                    "diagnostics": diagnostics,
                }
                return routed_mask, [unet_region], [f"Generated {mode} text mask."]

    paddle_detections = []
    paddle_warnings: list[str] = []
    try:
        paddle_detections = detect_text_lines(image_bgr, predictor=predictor)
    except Exception as exc:
        paddle_warnings.append(f"Paddle text detection unavailable: {exc}")

    if paddle_detections:
        paddle_mask, paddle_regions, p_warn = refine_detected_text_mask(
            image_bgr,
            paddle_detections,
            dilation_kernel=dilation_kernel,
        )
        paddle_warnings.extend(p_warn)
        paddle_coverage = float(np.count_nonzero(paddle_mask)) / max(1, paddle_mask.size)
        if paddle_regions and 0 < paddle_coverage <= 0.90:
            return paddle_mask, paddle_regions, paddle_warnings
        paddle_warnings.append("Paddle proposals did not pass the safe-mask quality gate; trying Color Rescue.")

    color_seed, color_detections = detect_colored_text_lines(image_bgr)
    if color_detections:
        rescue_mask, rescue_regions, rescue_warnings = refine_detected_text_mask(
            image_bgr,
            color_detections,
            dilation_kernel=dilation_kernel,
            color_seed=color_seed,
        )
        rescue_coverage = float(np.count_nonzero(rescue_mask)) / max(1, rescue_mask.size)
        if rescue_regions and 0 < rescue_coverage <= 0.90:
            warnings = [*paddle_warnings, *rescue_warnings]
            return rescue_mask, rescue_regions, warnings

    # 3. Webtoon SFX (Sound Effects) & Calligraphy Text Adaptive Rescue
    sfx_mask = generate_adaptive_sfx_mask(image_bgr, dilation_kernel=dilation_kernel)
    sfx_coverage = float(np.count_nonzero(sfx_mask)) / max(1, sfx_mask.size)
    if sfx_coverage > 0:
        sfx_region = {
            "polygon": [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
            "mask_coverage": round(sfx_coverage, 4),
            "source": "sfx_adaptive"
        }
        return sfx_mask, [sfx_region], ["Generated Webtoon SFX adaptive text mask."]

    warnings = paddle_warnings or ["No text lines were detected."]
    return np.zeros(image_bgr.shape[:2], dtype=np.uint8), [], warnings


def _high_quality_text_mask_worker(
    encoded_image: bytes,
    dilation_kernel: int,
) -> tuple[bytes, list[dict[str, Any]], list[str]]:
    """Runs in a separate Python process so Paddle cannot freeze pywebview."""
    image = cv2.imdecode(np.frombuffer(encoded_image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("Unable to decode the mask-editor crop in worker")
    mask, regions, warnings = generate_high_quality_text_mask(image, dilation_kernel)
    success, encoded_mask = cv2.imencode(".png", mask)
    if not success:
        raise RuntimeError("Unable to encode high-quality text mask")
    return encoded_mask.tobytes(), regions, warnings


def _get_worker_pool() -> ProcessPoolExecutor:
    """Create one long-lived worker so the costly model loads only once."""
    global _worker_pool
    with _worker_pool_lock:
        if _worker_pool is None:
            _worker_pool = ProcessPoolExecutor(
                max_workers=1,
                mp_context=multiprocessing.get_context("spawn"),
            )
            logger.info("Started isolated high-quality text-mask worker")
        return _worker_pool


def generate_high_quality_text_mask_isolated(
    image_bgr: np.ndarray,
    dilation_kernel: int = 3,
    timeout_seconds: float = 180.0,
) -> tuple[np.ndarray, list[dict[str, Any]], list[str]]:
    """Run the expensive model outside the desktop/backend process.

    The API request can wait for its result without blocking pywebview's UI
    thread or FastAPI's process-wide GIL. The worker survives for later uses,
    so only the very first request pays the model-load cost.
    """
    success, encoded_image = cv2.imencode(".png", image_bgr)
    if not success:
        raise RuntimeError("Unable to encode the mask-editor crop")
    future = _get_worker_pool().submit(
        _high_quality_text_mask_worker,
        encoded_image.tobytes(),
        max(0, min(56, int(dilation_kernel))),
    )
    encoded_mask, regions, warnings = future.result(timeout=timeout_seconds)
    mask = cv2.imdecode(np.frombuffer(encoded_mask, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise RuntimeError("Unable to decode high-quality text mask from worker")
    return mask, regions, warnings


def shutdown_high_quality_text_mask_worker() -> None:
    """Release the isolated Paddle process during a normal desktop shutdown."""
    global _worker_pool
    with _worker_pool_lock:
        if _worker_pool is not None:
            _worker_pool.shutdown(wait=False, cancel_futures=True)
            _worker_pool = None
