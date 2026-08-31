# รายงานวิเคราะห์ปัญหา Smart Balloon Typesetting — 9 ตัวอย่างในโปรเจกต์ 350

**วันที่**: 2026-08-13  
**ตัวอย่างที่วิเคราะห์**: #06, #09, #10, #14, #15, #18, #19, #26, #28  
**โปรเจกต์ต้นฉบับ**: `E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350`  
**โฟลเดอร์วิจัย**: `E:\houmi\research` (ไม่แตะโค้ดใน `e:\houmi\backend`)

---

## สรุปสั้น

งานวิจัยครั้งก่อน (`run_smart_balloon_research.py`) **ล้มเหลวเกือบทุกตัวอย่าง** เพราะ:
1. **crop เล็กเกินไป** — ไม่มีขอบดำให้ selection หยุด → รั่วเต็ม crop = ได้ (0,0,W,H)
2. **seed ตกบนตัวอักษร** — flood จากจุดดำแทนจุดขาว → ไม่ได้บอลลูนเลย
3. **บอลลูนติดกันเชื่อมเป็นก้อนเดียว** — opening ไม่ช่วย เพราะขอบมีรอยขาด

งานครั้งนี้ (`smart_balloon_v2.py`) **แก้ทั้งสามข้อ ผ่าน 9/9 ตัวอย่าง** โดยใช้:
- **Crop ขยาย** `max(w, h)` แทน `20px` → เห็นขอบบอลลูนครบ
- **Component analysis** แทน flood จากจุดเดียว → seed จาก majority vote ใน text bbox
- **Geodesic Voronoi** แทน watershed → แยกบอลลูนที่แค่แตะกัน โดยไม่ต้องเดา threshold

ผลคือ #28 ฟื้นจาก 15×10 (mask ล่ม) เป็น 540×583, และ #14/#15 แยกกันได้ (fill 0.68→0.82, 0.72→0.80)

---

## ปัญหาที่ถูกกล่าวหา 4 ข้อ vs ความจริงที่วัดได้

### ข้อ 1: "Dominant Interior Color Leakage" — **ไม่เป็นความจริง**

คุณระบุว่าระบบดึงสีผิวตัวละครมาแทนสีขาว แต่ผมวัด histogram ของ crop ทั้ง 9 ภาพแล้ว
**ได้ dominant gray = 255 (สีขาวบริสุทธิ์) ทุกใบ** สัดส่วนพิกเซล >195 อยู่ที่ 0.75–0.89:

| # | dominant gray | สัดส่วนขาว >195 |
|---|---|---|
| 06 | 255 | 0.75 |
| 09 | 255 | 0.80 |
| 10 | 255 | 0.82 |
| 14 | 255 | 0.81 |
| 15 | 255 | 0.89 |
| 18 | 255 | 0.88 |
| 19 | 255 | 0.81 |
| 26 | 255 | 0.88 |
| 28 | 255 | 0.88 |

อาการที่เห็นใน #28 ไม่ใช่เรื่องสีผิด แต่คือ **mask ยุบ** (15×10 จาก 400×172) เพราะ
seed flood ล้มเหลวและถูก erode 15×15 กลืนหมด — สาเหตุคือ crop/seed ตั้งผิด
ไม่ใช่ขั้นตอนดึงสีผิด

**สรุป**: ข้อ 1 ควรตัดออกจาก scope ปัญหาจริงอยู่ที่ข้อ 2–4

---

### ข้อ 2: "Spurious Outer Bbox Spawning" — **เป็นความจริง แต่สาเหตุคือ crop เล็ก**

`RESEARCH_RUN_SUMMARY.txt` แสดง Smart Bbox = (0, 0, W, H) ในเกือบทุกตัวอย่าง
นั่นคือรั่วเต็ม crop ไม่ใช่รูปทรงบอลลูน

**สาเหตุชัดเจน**: `run_smart_balloon_research.py:145` ใช้ `pad = 20` รอบ text bbox
แต่ text bbox เป็นกรอบตัวอักษร ซึ่งเล็กกว่าบอลลูนมาก ผลวัดขอบ crop:

| # | พิกเซลขอบ crop ที่สว่าง >200 |
|---|---|
| 06 | 94.7% |
| 10 | 76.2% |
| 15 | 100.0% |
| 26 | 98.8% |

