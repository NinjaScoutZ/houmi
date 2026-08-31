"""Smart Balloon Dedicated Shape Typesetting Engine.

Independent, shape-aware typesetting pipeline that fits text lines directly
into 2D Smart Balloon contour polygons and centers text at the visual centroid.
"""

from __future__ import annotations

import logging
import math
import cv2
import numpy as np
from PIL import ImageFont
from typing import Any, Optional

from app.services.typesetting.schemas import TypesettingSpec, LayoutRegionSpec, PaddingSpec
from app.services.typesetting.segmentation import segment_text
from app.services.typesetting.service import _resolve_block_font

logger = logging.getLogger(__name__)


import itertools


def _generate_smart_balloon_candidate_splits(tokens: list[str]) -> list[list[str]]:
    """Generate all sensible candidate line break groupings respecting paragraph boundaries."""
    # Split tokens into paragraphs by '\n'
    paragraphs: list[list[str]] = []
    curr_para: list[str] = []
    for tok in tokens:
        if tok == "\n":
            if curr_para:
                paragraphs.append(curr_para)
                curr_para = []
        elif tok.isspace():
            if curr_para:
                curr_para[-1] += tok
        else:
            curr_para.append(tok)
    if curr_para:
        paragraphs.append(curr_para)

    if not paragraphs:
        return []

    # For each paragraph, generate candidate line splits (1, 2, 3, 4 lines)
    def splits_for_para(para_tokens: list[str]) -> list[list[str]]:
        n = len(para_tokens)
        full_p = "".join(para_tokens).strip()
        if not full_p:
            return []
        if n <= 1:
            return [[full_p]]
        if len(full_p) <= 8 or n <= 2:
            return [[full_p]]

        cand: list[list[str]] = [[full_p]]

        # 2-line splits
        for i in range(1, n):
            l1 = "".join(para_tokens[:i]).strip()
            l2 = "".join(para_tokens[i:]).strip()
            if l1 and l2:
                cand.append([l1, l2])

        # 3-line splits
        if n >= 3:
            for i in range(1, n - 1):
                for j in range(i + 1, n):
                    l1 = "".join(para_tokens[:i]).strip()
                    l2 = "".join(para_tokens[i:j]).strip()
                    l3 = "".join(para_tokens[j:]).strip()
                    if l1 and l2 and l3:
                        cand.append([l1, l2, l3])

        # 4-line splits
        if n >= 4 and len(full_p) >= 16:
            for i in range(1, n - 2):
                for j in range(i + 1, n - 1):
                    for k in range(j + 1, n):
                        l1 = "".join(para_tokens[:i]).strip()
                        l2 = "".join(para_tokens[i:j]).strip()
                        l3 = "".join(para_tokens[j:k]).strip()
                        l4 = "".join(para_tokens[k:]).strip()
                        if l1 and l2 and l3 and l4:
                            cand.append([l1, l2, l3, l4])

        return cand

    para_cands = [splits_for_para(p) for p in paragraphs]

    # Combine candidates across paragraphs using Cartesian product
    combined: list[list[str]] = []
    for combo in itertools.product(*para_cands):
        flat_lines = []
        for p_lines in combo:
            flat_lines.extend(p_lines)
        if flat_lines and len(flat_lines) <= 6:
            combined.append(flat_lines)

    return combined


def _detect_script_density_characteristics(text: str, user_line_height: Optional[float] = None) -> dict[str, Any]:
    """
    Calculates language-specific typography metrics (Thai tone marks, CJK square glyphs, Latin word-spacing).
    """
    thai_chars = sum(1 for c in text if '\u0e00' <= c <= '\u0e7f')
    cjk_chars = sum(1 for c in text if '\u3040' <= c <= '\u9fff')
    total_len = max(1, len(text.replace(" ", "").replace("\n", "")))

    thai_ratio = thai_chars / total_len
    cjk_ratio = cjk_chars / total_len

    if thai_ratio > 0.25:
        # Thai script has 4 vertical layers (base, below-vowel, above-vowel, tone mark)
        default_lh = 1.38
        return {
            "line_height_ratio": max(user_line_height or default_lh, default_lh),
            "char_width_ratio": 0.75,
            "target_density_min": 0.55,
            "target_density_max": 0.82,
            "script": "thai",
        }
    elif cjk_ratio > 0.25:
        # CJK ideographic square glyphs
        default_lh = 1.20
        return {
            "line_height_ratio": user_line_height or default_lh,
            "char_width_ratio": 1.00,
            "target_density_min": 0.65,
            "target_density_max": 0.85,
            "script": "cjk",
        }
    else:
        # Latin / Western scripts
        default_lh = 1.22
        return {
            "line_height_ratio": user_line_height or default_lh,
            "char_width_ratio": 0.55,
            "target_density_min": 0.60,
            "target_density_max": 0.80,
            "script": "latin",
        }


