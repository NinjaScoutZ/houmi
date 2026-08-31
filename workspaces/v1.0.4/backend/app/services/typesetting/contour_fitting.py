"""Contour-aware width constraints for speech-balloon typesetting.

The production line engine still owns line breaking and scoring.  This module
only supplies a conservative, mask-derived width function so the existing
engine can remain the safe fallback when a mask is missing or uncertain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

import cv2
import numpy as np


LineWidthProvider = Callable[[int, int, float, float, float, float], float]


def _longest_run_width(row: np.ndarray, preferred_x: int) -> int:
    """Return the width of the run containing preferred_x, or the longest run."""
    indices = np.flatnonzero(row > 0)
    if indices.size == 0:
        return 0

    split_at = np.flatnonzero(np.diff(indices) > 1) + 1
    runs = np.split(indices, split_at)
    containing = [run for run in runs if int(run[0]) <= preferred_x <= int(run[-1])]
    selected = containing[0] if containing else max(runs, key=len)
    return int(selected[-1] - selected[0] + 1)


@dataclass(frozen=True)
class ContourWidthProfile:
    """A normalized row-width profile for one balloon interior mask."""

    row_widths: tuple[int, ...]
    source_width: int
    source_height: int
    usable_row_ratio: float
    area_ratio: float

    @property
    def is_usable(self) -> bool:
        return (
            self.source_width >= 8
            and self.source_height >= 8
            and self.usable_row_ratio >= 0.20
            and max(self.row_widths, default=0) >= 4
        )

    def allowed_width(
        self,
        line_index: int,
        num_lines: int,
        line_height: float,
        line_spacing: float,
        block_w: float,
        block_h: float,
    ) -> float:
        """Return a conservative width for a line's vertical band.

        Coordinates match ``fitting._line_allowed_width``: the text group is
        centered in the region, then the width is sampled from the mask around
        that line.  Sampling a band, instead of a single row, avoids approving
        a glyph whose top or bottom crosses a narrow contour.
        """
        if not self.is_usable or block_w <= 0 or block_h <= 0 or num_lines <= 0:
            return 0.0

        total_height = num_lines * line_height + max(0, num_lines - 1) * line_spacing
        center_from_top = line_index * (line_height + line_spacing) + line_height / 2.0
        center = block_h / 2.0 + center_from_top - total_height / 2.0
        scale_y = self.source_height / max(float(block_h), 1.0)
        center_y = center * scale_y
        # Font ink generally occupies less than the full line box.  A 70% band
        # is conservative for ascenders/diacritics while not punishing normal
        # leading at the contour's first/last row.
        half_band = max(0.5, line_height * scale_y * 0.25)
        y0 = max(0, int(np.floor(center_y - half_band)))
        y1 = min(self.source_height - 1, int(np.ceil(center_y + half_band)))
        widths = self.row_widths[y0 : y1 + 1]
        valid_widths = [w for w in widths if w > 0]
        if not valid_widths:
            return 0.0
        # Use 25th percentile of valid rows in the band — conservative enough to
        # keep text inside spiky/star contours whose edges narrow rapidly.
        effective_w = float(np.percentile(valid_widths, 25)) if len(valid_widths) >= 3 else float(min(valid_widths))
        scale_x = block_w / max(float(self.source_width), 1.0)
        return max(0.0, min(block_w, effective_w * scale_x))

    def provider(self) -> LineWidthProvider:
        return self.allowed_width


def build_contour_width_profile(
    mask: np.ndarray,
    *,
    target_width: float | None = None,
    target_height: float | None = None,
    padding: float = 0.0,
) -> ContourWidthProfile | None:
    """Build a profile from a binary mask, returning ``None`` for bad input."""
    if mask is None or not isinstance(mask, np.ndarray) or mask.size == 0:
        return None
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    if mask.ndim != 2:
        return None

    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    if target_width and target_height and (
        int(round(target_width)) != binary.shape[1]
        or int(round(target_height)) != binary.shape[0]
    ):
        binary = cv2.resize(
            binary,
            (max(1, int(round(target_width))), max(1, int(round(target_height)))),
            interpolation=cv2.INTER_NEAREST,
        )

    radius = max(0, int(round(float(padding))))
    if radius:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1)
        )
        binary = cv2.erode(binary, kernel)

    height, width = binary.shape[:2]
    preferred_x = width // 2
    row_widths = tuple(_longest_run_width(binary[y], preferred_x) for y in range(height))
    usable_rows = sum(value > 0 for value in row_widths)
    area_ratio = float(np.count_nonzero(binary)) / max(1, width * height)
    profile = ContourWidthProfile(
        row_widths=row_widths,
        source_width=width,
        source_height=height,
        usable_row_ratio=usable_rows / max(1, height),
        area_ratio=area_ratio,
    )
    return profile if profile.is_usable else None


def _read_mask(path: str | Path) -> np.ndarray | None:
    try:
        from app.utils.image_utils import cv2_imread_unicode
        return cv2_imread_unicode(path, cv2.IMREAD_GRAYSCALE)
    except (OSError, ValueError, TypeError):
        return None


def _mask_path_candidates(block: Any, region: dict[str, Any]) -> list[str | Path]:
    metadata = getattr(block, "extra_metadata", None) or {}
    candidates: list[str | Path] = []
    for candidate in (
        region.get("mask_path"),
        getattr(block, "smart_mask_path", None),
        metadata.get("mask_path") if isinstance(metadata, dict) else None,
        metadata.get("smart_mask_path") if isinstance(metadata, dict) else None,
    ):
        if candidate and str(candidate) not in {str(path) for path in candidates}:
            candidates.append(candidate)

    # Projects created before ``layout_region.mask_path`` was introduced often
    # kept the mask only under the conventional ``mask_<block-id>.png`` name.
    page = getattr(block, "page", None)
    block_id = getattr(block, "id", None)
    if page is not None and block_id is not None:
        source_path = getattr(page, "source_image_path", None)
        if source_path:
            source_parent = Path(str(source_path)).parent
            legacy_name = f"mask_{block_id}.png"
            candidates.extend(
                [source_parent / legacy_name, source_parent / "masks" / legacy_name]
            )
        project = getattr(page, "project", None)
        settings = getattr(project, "settings", None) or {}
        local_folder = settings.get("local_folder") if isinstance(settings, dict) else None
        if local_folder:
            page_number = max(0, int(getattr(page, "page_number", 0) or 0))
            candidates.append(
                Path(str(local_folder))
                / "masks"
                / f"{page_number:02d}_mask_{block_id}.png"
            )
    return candidates


def resolve_mask_path(block: Any, region: dict[str, Any]) -> str | None:
    """Resolve an explicit or legacy mask path without creating any folders."""
    candidates = _mask_path_candidates(block, region)
    for candidate in candidates:
        if Path(str(candidate)).is_file():
            return str(candidate)
    # Preserve an explicit missing path in the typesetting signature so that a
    # mask appearing later invalidates a previously cached fallback spec.
    return str(candidates[0]) if candidates else None


def profile_for_block(
    block: Any,
    region: dict[str, Any],
    *,
    target_width: float,
    target_height: float,
    padding: float = 0.0,
) -> ContourWidthProfile | None:
    """Load a contour profile for the block from Smart Balloon polygon or mask asset."""
    # 1. Primary: exact Smart Balloon contour polygon in block.extra_metadata
    metadata = getattr(block, "extra_metadata", None) or {}
    sb_meta = metadata.get("smart_balloon") if isinstance(metadata, dict) else None
    if isinstance(sb_meta, dict):
        contour_points = sb_meta.get("contour_points") or sb_meta.get("raw_contour_points")
        if isinstance(contour_points, list) and len(contour_points) > 2:
            rx = float(region.get("x", 0.0))
            ry = float(region.get("y", 0.0))
            rw = max(1, int(round(float(region.get("width", target_width)))))
            rh = max(1, int(round(float(region.get("height", target_height)))))
            local_pts = [(int(round(px - rx)), int(round(py - ry))) for px, py in contour_points]
            local_mask = np.zeros((rh, rw), dtype=np.uint8)
            cv2.fillPoly(local_mask, [np.array(local_pts, dtype=np.int32).reshape(-1, 1, 2)], 255)
            profile = build_contour_width_profile(
                local_mask,
                target_width=target_width,
                target_height=target_height,
                padding=padding,
            )
            if profile is not None and profile.is_usable:
                return profile

    # 2. Fallback: mask file
    mask_path = resolve_mask_path(block, region)
    if mask_path is None:
        return None

    mask = _read_mask(mask_path)
    if mask is None:
        return None

    x = max(0, int(np.floor(float(region.get("x", 0.0)))))
    y = max(0, int(np.floor(float(region.get("y", 0.0)))))
    w = max(1, int(np.ceil(float(region.get("width", target_width)))))
    h = max(1, int(np.ceil(float(region.get("height", target_height)))))

    mask_h, mask_w = mask.shape[:2]

    if mask_w >= x + 2 and mask_h >= y + 2:
        # Full-page mask: crop using absolute layout region coordinates
        crop = mask[y : min(mask_h, y + h), x : min(mask_w, x + w)]
    else:
        # If mask is a crop from compute_smart_balloon_bounds (has zero padding around balloon),
        # extract the exact non-zero balloon bounding box so padding doesn't shrink the profile
        nz = cv2.findNonZero(mask)
        if nz is not None:
            mx, my, mw, mh = cv2.boundingRect(nz)
            crop = mask[my : my + mh, mx : mx + mw]
        else:
            crop = mask

    if crop.size == 0:
        return None
    return build_contour_width_profile(
        crop,
        target_width=target_width,
        target_height=target_height,
        padding=padding,
    )
