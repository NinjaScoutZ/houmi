import cv2
import numpy as np
from pathlib import Path

# =========================================================================
# ส่วนที่ 1: การดูดสีและสกัดเส้นรอบรูปเดิมของบอลลูน (Raw Contour Extraction)
# =========================================================================
img_path = r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\.user_uploaded\media_1786738212525.png"
img = cv2.imread(img_path)
h, w = img.shape[:2]
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# ดูดสีขาวเฉพาะเนื้อบอลลูน (ค่าความสว่าง > 230)
_, white_raw = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY)

# กรองเอาเฉพาะชิ้นที่เป็นบอลลูนหลัก (ตัด noise พื้นหลังเล็กๆ ออก)
n_lbl, labels, stats, _ = cv2.connectedComponentsWithStats(white_raw)
big_lbls = [i for i in range(1, n_lbl) if stats[i, cv2.CC_STAT_AREA] > 20000]

white_mask = np.zeros_like(white_raw)
for l in big_lbls:
    white_mask[labels == l] = 255

# สกัดพิกัดเส้นรอบรูปภายนอก (CHAIN_APPROX_NONE = เก็บทุกพิกเซล ไม่ย่อจุด)
cnts, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
raw_contour = cnts[0].squeeze() # Array พิกัด (x, y)
print(f"Part 1: Raw contour extracted with {len(raw_contour)} exact pixels.")

# =========================================================================
# ส่วนที่ 2: การตรวจจับจุดคอด 2 จุดตรงรอยเชื่อม (P1, P2) ด้วย Convexity Defects
# =========================================================================
hull_idx = cv2.convexHull(raw_contour[:, None, :], returnPoints=False)
defects = cv2.convexityDefects(raw_contour[:, None, :], hull_idx)

defect_list = []
for i in range(len(defects)):
    s, e, f, d = defects[i].flatten()
    defect_list.append((d / 256.0, f, tuple(raw_contour[f])))

defect_list.sort(key=lambda x: x[0], reverse=True)
idx1, idx2 = sorted([defect_list[0][1], defect_list[1][1]])

p1 = tuple(raw_contour[idx1])
p2 = tuple(raw_contour[idx2])
print(f"Part 2: P1={p1} (idx={idx1}), P2={p2} (idx={idx2})")

# =========================================================================
# ส่วนที่ 3: การแบ่งชุดพิกัดเส้นขอบเดิม 100% (Original Arcs Extraction)
# =========================================================================
original_arc_lower = raw_contour[idx1:idx2+1]
original_arc_upper = np.vstack([raw_contour[idx2:], raw_contour[:idx1+1]])
print(f"Part 3: Original Arc Upper = {len(original_arc_upper)} pts, Lower = {len(original_arc_lower)} pts.")

# =========================================================================
# ส่วนที่ 4: การคำนวณคุณสมบัติความโค้งจากขอบที่สมบูรณ์
# =========================================================================
ellipse_upper = cv2.fitEllipseDirect(original_arc_upper[:, None, :])
ellipse_lower = cv2.fitEllipseDirect(original_arc_lower[:, None, :])

print("Part 4: Ellipse Upper:", ellipse_upper)
print("Part 4: Ellipse Lower:", ellipse_lower)

# =========================================================================
# ส่วนที่ 5: ฟังก์ชันสร้างสะพานปิดปากทาง (generate_natural_bridge)
# =========================================================================
def generate_natural_bridge(ellipse, pt_start, pt_end, num_samples=50):
    (xc, yc), (d1, d2), angle = ellipse
    a, b = d1 / 2.0, d2 / 2.0
    rad = np.deg2rad(angle)
    cos_a, sin_a = np.cos(rad), np.sin(rad)
    
    def to_local(p):
        dx, dy = p[0] - xc, p[1] - yc
        x_rot = cos_a * dx + sin_a * dy
        y_rot = -sin_a * dx + cos_a * dy
        return np.arctan2(y_rot / b, x_rot / a)
    
    t_start = to_local(pt_start)
    t_end = to_local(pt_end)
    
    if t_end < t_start: 
        t_end += 2 * np.pi
    if (t_end - t_start) > np.pi: 
        t_start, t_end = t_end, t_start + 2 * np.pi
        
    t_vals = np.linspace(t_start, t_end, num_samples)
    x_loc = a * np.cos(t_vals)
    y_loc = b * np.sin(t_vals)
    
    x_glob = xc + (cos_a * x_loc - sin_a * y_loc)
    y_glob = yc + (sin_a * x_loc + cos_a * y_loc)
    
    return np.column_stack((x_glob, y_glob)).astype(np.int32)

# =========================================================================
# ส่วนที่ 6: การผสานพิกัดและสร้าง Mask ผลลัพธ์ (np.vstack & fillPoly)
# =========================================================================
bridge_upper = generate_natural_bridge(ellipse_upper, p1, p2)
bridge_lower = generate_natural_bridge(ellipse_lower, p2, p1)

contour_balloon1_closed = np.vstack([original_arc_upper, bridge_upper])
contour_balloon2_closed = np.vstack([original_arc_lower, bridge_lower])

mask_balloon1 = np.zeros_like(white_raw)
mask_balloon2 = np.zeros_like(white_raw)
cv2.fillPoly(mask_balloon1, [contour_balloon1_closed], 255)
cv2.fillPoly(mask_balloon2, [contour_balloon2_closed], 255)

out_dir = Path(r"e:\houmi\research\v15_fuzzy_edge_research")
cv2.imwrite(str(out_dir / "pure_natural_balloon1.png"), mask_balloon1)
cv2.imwrite(str(out_dir / "pure_natural_balloon2.png"), mask_balloon2)
print("Part 6: Saved pure_natural_balloon1.png and pure_natural_balloon2.png successfully!")