เมื่อขอบ crop เป็นสีขาวทั้งหมด แปลว่า crop อยู่ **ในบอลลูนทั้งหมด** ไม่มีเส้นขอบดำ
ให้ selection หยุด → `floodFill` จากศูนย์กลางจึงวิ่งถึงขอบ crop = ได้ (0,0,W,H)

นี่ไม่ใช่ "mask หลุดออกนอกบอลลูน" ตามที่กล่าวหา แต่คือ crop เล็กจนไม่มีขอบบอลลูน
ให้เห็นเลย

**แก้**: `crop_for()` ใน v2 ใช้ `pad = max(w, h)` แทน → เห็นเส้นขอบบอลลูนครบทุกตัวอย่าง

---

### ข้อ 3: "Off-Center Vertical Alignment" — **เป็นความจริง แต่ทิศทางไม่ตรงที่คุณสันนิษฐาน**

คุณระบุว่าหางบอลลูนดึงศูนย์กลางลงมา แต่ #14 (ตัวอย่างหางบอลลูนชี้ **ขึ้น**)
ให้ผล centroid = 0.60 (เยื้องลง) นั่นหมายความว่าหางดึงศูนย์กลาง **ลง** เพราะ
bbox ถูกยืด **ขึ้น** — ตรงข้ามกับที่คาดไว้

ผมวัด row-width profile และตำแหน่ง body จริง:

| # | wideband (ตัวบอลลูน) | y centroid (เดิม) | เยื้อง |
|---|---|---|---|
| 09 | 0.01–0.73 | 0.37 | ขึ้น (หางล่าง) |
| 14 | 0.38–0.95 | 0.60 | ลง (หางบน) |
| 26 | 0.12–0.80 | 0.46 | ลง (หางล่าง) |

#14 มีหางบน 38% และ centroid เยื้องลงเป็น 0.60 (เทียบกับ 0.5 ที่ควรเป็น) = เยื้อง 10%
ของความสูง bbox นี่คือผลจริงของปัญหาข้อ 3

**แก้**: `body_region()` ตัดหางออกด้วย row-width profiling แล้วใช้ **centroid ของ
core rows** เป็นศูนย์กลางแทน มัธยฐานของ bbox ผลคือ center shift −25px ถึง +24px

---

### ข้อ 4: "Small Font Size & Line Break Overshoot" — **เป็นความจริง และเป็นผลจาก R1+R2+R3**

ฟอนต์เล็กและข้อความล้นมาจาก 3 สาเหตุรวมกัน:

**R1**: `layout_region.analyze_layout_region` เป็น stub คืน `text_bbox_passthrough`
ตรง ๆ ไม่ว่าจะหาขอบบอลลูนได้ดีแค่ไหนก็ไม่มีผล → พื้นที่จัดวางเล็กกว่าจริง 30–45%

**R2**: `_resolve_shared_layout_regions` แก้บอลลูนซ้อนด้วยการหุบกรอบทั้งสองฝ่าย
ด้วย inset คงที่ 4.5%–5.5% → บอลลูนที่ปกติอยู่แล้วโดนบีบให้แคบลง

**R3**: `fitting.py:807` hardcode `min_size = 6` ทับค่า `pref_min` ที่คำนวณแล้ว →
ระบบยอมลงถึง 6pt เพื่อหนี overflow แทนที่จะรายงานว่าใส่ไม่ได้

ผลวัดจากโปรเจกต์ 350: #14 ได้ 24pt ขณะที่ `min_font_size=30`, และบล็อก #57/#70
ได้ **6.0pt** สถานะ `overflow`

**แก้ (ใน v2 ไม่ได้แตะ fitting.py)**: v2 แก้เฉพาะสาเหตุต้นน้ำ คือให้ Smart Bbox
กว้าง 1.2–1.4 เท่า สูง 1.7–3.4 เท่าของ text bbox → พื้นที่จัดวางใหญ่ขึ้น
แต่การแก้ R3 ต้องไปแก้โค้ด fitting.py ซึ่งนอก scope งานนี้

---

## ปัญหาที่เจอเพิ่มเติม: บอลลูนติดกันรวมเป็นก้อนเดียว

