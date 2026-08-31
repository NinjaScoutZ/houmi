"""Smart Balloon Research v2 — 8-step pipeline, research-folder exclusive.

Runs entirely inside e:\\houmi\\research. Does not import or modify any code
under e:\\houmi\\backend.

Pipeline (as specified):
  1. Balloon เดิม            -> bbox ตั้งต้นจาก detector
  2. ดึงค่าสีมากที่สุด        -> dominant bright colour (ได้ขาว)
  3. Selection สีขาว         -> threshold + seed component
  4. ได้ Shape Balloon       -> inner contour
  5. Fill เต็ม               -> Smart Balloon + smart_bbox
  6. Generate Mask Text      -> ink mask ภายใน Smart Balloon
  7. Clean                   -> inpaint
  8. ลงคำด้วยขนาด Smart Balloon -> contour fitting + vertical centering

Why v1 failed (measured, see FINDINGS in the report):
  * crop = text_bbox + 20px lies entirely INSIDE the balloon (border is 75-100%
    white), so a flood from the centre escapes to the crop edge and the
    "balloon" becomes the whole crop -> smart_bbox = (0, 0, W, H).
  * the seed pixel was taken at the geometric centre, which usually lands on a
    black glyph, not on the balloon's white interior.
  * webtoon panels are separated by white gutters, so the balloon's white is
    4-connected to the page background through the balloon's own anti-aliased
    border; without opening, the component leaks page-wide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

RESEARCH_DIR = Path(__file__).resolve().parent
PROJECT_350 = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUT_DIR = RESEARCH_DIR / "smart_balloon_previews_v2"

# --- tuned constants (see report for the sweep that produced them) ----------
WHITE_LEVEL = 200          # step 3 threshold on the dominant-white distance
GLYPH_CLOSE = 25           # close ink holes so glyphs don't split the interior
NECK_OPEN = 15             # sever white necks to the page gutter (r=15 fixed
                           # #10 fill 0.55->0.77 and #19 0.48->0.72)
TAIL_CORE = 0.55           # rows >= 55% of peak width are balloon body
TAIL_REGROW = 0.30
MIN_FILL = 0.45            # sanity: solid balloon shape
MIN_COVER = 0.35           # sanity: must cover the text it belongs to


def imread(path: Path, flags=cv2.IMREAD_COLOR):
    data = np.fromfile(str(path), dtype=np.uint8)
    return None if data.size == 0 else cv2.imdecode(data, flags)


def imwrite(path: Path, img) -> None:
    ok, buf = cv2.imencode(path.suffix or ".png", img)
    if ok:
        buf.tofile(str(path))


@dataclass
class BalloonResult:
    ok: bool
    reason: str = ""
    dominant: int = 255
    white_sel: np.ndarray | None = None
    shape: np.ndarray | None = None
    text_mask: np.ndarray | None = None
    cleaned: np.ndarray | None = None
    smart_bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    core_span: tuple[int, int] = (0, 0)
    row_widths: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int32))
    fill: float = 0.0
    cover: float = 0.0


def dominant_bright(gray: np.ndarray, tx: int, ty: int, tw: int, th: int) -> int:
    """Step 2: dominant colour of the balloon interior.

    Sampling the whole text bbox mixes glyph ink into the histogram, so the mode
    can land on grey.  Restricting to pixels brighter than the bbox median keeps
    the estimate on the paper, and the histogram mode (not the mean) is what
    makes it robust to the anti-aliased glyph edges.
    """
    roi = gray[ty : ty + th, tx : tx + tw]
    if roi.size == 0:
        return 255
    bright = roi[roi >= max(160, int(np.median(roi)))]
    if bright.size < 32:
        return 255
    hist = np.bincount(bright, minlength=256)
    return int(np.argmax(hist))


def geodesic_distance(region: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """Hop count from ``seed`` to every pixel, travelling only inside ``region``.

    Straight-line distance would jump across a balloon border; a geodesic must
    follow the white interior, so two balloons that merely touch stay far apart
    even where their outlines have a gap.
    """
    dist = np.full(region.shape, -1, np.int32)
    cur = (seed & (region > 0)).astype(np.uint8)
    if not cur.any():
        return dist
    dist[cur > 0] = 0
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    step = 0
    while step < 6000:
        nxt = cv2.dilate(cur, kernel) * region
        fresh = (nxt > 0) & (dist < 0)
        if not fresh.any():
            break
        step += 1
        dist[fresh] = step
        cur = nxt.astype(np.uint8)
    return dist


def split_shared_component(
    comp: np.ndarray,
    own_box: tuple[int, int, int, int],
    rival_boxes: list[tuple[int, int, int, int]],
) -> np.ndarray:
    """Keep only the part of ``comp`` closer (geodesically) to our own text.

    Adjacent balloons often share one white component: their outlines touch and
    the dark border has anti-aliased gaps, so no threshold or opening separates
    them (measured on #14/#15: still one component at threshold 245 with no
    closing).  Assigning each pixel to the nearest text block along paths inside
    the balloon splits them without guessing a cut position.
    """
    if not rival_boxes:
        return comp

    def box_mask(box):
        x, y, w, h = box
        m = np.zeros(comp.shape, np.uint8)
        m[max(0, y) : y + h, max(0, x) : x + w] = 1
        return m

    mine = geodesic_distance(comp, box_mask(own_box))
    if not (mine >= 0).any():
        return comp

    keep = mine >= 0
    for box in rival_boxes:
        theirs = geodesic_distance(comp, box_mask(box))
        contested = (theirs >= 0) & (mine >= 0)
        if not contested.any():
            continue
        keep &= ~(contested & (theirs < mine))

    out = (keep & (comp > 0)).astype(np.uint8) * 255
    # Keep the piece that still contains our text.
    n, lab, stats, _ = cv2.connectedComponentsWithStats(out, connectivity=4)
    if n <= 1:
        return comp
    x, y, w, h = own_box
    roi = lab[max(0, y) : y + h, max(0, x) : x + w]
    labels, counts = np.unique(roi[roi > 0], return_counts=True)
    if labels.size == 0:
        return comp
    return (lab == int(labels[np.argmax(counts)])).astype(np.uint8) * 255


def smart_balloon(
    crop_gray: np.ndarray,
    tx: int,
    ty: int,
    tw: int,
    th: int,
    rival_boxes: list[tuple[int, int, int, int]] | None = None,
) -> tuple[np.ndarray | None, str, int]:
    """Steps 2-5: dominant white -> selection -> contour -> filled shape."""
    ch, cw = crop_gray.shape
    dom = dominant_bright(crop_gray, tx, ty, tw, th)

    # Step 3: select pixels close to the dominant white.
    sel = (crop_gray >= min(WHITE_LEVEL, dom - 40)).astype(np.uint8)

    # Close ink holes first: otherwise glyphs cut the interior into fragments
    # and the seed component is only the gap between two lines of text.
    sel = cv2.morphologyEx(
        sel, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (GLYPH_CLOSE, GLYPH_CLOSE)),
    )
    # Sever thin white necks joining the balloon to the page gutter.
    sel = cv2.morphologyEx(
        sel, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (NECK_OPEN * 2 + 1,) * 2),
    )

    n, lab, stats, _ = cv2.connectedComponentsWithStats(sel, connectivity=4)
    if n <= 1:
        return None, "no_white_component", dom

    # Seed by majority vote over the text bbox rather than a single centre pixel
    # (the centre pixel usually sits on a glyph).
    roi = lab[ty : ty + th, tx : tx + tw]
    labels, counts = np.unique(roi[roi > 0], return_counts=True)
    if labels.size == 0:
        return None, "text_bbox_has_no_white", dom
    best = int(labels[np.argmax(counts)])

    comp = (lab == best).astype(np.uint8) * 255

    # If a neighbouring balloon shares this component, cut it along the
    # geodesic midline between the two text blocks.
    comp = split_shared_component(comp, (tx, ty, tw, th), rival_boxes or [])

    # Steps 4-5: outer contour of the interior, filled solid.
    cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None, "no_contour", dom
    shape = np.zeros_like(comp)
    cv2.drawContours(shape, [max(cnts, key=cv2.contourArea)], -1, 255, -1)
    return shape, "", dom


def core_row_span(row_widths: np.ndarray) -> tuple[int, int]:
    """Balloon body rows, excluding the tail (longest contiguous wide run)."""
    if row_widths.size == 0:
        return (0, 0)
    peak = int(row_widths.max())
    if peak <= 0:
        return (0, int(row_widths.size) - 1)
    idx = np.flatnonzero(row_widths >= peak * TAIL_CORE)
    if idx.size == 0:
        return (0, int(row_widths.size) - 1)
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    best = max(runs, key=len)
    y0, y1 = int(best[0]), int(best[-1])
    floor_w = peak * TAIL_REGROW
    while y0 > 0 and floor_w <= row_widths[y0 - 1] <= row_widths[y0]:
        y0 -= 1
    last = int(row_widths.size) - 1
    while y1 < last and floor_w <= row_widths[y1 + 1] <= row_widths[y1]:
        y1 += 1
    return (y0, y1)


def row_width_profile(shape_bin: np.ndarray) -> np.ndarray:
    """Width of the widest horizontal run per row (ignores concavities)."""
    out = np.zeros(shape_bin.shape[0], np.int32)
    for y in range(shape_bin.shape[0]):
        idx = np.flatnonzero(shape_bin[y] > 0)
        if idx.size == 0:
            continue
        runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
        run = max(runs, key=len)
        out[y] = int(run[-1] - run[0] + 1)
    return out


def process(
    crop_bgr: np.ndarray,
    tx: int,
    ty: int,
    tw: int,
    th: int,
    rival_boxes: list[tuple[int, int, int, int]] | None = None,
) -> BalloonResult:
    """Full 8-step pipeline on one balloon crop."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)

    shape, reason, dom = smart_balloon(gray, tx, ty, tw, th, rival_boxes)
    if shape is None:
        return BalloonResult(False, reason, dominant=dom)

    nz = cv2.findNonZero(shape)
    bx, by, bw, bh = cv2.boundingRect(nz)

    # Sanity gate: a collapsed or hollow shape must be rejected, not returned.
    area = int(cv2.countNonZero(shape))
    fill = area / max(1, bw * bh)
    inside = int(cv2.countNonZero(shape[ty : ty + th, tx : tx + tw]))
    cover = inside / max(1, tw * th)
    if fill < MIN_FILL or cover < MIN_COVER:
        return BalloonResult(
            False, f"sanity_fail(fill={fill:.2f},cover={cover:.2f})",
            dominant=dom, fill=fill, cover=cover,
        )

    # Step 6: ink mask, strictly clipped to the Smart Balloon.
    ink = (gray < 150).astype(np.uint8) * 255
    text_mask = cv2.bitwise_and(ink, shape)
    # Drop specks that are not glyphs.
    n, lab, stats, _ = cv2.connectedComponentsWithStats(text_mask, connectivity=8)
    keep = np.zeros_like(text_mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 12:
            keep[lab == i] = 255
    text_mask = keep

    # Step 7: clean.
    dilated = cv2.dilate(
        text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    )
    cleaned = cv2.inpaint(crop_bgr, dilated, 3, cv2.INPAINT_TELEA)

    # Step 8: contour fitting inputs — row profile and tail-free body.
    body = shape[by : by + bh, bx : bx + bw]
    widths = row_width_profile(body)
    span = core_row_span(widths)

    return BalloonResult(
        True, "", dom, None, shape, text_mask, cleaned,
        (bx, by, bw, bh), span, widths, fill, cover,
    )


def crop_for(img: np.ndarray, x: int, y: int, w: int, h: int):
    """Crop generously enough that the balloon's dark border is inside the crop.

    This is the fix for v1's core defect.  ``text_bbox + 20px`` sits wholly
    inside the balloon (its border is 75-100% white), so the white selection had
    no dark boundary to stop at.  Padding by the bbox's own size guarantees the
    balloon outline is visible for every sample in project 350.
    """
    H, W = img.shape[:2]
    pad = max(w, h)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
    return img[y0:y1, x0:x1].copy(), x0, y0


LBL = cv2.FONT_HERSHEY_SIMPLEX


def label(img, text, org, color, scale=0.55):
    cv2.putText(img, text, org, LBL, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, org, LBL, scale, color, 1, cv2.LINE_AA)


def build_preview(crop, res: BalloonResult, tx, ty, tw, th, title: str):
    """Four panels matching the documented research output."""
    # 1. initial bbox
    p1 = crop.copy()
    cv2.rectangle(p1, (tx, ty), (tx + tw, ty + th), (0, 0, 255), 2)
    label(p1, "1. INITIAL BBOX (Red)", (10, 24), (0, 0, 255))

    if not res.ok:
        p2 = np.zeros_like(crop)
        label(p2, "REJECTED", (10, 48), (0, 0, 255), 0.8)
        label(p2, res.reason[:46], (10, 76), (0, 200, 255), 0.45)
        sheet = np.hstack([p1, p2])
        hdr = np.full((56, sheet.shape[1], 3), 28, np.uint8)
        label(hdr, title, (10, 22), (255, 255, 255))
        label(hdr, f"dominant={res.dominant}  {res.reason}", (10, 44), (0, 200, 255), 0.5)
        return np.vstack([hdr, sheet])

    bx, by, bw, bh = res.smart_bbox
    cnts, _ = cv2.findContours(res.shape, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 2. smart balloon shape + smart bbox
    p2 = cv2.cvtColor(res.shape, cv2.COLOR_GRAY2BGR)
    cv2.drawContours(p2, cnts, -1, (0, 255, 0), 2)
    cv2.rectangle(p2, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)
    label(p2, "2. SMART BBOX & CONTOUR", (10, 24), (0, 255, 0))

    # 3. text ink mask inside the balloon
    p3 = cv2.cvtColor(res.text_mask, cv2.COLOR_GRAY2BGR)
    cv2.drawContours(p3, cnts, -1, (0, 120, 0), 1)
    label(p3, "3. TEXT MASK IN BALLOON", (10, 24), (255, 255, 0))

    # 4. cleaned + body span + true vertical centre
    p4 = res.cleaned.copy()
    cv2.drawContours(p4, cnts, -1, (0, 255, 0), 2)
    cy0, cy1 = res.core_span
    ay0, ay1 = by + cy0, by + cy1
    cv2.rectangle(p4, (bx, ay0), (bx + bw, ay1), (0, 255, 0), 2)
    if cy0 > 0:
        cv2.rectangle(p4, (bx, by), (bx + bw, ay0), (0, 0, 255), 1)
        label(p4, "tail", (bx + 6, ay0 - 6), (0, 0, 255), 0.42)
    if cy1 < bh - 1:
        cv2.rectangle(p4, (bx, ay1), (bx + bw, by + bh), (0, 0, 255), 1)
        label(p4, "tail", (bx + 6, ay1 + 18), (0, 0, 255), 0.42)
    mid = (ay0 + ay1) // 2
    cv2.line(p4, (bx, mid), (bx + bw, mid), (255, 150, 0), 2)
    old_mid = by + bh // 2
    if abs(old_mid - mid) > 2:
        cv2.line(p4, (bx, old_mid), (bx + bw, old_mid), (120, 120, 120), 1)
        label(p4, "old center", (bx + bw - 108, old_mid - 6), (150, 150, 150), 0.4)
    label(p4, "4. CLEANED & FITTED", (10, 24), (0, 255, 0))

    sheet = np.hstack([p1, p2, p3, p4])
    hdr = np.full((56, sheet.shape[1], 3), 28, np.uint8)
    label(hdr, title, (10, 22), (255, 255, 255))
    label(
        hdr,
        f"dominant={res.dominant}  smart_bbox={bw}x{bh}  fill={res.fill:.2f}  "
        f"body_rows={cy0}-{cy1}/{bh}  center_shift={mid - old_mid:+d}px",
        (10, 44), (0, 255, 0), 0.5,
    )
    return np.vstack([hdr, sheet])


TARGETS = {6, 9, 10, 14, 15, 18, 19, 26, 28}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proj = json.loads((PROJECT_350 / "project.json").read_text(encoding="utf-8"))

    rows: list[str] = []
    g = 0
    for page in proj["pages"]:
        pn = page["page_number"]
        img = None
        siblings = [
            (int(b["x"]), int(b["y"]), int(b["width"]), int(b["height"]))
            for b in page["text_blocks"]
        ]
        for idx, blk in enumerate(page["text_blocks"]):
            g += 1
            if g not in TARGETS:
                continue
            if img is None:
                img = imread(PROJECT_350 / f"{pn:02d}.jpg")
            if img is None:
                continue

            x, y = int(blk["x"]), int(blk["y"])
            w, h = int(blk["width"]), int(blk["height"])
            crop, ox, oy = crop_for(img, x, y, w, h)
            tx, ty = x - ox, y - oy
            ch, cw = crop.shape[:2]

            # Neighbouring text blocks that fall inside this crop compete for
            # the same white component.
            rivals = []
            for j, (sx, sy, sw, sh) in enumerate(siblings):
                if j == idx:
                    continue
                rx, ry = sx - ox, sy - oy
                if rx + sw > 0 and ry + sh > 0 and rx < cw and ry < ch:
                    rivals.append((rx, ry, sw, sh))

            res = process(crop, tx, ty, w, h, rivals)
            title = f"#{g:02d}  page {pn}  text_bbox {w}x{h}"
            imwrite(OUT_DIR / f"sample_{g:02d}_page{pn:02d}.png",
                    build_preview(crop, res, tx, ty, w, h, title))

            if res.ok:
                bw, bh = res.smart_bbox[2], res.smart_bbox[3]
                cy0, cy1 = res.core_span
                body = cy1 - cy0 + 1
                shift = (cy0 + cy1) // 2 - bh // 2
                rows.append(
                    f"#{g:02d} p{pn} dom={res.dominant} smart={bw}x{bh} "
                    f"(x{bw/w:.2f} wider, x{bh/h:.2f} taller) fill={res.fill:.2f} "
                    f"body={cy0}-{cy1}({body}px) center_shift={shift:+d}px"
                )
            else:
                rows.append(f"#{g:02d} p{pn} REJECTED: {res.reason}")
            print(rows[-1])

    (RESEARCH_DIR / "SMART_BALLOON_V2_SUMMARY.txt").write_text(
        "\n".join(rows), encoding="utf-8"
    )
    print(f"\n{len(rows)} samples -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
