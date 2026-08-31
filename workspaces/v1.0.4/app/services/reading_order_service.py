"""
Reading Order Graph & Sequence Service for Houmi Studio.
Computes 2D reading flow lines and re-orders dialogue blocks for Japanese Manga (RTL), Webtoons, and Western Comics.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.all_models import TextBlock, Page
import logging

logger = logging.getLogger("houmi-reading-order")


def compute_reading_order_sequence(
    blocks: List[TextBlock],
    mode: str = "manga_rtl",
    row_tolerance_px: float = 60.0,
) -> List[TextBlock]:
    """
    Sort a list of TextBlocks according to reading mode geometry.
    - manga_rtl: Groups blocks into horizontal rows (within row_tolerance_px), then sorts Right-to-Left (x descending).
    - webtoon_ltr: Continuous vertical reading (y ascending, secondary x ascending).
    - western_ltr: Left-to-Right rows (y ascending, secondary x ascending).
    """
    if len(blocks) <= 1:
        return list(blocks)

    if mode == "webtoon_ltr":
        # Continuous top-to-bottom scroll flow
        return sorted(blocks, key=lambda b: (b.y, b.x))

    if mode == "western_ltr":
        # Standard Western comic flow: Top-to-bottom rows, Left-to-Right
        sorted_by_y = sorted(blocks, key=lambda b: b.y)
        rows: List[List[TextBlock]] = []
        for b in sorted_by_y:
            placed = False
            for row in rows:
                # If block y is within row_tolerance_px of row average y
                avg_y = sum(item.y for item in row) / len(row)
                if abs(b.y - avg_y) <= row_tolerance_px:
                    row.append(b)
                    placed = True
                    break
            if not placed:
                rows.append([b])

        result: List[TextBlock] = []
        for row in rows:
            # Sort row left-to-right (x ascending)
            sorted_row = sorted(row, key=lambda b: b.x)
            result.extend(sorted_row)
        return result

    # Default: manga_rtl (Japanese / Traditional Manga)
    # Top-to-bottom rows, Right-to-Left within each row
    sorted_by_y = sorted(blocks, key=lambda b: b.y)
    rows: List[List[TextBlock]] = []
    for b in sorted_by_y:
        placed = False
        for row in rows:
            avg_y = sum(item.y for item in row) / len(row)
            if abs(b.y - avg_y) <= row_tolerance_px:
                row.append(b)
                placed = True
                break
        if not placed:
            rows.append([b])

    result: List[TextBlock] = []
    for row in rows:
        # Sort row right-to-left (x descending)
        sorted_row = sorted(row, key=lambda b: -b.x)
        result.extend(sorted_row)
    return result


def compute_reading_flow_lines(ordered_blocks: List[TextBlock]) -> List[Dict[str, Any]]:
    """
    Generate 2D line segments connecting center points of sequential speech bubbles for visual canvas rendering.
    """
    flow_lines = []
    for i in range(len(ordered_blocks) - 1):
        b1 = ordered_blocks[i]
        b2 = ordered_blocks[i + 1]

        c1_x = b1.x + (b1.width / 2.0)
        c1_y = b1.y + (b1.height / 2.0)
        c2_x = b2.x + (b2.width / 2.0)
        c2_y = b2.y + (b2.height / 2.0)

        flow_lines.append({
            "from_index": i + 1,
            "to_index": i + 2,
            "from_block_id": str(b1.id),
            "to_block_id": str(b2.id),
            "start": {"x": round(c1_x, 1), "y": round(c1_y, 1)},
            "end": {"x": round(c2_x, 1), "y": round(c2_y, 1)},
        })
    return flow_lines


def get_page_reading_order(
    page_id: str,
    mode: str,
    db: Session,
) -> Dict[str, Any]:
    """
    Compute reading order sequence and flow lines for a page.
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        return {"error": "Page not found", "blocks": [], "flow_lines": []}

    blocks = db.query(TextBlock).filter(TextBlock.page_id == page_id).all()
    ordered = compute_reading_order_sequence(blocks, mode=mode)
    flow_lines = compute_reading_flow_lines(ordered)

    return {
        "page_id": page_id,
        "mode": mode,
        "total_blocks": len(ordered),
        "blocks": [
            {
                "id": str(b.id),
                "reading_index": idx + 1,
                "current_block_index": b.block_index,
                "x": b.x,
                "y": b.y,
                "width": b.width,
                "height": b.height,
                "center": {"x": round(b.x + b.width / 2.0, 1), "y": round(b.y + b.height / 2.0, 1)},
                "source_text": b.source_text or "",
                "translation": b.translation or "",
            }
            for idx, b in enumerate(ordered)
        ],
        "flow_lines": flow_lines,
    }


def apply_page_reading_order(
    page_id: str,
    block_ids_in_order: List[str],
    db: Session,
) -> Dict[str, Any]:
    """
    Persist new block_index values for TextBlocks on a page according to chosen order.
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")

    blocks_by_id = {str(b.id): b for b in page.text_blocks}
    updated_count = 0

    for idx, b_id in enumerate(block_ids_in_order):
        block = blocks_by_id.get(b_id)
        if block:
            block.block_index = idx
            updated_count += 1

    db.commit()
    return {"status": "success", "updated_count": updated_count}