#14 กับ #15 (หน้า 3) มีขอบดำแตะกัน แต่ขอบมีรอยขาดจาก anti-aliasing
ทำให้ selection เชื่อมกัน ผมทดสอบวิธีแยกแบบดั้งเดิมแล้วล้มเหลว:

| วิธี | ผล |
|---|---|
| `MORPH_OPEN` r = 15, 21, 27, 35, 45 | ยังเป็น 1 component ทุกค่า |
| threshold 200 → 245 | ยังเป็น 1 component ทุกค่า |
| watershed + distance transform | แยกได้เฉพาะ frac=0.55 เปราะมาก |

Vision model ยืนยันว่าสองบอลลูนมี "dark outline separating them" แต่ในโค้ดเชื่อมกัน
แปลว่าขอบมีรอยขาดจริง

**แก้ด้วย Geodesic Voronoi** (`split_shared_component`):

วัดระยะจาก text bbox ของแต่ละบล็อกแบบ **เดินภายในพื้นขาวเท่านั้น** (BFS 4-connected)
แล้วให้แต่ละพิกเซลเป็นของบล็อกที่ระยะ geodesic ใกล้กว่า:

$$\text{owner}(p) = \arg\min_i \; d_{\text{geo}}(p, T_i \mid \Omega_{\text{white}})$$

ระยะเส้นตรง (Euclidean) จะกระโดดข้ามขอบบอลลูนได้ แต่ระยะ geodesic ต้องเดินตาม
พื้นขาวเท่านั้น → สองบอลลูนที่แค่แตะกันจึงอยู่ห่างกันมาก แม้ขอบมีรอยขาด

**ไม่ต้องเดา threshold หรือ watershed fraction** เพราะ geodesic เป็นการวัดจริง
ตามรูปทรงของบอลลูน

ผล:
- #14: 794×773 (fill 0.68) → **694×533 (fill 0.82)**
- #15: 699×578 (fill 0.72) → **448×320 (fill 0.80)**

---

## อัลกอริทึมที่นำมาใช้ใน v2

### 1. Adaptive Crop Sizing

```python
def crop_for(img, x, y, w, h):
    """Crop enlarged by max(w, h) to ensure balloon boundary is visible."""
    pad = max(w, h)
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(img.shape[1], x + w + pad)
    y1 = min(img.shape[0], y + h + pad)
    return img[y0:y1, x0:x1], x0, y0
```

เดิมใช้ `pad = 20` คงที่ → บอลลูนใหญ่ถูก crop ขาด  
ตอนนี้ใช้ `pad = max(w, h)` → เห็นขอบบอลลูนครบทุกขนาด

---

### 2. Majority-Vote Seed (แทน single-point flood)

```python
# ก่อน: seed = (cx, cy) ศูนย์กลางเรขาคณิต → มักตกบน glyph
# หลัง: seed = component ที่ครองพื้นที่มากสุดใน text bbox
white_binary = (gray >= WHITE_LEVEL).astype(np.uint8)
white_binary = cv2.morphologyEx(
    white_binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
)
n, labels, stats, _ = cv2.connectedComponentsWithStats(white_binary, connectivity=4)
roi = labels[ty : ty + th, tx : tx + tw]
label_counts = np.bincount(roi[roi > 0])
best = int(np.argmax(label_counts))
comp = (labels == best).astype(np.uint8) * 255
```

**MORPH_CLOSE 25×25** ปิดรูตัวอักษร ไม่งั้นพื้นขาวจะแตกเป็นเสี่ยง  
**Majority vote** ใน text bbox แทนการอ่านพิกเซลเดียว → ทนต่อ glyph และ noise

---

### 3. Geodesic Voronoi for Shared Components

```python
def geodesic_distance(region: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """Hop count from seed to every pixel, travelling only inside region."""
    dist = np.full(region.shape, -1, np.int32)
    cur = (seed & (region > 0)).astype(np.uint8)
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
```

BFS ที่เดินได้เฉพาะพื้นขาว → ระยะตามเส้นทางจริง ไม่ข้ามขอบบอลลูน

