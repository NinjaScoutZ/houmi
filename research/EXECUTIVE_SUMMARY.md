# สรุปการวิเคราะห์ปัญหา Smart Balloon Typesetting

## คำถามเดิม
วิเคราะห์สาเหตุเชิงลึกและเสนอแนวทางแก้ไขระดับอัลกอริทึมสำหรับบอลลูน 9 ตัวอย่าง (#06, #09, #10, #14, #15, #18, #19, #26, #28) โดยอ้างอิงปัญหา 4 ด้าน:

1. Dominant Interior Color Leakage
2. Spurious Outer Bbox Spawning  
3. Off-Center Vertical Alignment
4. Small Font Size & Line Break Overshoot

## คำตอบสั้น

**ปัญหาข้อ 1 (Color Leakage) ไม่เป็นความจริง** — dominant = 255 ทั้ง 9 ตัวอย่าง ไม่มีการดึงสีผิวตัวละคร

**ปัญหาจริงคือ crop/seed/shared-component ผิด** แก้ด้วย:
- **Adaptive crop** `max(w,h)` แทน 20px → เห็นขอบบอลลูนครบ
- **Component analysis** แทน flood จากจุดเดียว → seed จาก majority vote
- **Geodesic Voronoi** แทน watershed → แยกบอลลูนติดกันโดยไม่ต้องเดา threshold
- **Row-width profiling** → ตัดหางและใช้ centroid จริงของ body

**ผลลัพธ์: PASS 9/9 ตัวอย่าง**
- #28 ฟื้นจาก 15×10 → 540×583
- #14/#15 แยกกัน (fill 0.68→0.82, 0.72→0.80)
- Smart Bbox สูง 1.7–3.4 เท่า text bbox (พื้นที่ที่ระบบไม่เคยได้ใช้มาก่อน)

## เอกสารฉบับเต็ม

- **REPORT_TH.md** — รายงานวิเคราะห์ปัญหาทั้งหมดพร้อมตัวเลข (21K, ภาษาไทย)
- **ALGORITHMS.md** — อัลกอริทึมทางคณิตศาสตร์ทั้ง 5 ข้อ (10K, Mathematical Morphology)
- **SMART_BALLOON_V2_FINDINGS.md** — ผลการค้นพบและวิธีแก้ (11K, English)
- **smart_balloon_v2.py** — สคริปต์วิจัยที่รันได้ (18K, 336 บรรทัด)
- **smart_balloon_previews_v2/** — ภาพพรีวิว 4 แผงต่อตัวอย่าง (9 ไฟล์)

## อัลกอริทึมหลักที่นำเสนอ

### 1. Adaptive Crop Sizing
```python
pad = max(w, h)  # แทน 20px คงที่
crop = img[y-pad:y+h+pad, x-pad:x+w+pad]
```
การันตีเห็นขอบบอลลูนครบทุกขนาด

### 2. Component-Based Seed Selection
```python
# Binarize → Close 25×25 → Connected Components → Majority vote ใน text bbox
binary = (gray >= 200)
closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, (25,25))
labels = cv2.connectedComponentsWithStats(closed, connectivity=4)
best_label = most_common_in_roi(labels, text_bbox)
```
ทนต่อ glyph และ noise ไม่ต้องเดาจุด seed

### 3. Geodesic Voronoi Separation
```python
def geodesic_distance(region, seed):
    """BFS hop count from seed, travelling only inside region"""
    dist = np.full(region.shape, -1, np.int32)
    dist[seed] = 0
    queue = seed_positions
    while queue:
        expand_4_neighbors(queue, region, dist)
    return dist

# แต่ละพิกเซลเป็นของบล็อกที่ geodesic distance ใกล้ที่สุด
for block in blocks:
    d[block] = geodesic_distance(white_region, block.text_bbox)
owner = argmin(d, axis=0)
```
แยกบอลลูนที่แค่แตะกัน ไม่ต้อง tune threshold หรือ watershed fraction

### 4. Tail Amputation via Row-Width Profile
```python
profile = [np.sum(mask[y] > 0) for y in range(H)]
peak = max(profile)
core_rows = [y for y, w in enumerate(profile) if w >= 0.55 * peak]
y0, y1 = min(core_rows), max(core_rows)
# Monotone expansion ไม่ให้ตัดส่วนโค้ง
while y0 > 0 and profile[y0-1] >= profile[y0] and profile[y0-1] >= 0.30*peak:
    y0 -= 1
# Weighted centroid
center_y = sum(y * profile[y] for y in core_rows) / sum(profile[core_rows])
```
ศูนย์กลางจริงของตัวบอลลูน ไม่ถูกดึงโดยหาง

### 5. Sanity Gates
```python
fill = np.count_nonzero(mask) / (w * h)
coverage = np.count_nonzero(text_mask & balloon_mask) / np.count_nonzero(text_mask)
assert fill >= 0.45 and coverage >= 0.35
```
จับ mask ที่ยุบหรือรั่ว (#28 v1 ได้ fill=0.08 ถูกจับได้ทันที)

## ข้อมูลสำคัญที่พบ

### 1. ไม่มี Color Leakage
| Sample | Dominant Gray | White Ratio >195 |
|---|---|---|
| ทั้ง 9 | 255 | 0.75–0.89 |

ขั้นตอนดึงสีทำงานถูกต้อง ปัญหาที่เห็นเป็นเรื่อง mask ไม่ใช่สี

### 2. Crop เล็กเกินไปคือสาเหตุหลัก
| Sample | Edge brightness (v1) | Edge brightness (v2) |
|---|---|---|
| #06 | 94.7% ขาว | 12.3% ขาว ✓ |
| #15 | 100.0% ขาว | 8.7% ขาว ✓ |
| #28 | 98.8% ขาว | 15.2% ขาว ✓ |

v1 crop อยู่ในบอลลูนทั้งหมด → selection รั่ว

### 3. Smart Bbox ใหญ่กว่า Text Bbox มาก
| Sample | Smart Bbox | Width ratio | Height ratio |
|---|---|---|---|
| #06 | 635×622 | ×1.38 | ×1.66 |
| #09 | 621×570 | ×1.21 | ×1.79 |
| #28 | 540×583 | ×1.35 | ×3.39 |

นี่คือพื้นที่ที่ระบบไม่เคยได้ใช้เพราะ `analyze_layout_region` คืน text bbox ตรง ๆ

### 4. Center Shift จากหางบอลลูน
| Sample | Body Span | Center Shift |
|---|---|---|
| #09 | rows 9–512 (0.01–0.73) | −25px ↑ |
| #14 | rows 7–513 (0.38–0.95) | −6px ↓ |
| #26 | rows 73–608 (0.12–0.80) | −23px ↓ |
| #28 | rows 76–554 (0.14–0.95) | +24px ↑ |

หางทำให้ศูนย์กลาง bbox เยื้อง 10–12% ของความสูง

## ข้อจำกัด

- รันเฉพาะ 9 ตัวอย่างที่ระบุ ไม่ได้ทดสอบ 81 บล็อกที่เหลือ
- ไม่ได้แก้โค้ดใน `e:\houmi\backend` — รันใน research folder เท่านั้น
- ยังไม่ทดสอบบอลลูนรูปร่างพิเศษ (multi-blob, extreme aspect ratio)

## ขั้นตอนถัดไป (ถ้านำเข้าโปรดักชัน)

1. แก้ `layout_region.analyze_layout_region()` ที่ตอนนี้เป็น stub คืน text bbox ตรง ๆ
2. ใส่อัลกอริทึม geodesic Voronoi ลงใน `_resolve_shared_layout_regions`
3. แก้ `fitting.py:807` ห้ามลง 6pt เงียบ ๆ ต้องรายงาน warning
4. ทดสอบกับโปรเจกต์อื่น ๆ เพื่อยืนยันความทนทาน

## วิธีรันซ้ำ

```bash
cd E:\houmi\research
python smart_balloon_v2.py
# หรือ
bash RUN_AGAIN.sh
```

ผลลัพธ์:
- `smart_balloon_previews_v2/*.png` — ภาพพรีวิว 4 แผง
- `SMART_BALLOON_V2_SUMMARY.txt` — ตัวเลขสรุป 1 บรรทัดต่อตัวอย่าง

---

**วันที่**: 2026-08-13  
**โปรเจกต์ทดสอบ**: E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350  
**ผลลัพธ์**: ✅ PASS 9/9 ตัวอย่าง  
**สคริปต์**: `smart_balloon_v2.py` (336 บรรทัด, รันได้ standalone)
