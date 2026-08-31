import sys
sys.path.insert(0, r"e:\houmi\backend")
import cv2
import numpy as np
from pathlib import Path
from app.services.smart_balloon import process_smart_balloon_v15, _compute_row_width_constraints

def wrap_text_shape_adaptive(words: list[str], row_widths: list[float], top_offset: int, line_height: int, font_scale: float, thickness: int) -> list[tuple[str, int, int]]:
    """
    Simulates shape-adaptive text wrapping where each line's max width is bounded by row_widths at that Y.
    Returns list of (line_text, relative_x, relative_y).
    """
    lines = []
    curr_words = []
    line_idx = 0
    word_idx = 0
    
    while word_idx < len(words):
        y_pos = top_offset + line_idx * line_height
        # Sample available width at this Y
        row_idx = max(0, min(len(row_widths) - 1, y_pos))
        max_w = row_widths[row_idx] if row_widths else 300.0
        
        # Try adding next word
        candidate = " ".join(curr_words + [words[word_idx]])
        (tw, th), _ = cv2.getTextSize(candidate, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        
        if tw <= max_w:
            curr_words.append(words[word_idx])
            word_idx += 1
        else:
            if curr_words:
                line_str = " ".join(curr_words)
                (lw, lh), _ = cv2.getTextSize(line_str, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
                lines.append((line_str, y_pos, lw))
                curr_words = []
                line_idx += 1
            else:
                # Word itself is wider than max_w, force break
                lines.append((words[word_idx], y_pos, tw))
                word_idx += 1
                line_idx += 1
                
    if curr_words:
        line_str = " ".join(curr_words)
        (lw, lh), _ = cv2.getTextSize(line_str, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        lines.append((line_str, top_offset + line_idx * line_height, lw))
        
    return lines

# -------------------------------------------------------------------------
# Create 3 Test Balloons (Oval, Diamond/Angular, and Fuzzy/Spiky)
# -------------------------------------------------------------------------
canvas_w, canvas_h = 1600, 1000
canvas = np.full((canvas_h, canvas_w, 3), 24, dtype=np.uint8) # Dark UI background

# Header
cv2.putText(canvas, "SMART BALLOON V15: SHAPE-ADAPTIVE TEXT WRAPPING PREVIEW", (30, 45), cv2.FONT_HERSHEY_DUPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(canvas, "Comparing Fixed Rectangular vs. Dynamic Contour-Guided Row Widths", (30, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 160, 160), 1)

# Sample text for testing
sample_story = "Smart Balloon analyzes the true boundary shape to ensure words gracefully follow the natural curves and spikes without overflowing the safe margin."
words = sample_story.split()

balloons_data = [
    {
        "title": "1. OVAL BALLOON (Short-Long-Short Flow)",
        "shape": "oval",
        "bbox": {"x": 80, "y": 180, "width": 400, "height": 320},
        "text_box": {"x": 140, "y": 240, "width": 280, "height": 200},
    },
    {
        "title": "2. ANGULAR / DIAMOND (Tapered Top & Bottom)",
        "shape": "diamond",
        "bbox": {"x": 580, "y": 180, "width": 420, "height": 320},
        "text_box": {"x": 640, "y": 240, "width": 300, "height": 200},
    },
    {
        "title": "3. SPIKY / FUZZY AURA (Protected Margin)",
        "shape": "fuzzy",
        "bbox": {"x": 1080, "y": 180, "width": 440, "height": 320},
        "text_box": {"x": 1140, "y": 240, "width": 320, "height": 200},
    }
]

# Create sub-image for testing Smart Balloon
sim_page = np.full((canvas_h, canvas_w, 3), 30, dtype=np.uint8)

# 1. Draw Oval
cv2.ellipse(sim_page, (280, 340), (190, 140), 0, 0, 360, (255, 255, 255), -1)
cv2.ellipse(sim_page, (280, 340), (190, 140), 0, 0, 360, (0, 0, 0), 4)

# 2. Draw Diamond
d_pts = np.array([[790, 190], [980, 340], [790, 490], [600, 340]], dtype=np.int32)
cv2.fillPoly(sim_page, [d_pts], (255, 255, 255))
cv2.polylines(sim_page, [d_pts], True, (0, 0, 0), 4)

# 3. Draw Fuzzy / Spiky Star
f_center = (1300, 340)
f_pts = []
for i in range(120):
    ang = i * (2 * np.pi / 120)
    r = 150 + (25 if i % 4 == 0 else -10)
    x = int(f_center[0] + r * np.cos(ang))
    y = int(f_center[1] + r * 0.75 * np.sin(ang))
    f_pts.append([x, y])
cv2.fillPoly(sim_page, [np.array(f_pts)], (255, 255, 255))
for i in range(120):
    ang = i * (2 * np.pi / 120)
    r1 = 145 + (i % 7) * 3
    r2 = 175 + (i % 5) * 4
    x1 = int(f_center[0] + r1 * np.cos(ang))
    y1 = int(f_center[1] + r1 * 0.75 * np.sin(ang))
    x2 = int(f_center[0] + r2 * np.cos(ang))
    y2 = int(f_center[1] + r2 * 0.75 * np.sin(ang))
    cv2.line(sim_page, (x1, y1), (x2, y2), (0, 0, 0), 2)

# Copy base image onto canvas
canvas[120:560, :] = sim_page[120:560, :]

# Process each balloon with Smart Balloon V15
for idx, b_info in enumerate(balloons_data):
    tb = b_info["text_box"]
    res = process_smart_balloon_v15(sim_page, tb, inset_ratio=0.10)
    
    # Draw section headers
    title_x = b_info["bbox"]["x"]
    cv2.putText(canvas, b_info["title"], (title_x, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 215, 0), 2)
    
    if res["success"]:
        # Draw Safe Margin contour (Yellow)
        safe_cnt = np.array(res["contour_points"], dtype=np.int32)
        cv2.polylines(canvas, [safe_cnt], True, (0, 230, 255), 2)
        
        # Draw Centroid (Red circle)
        cx, cy = int(res["center"]["x"]), int(res["center"]["y"])
        cv2.circle(canvas, (cx, cy), 6, (0, 0, 255), -1)
        
        # Retrieve row width constraints
        row_data = res.get("row_width_constraints", {})
        row_widths = row_data.get("row_widths", [])
        
        # Row 1: Naive Rectangular Box Simulation (Top Sub-panel)
        # Row 2: Smart Shape-Adaptive Flow Simulation (Rendered right on the balloon)
        font_scale = 0.55
        thickness = 1
        line_height = 24
        
        # Render text with shape-adaptive wrapping
        safe_bbox = res["safe_bbox"]
        sx, sy, sw, sh = int(safe_bbox["x"]), int(safe_bbox["y"]), int(safe_bbox["width"]), int(safe_bbox["height"])
        
        top_offset = 25 # Start slightly below top of safe bbox
        fitted_lines = wrap_text_shape_adaptive(
            words[:16], 
            row_widths, 
            top_offset=top_offset, 
            line_height=line_height, 
            font_scale=font_scale, 
            thickness=thickness
        )
        
        # Center each line horizontally inside the balloon at (cx)
        total_text_h = len(fitted_lines) * line_height
        start_y = cy - total_text_h // 2 + 15
        
        for l_i, (line_text, _, lw) in enumerate(fitted_lines):
            lx = cx - lw // 2
            ly = start_y + l_i * line_height
            cv2.putText(canvas, line_text, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (15, 15, 15), thickness, cv2.LINE_AA)

# -------------------------------------------------------------------------
# Lower Comparison Panels: Row-Width Profile Diagrams (Y vs Available Width)
# -------------------------------------------------------------------------
cv2.line(canvas, (30, 580), (canvas_w - 30, 580), (80, 80, 80), 1)
cv2.putText(canvas, "ROW-WISE WIDTH PROFILES (Backend -> Frontend Constraint Array)", (30, 615), cv2.FONT_HERSHEY_DUPLEX, 0.75, (255, 255, 255), 2)
cv2.putText(canvas, "Red curve = Per-row max allowed text width W(y) | Grey Box = Old naive fixed bounding width", (30, 640), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

for idx, b_info in enumerate(balloons_data):
    tb = b_info["text_box"]
    res = process_smart_balloon_v15(sim_page, tb, inset_ratio=0.10)
    
    px = b_info["bbox"]["x"]
    py = 670
    pw = 420
    ph = 260
    
    # Panel background
    cv2.rectangle(canvas, (px, py), (px + pw, py + ph), (36, 36, 36), -1)
    cv2.rectangle(canvas, (px, py), (px + pw, py + ph), (70, 70, 70), 1)
    
    row_data = res.get("row_width_constraints", {})
    row_widths = row_data.get("row_widths", [])
    
    if row_widths:
        # Draw naive uniform rectangular baseline (Grey dotted)
        max_possible_w = max(row_widths)
        naive_w = int(max_possible_w * 0.85)
        n_x0 = px + pw // 2 - naive_w // 2
        n_x1 = px + pw // 2 + naive_w // 2
        cv2.rectangle(canvas, (n_x0, py + 20), (n_x1, py + ph - 20), (70, 70, 70), 1)
        cv2.putText(canvas, "Old Naive Rect (Fixed Width)", (px + 15, py + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (140, 140, 140), 1)
        
        # Plot available width as a function of Y
        n_rows = len(row_widths)
        curve_pts = []
        curve_pts_left = []
        curve_pts_right = []
        
        for r_i in range(0, n_rows, 3):
            y_coord = int(py + 20 + (r_i / n_rows) * (ph - 40))
            w_val = row_widths[r_i]
            x_left = int(px + pw // 2 - w_val / 2)
            x_right = int(px + pw // 2 + w_val / 2)
            curve_pts_left.append([x_left, y_coord])
            curve_pts_right.append([x_right, y_coord])
            
        # Draw contour-adaptive envelope
        envelope = curve_pts_left + curve_pts_right[::-1]
        cv2.fillPoly(canvas, [np.array(envelope, dtype=np.int32)], (55, 45, 30))
        cv2.polylines(canvas, [np.array(envelope, dtype=np.int32)], True, (0, 165, 255), 2)
        
        # Archetype badge & stats
        arch = res.get("archetype", "UNKNOWN")
        cv2.putText(canvas, f"Archetype: {arch}", (px + 15, py + ph - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 230, 255), 1)
        cv2.putText(canvas, f"Max Width: {int(max_possible_w)}px", (px + pw - 135, py + ph - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        cv2.putText(canvas, f"Rows: {n_rows}", (px + pw - 85, py + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

# Save result
out_img_path = Path(r"e:\houmi\research\v15_fuzzy_edge_research\shape_adaptive_wrapping_preview.png")
cv2.imwrite(str(out_img_path), canvas)
print(f"Shape-adaptive preview visualization generated successfully at: {out_img_path}")