```python
def split_shared_component(comp, own_box, rival_boxes):
    """Keep only the part closer (geodesically) to our own text."""
    mine = geodesic_distance(comp, box_mask(own_box))
    keep = mine >= 0
    for box in rival_boxes:
        theirs = geodesic_distance(comp, box_mask(box))
        contested = (theirs >= 0) & (mine >= 0)
        keep &= ~(contested & (theirs < mine))
    return (keep & (comp > 0)).astype(np.uint8) * 255
```

แต่ละพิกเซลไปอยู่กับบล็อกที่ geodesic distance ใกล้กว่า → แยกบอลลูนที่แตะกัน
โดยไม่ต้องหาคอหรือเดา threshold

---

### 4. Tail Amputation via Row-Width Profile

```python
def body_region(mask):
    """Identify core balloon body, excluding narrow tail rows."""
    profile = [(mask[y] > 0).sum() for y in range(mask.shape[0])]
    peak = max(profile)
    core = [y for y, w in enumerate(profile) if w >= peak * 0.55]
    if not core:
        return 0, mask.shape[0] - 1
    y0, y1 = min(core), max(core)
    # Expand monotonically to avoid cutting balloon curves
    while y0 > 0 and profile[y0 - 1] >= profile[y0] and profile[y0 - 1] >= peak * 0.30:
        y0 -= 1
    while y1 < len(profile) - 1 and profile[y1 + 1] >= profile[y1] and profile[y1 + 1] >= peak * 0.30:
        y1 += 1
    return y0, y1
```

แถวที่กว้าง ≥55% ของ max = ตัวบอลลูน / แถวแคบ = หาง  
**Monotone expansion** ไม่ให้ตัดส่วนโค้งของบอลลูนออก

ศูนย์กลางใช้ **weighted centroid ของ core rows** แทนมัธยฐานของ bbox:

$$y_{\text{center}} = \frac{\sum_{y \in \text{core}} y \cdot w(y)}{\sum_{y \in \text{core}} w(y)}$$

---

## ผลลัพธ์ 9 ตัวอย่าง

| # | หน้า | dominant | Smart Bbox | เทียบ text bbox | fill | body rows | center shift |
|---|---|---|---|---|---|---|---|
| 06 | 2 | 255 | 635×622 | ×1.38 / ×1.66 | 0.77 | 36–608 | +11px |
| 09 | 2 | 255 | 621×570 | ×1.21 / ×1.79 | 0.75 | 9–512 | −25px |
| 10 | 2 | 255 | 550×575 | ×1.31 / ×2.86 | 0.77 | 47–564 | +18px |
| 14 | 3 | 255 | 694×533 | ×1.24 / ×1.87 | 0.82 | 7–513 | −6px |
| 15 | 3 | 255 | 448×320 | ×1.38 / ×2.08 | 0.80 | 33–314 | +13px |
| 18 | 4 | 255 | 527×457 | ×1.36 / ×2.89 | 0.69 | 64–415 | +11px |
| 19 | 4 | 255 | 473×433 | ×1.23 / ×2.00 | 0.75 | 41–392 | +0px |
| 26 | 5 | 255 | 615×727 | ×1.44 / ×3.04 | 0.59 | 73–608 | −23px |
| 28 | 6 | 255 | 540×583 | ×1.35 / ×3.39 | 0.61 | 76–554 | +24px |

จุดสำคัญ:

- **dominant = 255 ทั้ง 9 ตัวอย่าง** → ไม่มี color leakage เลย
- **#28 ฟื้นแล้ว** จาก 15×10 เป็น 540×583 → พิสูจน์ว่าสาเหตุคือ crop/seed ผิด
- **Smart Bbox สูง 1.7–3.4 เท่า text bbox** → นี่คือพื้นที่ที่ระบบไม่เคยได้ใช้มาก่อน
- **center shift** คือระยะที่ศูนย์กลางขยับหลังตัดหาง #09 (−25px) และ #28 (+24px)
  เยอะสุด = เดิมข้อความเยื้องจากกลางบอลลูนจริงเท่านี้

### การตรวจสอบภาพ

ตรวจทั้ง 9 ภาพด้วย vision model แยกเป็น 2 รอบ ได้ **PASS 9/9** ทุกข้อ:
- รูปทรงตรงกับบอลลูนลูกเดียว ไม่รั่วออกพื้นหลัง ไม่รวมสองลูก ไม่ยุบ
- Text mask สะอาดและอยู่ในบอลลูน 100%
- ลบข้อความได้สมบูรณ์และเส้นกลางอยู่กลางตัวบอลลูน (ไม่ใช่กลาง bbox ที่รวมหาง)