def fit_text_to_smart_balloon_shape(
    block: Any,
    sb: dict[str, Any],
    tokens: list[str],
    font_path: str,
    line_height_ratio: float = 1.25,
    min_font_size: float = 12.0,
    max_font_size: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """
    Fits text tokens directly into the Smart Balloon polygon shape using
    Euclidean Distance Transform ($L_2$) for shape-aware safe area margin
    and density-aware optical layout scoring.
    """
    pts = np.array(sb.get("contour_points", []), dtype=np.float32)

    safe_bbox = sb.get("safe_bbox") or {}
    if not safe_bbox or safe_bbox.get("width", 0) <= 5 or safe_bbox.get("height", 0) <= 5:
        if len(pts) > 0:
            x, y, w, h = cv2.boundingRect(pts)
            safe_bbox = {"x": float(x), "y": float(y), "width": float(w), "height": float(h)}
            sb["safe_bbox"] = safe_bbox
        else:
            return None

    bw = float(safe_bbox["width"])
    bh = float(safe_bbox["height"])
    bx = float(safe_bbox["x"])
    by = float(safe_bbox["y"])

    center = sb.get("center") or {"x": bx + bw / 2.0, "y": by + bh / 2.0}
    cx = float(center["x"])
    cy = float(center["y"])

    # 1. Build raster mask of the Smart Balloon shape in local coordinates
    pad = 20
    mask_h = int(round(bh)) + pad * 2
    mask_w = int(round(bw)) + pad * 2
    local_mask = np.zeros((mask_h, mask_w), dtype=np.uint8)

    if len(pts) > 2:
        local_pts = [(int(round(p[0] - bx + pad)), int(round(p[1] - by + pad))) for p in pts]
        cv2.fillPoly(local_mask, [np.array(local_pts, dtype=np.int32)], 255)
    else:
        cv2.rectangle(local_mask, (pad, pad), (int(bw) + pad, int(bh) + pad), 255, -1)

    # 2. Shape-Aware Safe Area Inset via Euclidean Distance Transform ($L_2$)
    dist_map = cv2.distanceTransform(local_mask, cv2.DIST_L2, 5)
    max_clearance = float(np.max(dist_map)) if np.max(dist_map) > 0 else 1.0

    # Safe margin: 8% of minimum balloon dimension, clamped between 3.0px and 22.0px
    safe_margin_thresh = max(3.0, min(22.0, 0.08 * min(bw, bh)))
    safe_mask = (dist_map >= safe_margin_thresh).astype(np.uint8) * 255

    # Fallback if safe_mask is too restrictive on tiny balloons
    if np.count_nonzero(safe_mask) < 25:
        safe_margin_thresh = max(1.0, safe_margin_thresh * 0.5)
        safe_mask = (dist_map >= safe_margin_thresh).astype(np.uint8) * 255
        if np.count_nonzero(safe_mask) == 0:
            safe_mask = local_mask

    safe_contour_area = float(np.count_nonzero(safe_mask))
    row_widths = np.array([np.count_nonzero(safe_mask[y]) for y in range(mask_h)])

    # 3. Density-Aware Script Characteristics
    full_text = "".join(tokens).replace("\n", "").strip()
    n_tok = len([t for t in tokens if t != "\n"])
    if not full_text or n_tok == 0:
        return None

    density_spec = _detect_script_density_characteristics(full_text, line_height_ratio)
    eff_line_height_ratio = density_spec["line_height_ratio"]

    # Dynamic sizing based on text length & balloon aspect
    if len(full_text) <= 10 or n_tok <= 2:
        dim_cap = min(bh * 0.45, bw * 0.35)
    elif len(full_text) <= 25:
        dim_cap = min(bh * 0.30, bw * 0.24)
    else:
        dim_cap = min(bh * 0.22, bw * 0.18)

    if max_font_size is not None and max_font_size > 0:
        search_max = int(min(max_font_size, max(72.0, dim_cap)))
    else:
        search_max = int(max(28.0, min(120.0, dim_cap)))

    search_min = int(max(6.0, min_font_size))
    if search_max < search_min:
        search_max = search_min

    best_layout = None
    best_score = -1e9

    # Generate candidate line break groupings respecting paragraphs
    candidate_splits = _generate_smart_balloon_candidate_splits(tokens)
    if not candidate_splits:
        candidate_splits = [[full_text]]

    # 4. Shape-Aware & Density-Aware Search: Try font sizes from largest down
    for size in range(search_max, search_min - 1, -2):
        try:
            font = ImageFont.truetype(str(font_path), size)
        except Exception:
            font = ImageFont.load_default()

        line_h = size * eff_line_height_ratio

        for cand_lines in candidate_splits:
            num_lines = len(cand_lines)
            total_text_h = num_lines * line_h
            if total_text_h > bh * 0.85:
                continue

            # Centroid-relative vertical bounds
            rel_cy = (cy - by) + pad
            top_y = rel_cy - total_text_h / 2.0
            bottom_y = rel_cy + total_text_h / 2.0

            if top_y < pad or bottom_y > (bh + pad):
                continue

            fits = True
            line_widths = []
            for line_idx, line in enumerate(cand_lines):
                lw = font.getlength(line) if hasattr(font, "getlength") else font.getsize(line)[0]
                line_widths.append(lw)

                l_top = max(0, int(round(top_y + line_idx * line_h)))
                l_bot = min(mask_h - 1, int(round(top_y + (line_idx + 1) * line_h)))
                if l_top >= mask_h or l_bot <= 0 or l_top >= l_bot:
                    fits = False
                    break

                band_widths = row_widths[l_top:l_bot + 1]
                valid_band = band_widths[band_widths > 0]
                if len(valid_band) == 0:
                    fits = False
                    break

                # 15th percentile width for safe area contour constraint
                allowed_w = float(np.percentile(valid_band, 15))
                if lw > allowed_w:
                    fits = False
                    break

            if fits:
                fill_h = total_text_h / bh
                max_lw = max(line_widths)
                width_balance = min(line_widths) / max(1.0, max_lw) if len(line_widths) > 1 else 1.0

                # Calculate optical density ratio
                text_surface_area = sum(lw * line_h for lw in line_widths)
                density_ratio = text_surface_area / max(1.0, safe_contour_area)

                # Density Harmony Bonus: rewards filling 55% - 80% of safe area
                if density_spec["target_density_min"] <= density_ratio <= density_spec["target_density_max"]:
                    density_harmony = 35.0
                elif density_ratio < density_spec["target_density_min"]:
                    density_harmony = 10.0
                else:
                    density_harmony = -20.0

                # Optical profile bonus: diamond / oval profile (middle lines wider than top/bottom)
                shape_harmony = 0.0
                if num_lines >= 3:
                    mid_idx = num_lines // 2
                    if line_widths[mid_idx] >= line_widths[0] and line_widths[mid_idx] >= line_widths[-1]:
                        shape_harmony = 30.0

                if len(full_text) <= 10:
                    score = size * 150.0 + fill_h * 50.0 + density_harmony
                else:
                    score = size * 100.0 + fill_h * 60.0 + width_balance * 30.0 + shape_harmony + density_harmony

                if score > best_score:
                    best_score = score
                    best_layout = {
                        "font_size": float(size),
                        "explicit_lines": cand_lines,
                        "total_height": total_text_h,
                        "center": {"x": cx, "y": cy},
                        "safe_bbox": safe_bbox,
                        "density_ratio": density_ratio,
                        "script": density_spec["script"],
                        "line_height_ratio": eff_line_height_ratio,
                        "safe_margin": safe_margin_thresh,
                    }

        if best_layout and best_layout["font_size"] >= size:
            break

    return best_layout


def compute_smart_balloon_typesetting(
    block: Any,
    project_settings: Optional[dict[str, Any]] = None,
) -> Optional[TypesettingSpec]:
    """
    Dedicated typesetter for Smart Balloon blocks.
    Replaces rectangular typesetting with 100% shape-aware polygon fitting
    and density-aware optical balance.
    """
    from app.config import get_enable_smart_balloon
    if project_settings is not None and not get_enable_smart_balloon(project_settings):
        return None

    sb = getattr(block, "extra_metadata", {}).get("smart_balloon")
    if not sb:
        return None

    pts = np.array(sb.get("contour_points", []), dtype=np.float32)
    safe_bbox = sb.get("safe_bbox")
    if not safe_bbox and len(pts) > 0:
        x, y, w, h = cv2.boundingRect(pts)
        safe_bbox = {"x": float(x), "y": float(y), "width": float(w), "height": float(h)}
        sb["safe_bbox"] = safe_bbox

    if not safe_bbox:
        return None

    raw_text = (getattr(block, "translation", None) or getattr(block, "source_text", None) or "").strip()
    if not raw_text:
        return None

    project_settings = project_settings or {}
    font_family, resolved_entry = _resolve_block_font(block, getattr(block, "bold", False), getattr(block, "italic", False))
    tokens = segment_text(raw_text)

    line_height_ratio = float(getattr(block, "extra_metadata", {}).get("line_height_ratio") or 1.25)
    min_font_size = float(getattr(block, "extra_metadata", {}).get("min_font_size") or 12.0)

    # Check font_size_mode to determine if manual font size is locked
    meta = getattr(block, "extra_metadata", {})
    font_size_mode = meta.get("font_size_mode")
    manual_font_size = meta.get("manual_font_size")

    manual_font_locked = font_size_mode in {"manual", "fixed"} or (
        manual_font_size is not None and font_size_mode not in {"auto"}
    )

    if manual_font_locked and manual_font_size is not None and float(manual_font_size) > 0:
        max_font_size = float(manual_font_size)
    else:
        max_font_size = None

    fitted = fit_text_to_smart_balloon_shape(
        block,
        sb,
        tokens,
        str(resolved_entry.file_path),
        line_height_ratio=line_height_ratio,
        min_font_size=min_font_size,
        max_font_size=max_font_size,
    )

    if not fitted:
        return None

    safe_bbox = fitted["safe_bbox"]
    center = fitted["center"]
    font_size = float(fitted["font_size"])
    explicit_lines = fitted["explicit_lines"]
    eff_lh_ratio = float(fitted.get("line_height_ratio", line_height_ratio))
    line_height = round(font_size * eff_lh_ratio, 2)

    # Preserve block position coordinates during typesetting recalculations.
    # Centering inside balloon is executed on Detect Balloon so user manual adjustments remain intact.
    block.font_size = font_size

    spec = TypesettingSpec(
        layout_engine_version="smart_balloon_v16",
        layout_version="smart_balloon_v16",
        spec_id=f"spec_{block.id}",
        block_id=str(block.id),
        source_signature=f"sb_{block.id}_{font_size}_{len(explicit_lines)}",
        layout_status="valid",
        layout_source="auto",
        decision_status="AUTO_APPLIED",
        requested_font_family=getattr(block, "font_family", "TH Sarabun New") or "TH Sarabun New",
        resolved_font_id=getattr(resolved_entry, "font_id", "default"),
        resolved_font_family=font_family,
        resolved_postscript_name=resolved_entry.postscript_name,
        resolved_font_style=resolved_entry.style,
        font_postscript_name=resolved_entry.postscript_name,
        font_fingerprint=getattr(resolved_entry, "fingerprint", "unknown") or "unknown",
        font_size=font_size,
        bold=bool(getattr(block, "bold", False) or False),
        italic=bool(getattr(block, "italic", False) or False),
        color_hex=getattr(block, "color_hex", "#000000") or "#000000",
        explicit_lines=explicit_lines,
        normalized_text=raw_text,
        line_height=line_height,
        tracking=float(getattr(block, "extra_metadata", {}).get("tracking", 0.0) or 0.0),
        horizontal_align="center",
        text_align="center",
        vertical_align="center",
        padding=PaddingSpec(top=0.0, right=0.0, bottom=0.0, left=0.0),
        layout_region=LayoutRegionSpec(
            x=float(safe_bbox["x"]),
            y=float(safe_bbox["y"]),
            width=float(safe_bbox["width"]),
            height=float(safe_bbox["height"]),
            shape="smart_balloon",
            confidence=0.98,
            source="smart_balloon",
            safe_margin=float(fitted.get("safe_margin", 0.0)),
            mask_path=getattr(block, "smart_mask_path", None),
            contour_version="smart_balloon_v16",
        ),
        shape_type="smart_balloon",
        overflow=False,
        overflow_score=0.0,
        quality_score=98.0,
        metrics={
            "centroid": center,
            "archetype": sb.get("archetype", "SMOOTH_OVAL"),
            "is_smart_balloon": True,
            "density_ratio": fitted.get("density_ratio", 0.70),
            "script": fitted.get("script", "latin"),
            "row_width_constraints": sb.get("row_width_constraints"),
        },
    )

    return spec