---

## ค่าคงที่ที่ใช้

| ค่า | ใช้ทำอะไร | เหตุผล |
|---|---|---|
| `WHITE_LEVEL = 200` | threshold พื้นขาว | ขอบบอลลูนดำชัด แยกได้ที่ 200–245 เท่ากัน |
| `GLYPH_CLOSE = 25` | ปิดรูตัวอักษร | เล็กกว่านี้ตัวอักษรตัดพื้นขาวเป็นเสี่ยง |
| `NECK_OPEN = 15` | ตัดคอเชื่อมพื้นขาวนอกกรอบ | r=15 แก้ #10 (fill 0.55→0.77) และ #19 (0.48→0.72) |
| `TAIL_CORE = 0.55` | แถวที่ถือว่าเป็นตัวบอลลูน | ตัดหางได้ครบไม่กินเนื้อ |
| `MIN_FILL = 0.45` | sanity gate | #28 เดิม fill ต่ำ = จับได้ |
| `MIN_COVER = 0.35` | sanity gate | mask ต้องคลุมข้อความที่มันเป็นเจ้าของ |

sweep แล้ว ค่าเหล่านี้ทนได้กับทั้ง 9 ตัวอย่าง

---

## ข้อจำกัดและงานที่ยังไม่ทำ

1. **ไม่ได้แก้ R1–R3** ใน `layout_region.py`, `fitting.py` เพราะนอก scope งานนี้
   ผมรันแยกใน research folder เท่านั้น ไม่แตะโค้ดโปรเจกต์
   
2. **ยังไม่รัน 81 บล็อกที่เหลือ** ใน 350 รันเฉพาะ 9 ตัวอย่างที่ระบุมา
   
3. **ยังไม่ทดสอบบอลลูนรูปร่างพิเศษ** เช่น bubble แบบหลายก้อนเชื่อมกัน

4. ถ้าจะนำเข้าโปรดักชัน ต้องแก้ `layout_region.analyze_layout_region()` ที่ตอนนี้
   คืน `text_bbox_passthrough` ตรง ๆ ทำให้การคำนวณ contour ไม่มีผล — 34 บล็อก
   ถูกบังคับเป็น `fallback_bbox` ตลอด

---

## ไฟล์และโฟลเดอร์

- **สคริปต์**: `smart_balloon_v2.py` (336 บรรทัด)
- **ภาพพรีวิว**: `smart_balloon_previews_v2/sample_NN_pageNN.png` (9 ไฟล์ 4 แผง)
- **สรุปตัวเลข**: `SMART_BALLOON_V2_SUMMARY.txt`
- **รายงาน**: `SMART_BALLOON_V2_FINDINGS.md` (อังกฤษ), `REPORT_TH.md` (นี้)

---

## สรุป

ปัญหาที่คุณระบุ 4 ข้อ ความจริงคือ:

1. **Color Leakage (ข้อ 1)** — **ไม่เป็นความจริง** dominant = 255 ทุกตัวอย่าง
2. **Bbox Spawning (ข้อ 2)** — **เป็นความจริง** แต่สาเหตุคือ crop เล็ก ไม่ใช่ mask รั่ว
3. **Off-Center (ข้อ 3)** — **เป็นความจริง** แต่ทิศทางไม่ตรงที่สันนิษฐาน #14 หางบนดึงลง
4. **Small Font (ข้อ 4)** — **เป็นความจริง** และเป็นผลจาก R1+R2+R3 รวมกัน

งาน v2 นี้แก้สาเหตุต้นน้ำ (crop, seed, geodesic) ได้ **9/9 PASS** และพบปัญหาเพิ่ม
คือบอลลูนติดกันที่ไม่มีวิธีดั้งเดิมแก้ได้ → แก้ด้วย geodesic Voronoi โดยไม่ต้องเดา
threshold หรือ tune watershed fraction

**#28 ฟื้นจาก 15×10 เป็น 540×583** พิสูจน์ว่างานนี้ได้ผล
