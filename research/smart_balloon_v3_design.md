# Smart Balloon v3 — Full-Page Component-First Design

## ปัญหาของ v2

v2 ใช้ **crop-per-block**: แต่ละบล็อกสร้าง crop แล้วหา balloon ใน crop นั้น

ข้อจำกัด:
- Crop ต้องครอบ rival text blocks → ต้อง pad ใหญ่
- แต่ pad ใหญ่เกิน → ช้า + memory
- ถ้า rival อยู่นอก crop → Geodesic Voronoi ไม่ทำงาน

**ตัวอย่าง**: บอลลูน #14/#15 เชื่อมกัน แต่ crop(#15) ไม่ครอบ text bbox ของ #14 เลย

## แนวทางใหม่: Component-First

### Phase 1: Extract All Balloons (Full Page)

```python
def extract_all_balloons(page_img, text_blocks):
    """หาบอลลูนทั้งหมดในหน้าพร้อมกัน ไม่ crop"""
    
    # 1. Detect dominant white zones ทั้งหน้า
    gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)
    white_sel = (gray >= 200).astype(np.uint8)
    
    # 2. Morphology เพื่อ sever necks + close ink holes
    white_sel = cv2.morphologyEx(white_sel, cv2.MORPH_CLOSE, (25, 25))
    white_sel = cv2.morphologyEx(white_sel, cv2.MORPH_OPEN, (31, 31))
    
    # 3. Connected components → แต่ละ component เป็นบอลลูน (หรือหลายบอลลูนเชื่อมกัน)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(white_sel, connectivity=4)
    
    components = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 5000:  # กรองขยะ
            continue
        
        mask = (labels == i).astype(np.uint8) * 255
        x, y, w, h = stats[i, cv2.CC_STAT_LEFT:cv2.CC_STAT_TOP+3]
        
        # หา text blocks ที่อยู่ใน component นี้
        blocks_in_comp = []
        for j, blk in enumerate(text_blocks):
            bx, by, bw, bh = blk["x"], blk["y"], blk["width"], blk["height"]
            roi = mask[by:by+bh, bx:bx+bw]
            if roi.size > 0 and cv2.countNonZero(roi) > bw * bh * 0.3:
                blocks_in_comp.append((j, bx, by, bw, bh))
        
        components.append({
            "id": i,
            "mask": mask,
            "bbox": (x, y, w, h),
            "blocks": blocks_in_comp,
        })
    
    return components
```

### Phase 2: Split Shared Components

```python
def split_component_if_shared(comp, page_img):
    """ถ้า component มีหลาย text blocks → split ด้วย Geodesic Voronoi"""
    
    if len(comp["blocks"]) <= 1:
        # บอลลูนเดียว → ใช้ mask เดิม
        return {comp["blocks"][0][0]: comp["mask"]} if comp["blocks"] else {}
    
    # หลายบอลลูน → split
    mask = comp["mask"]
    result = {}
    
    for idx, bx, by, bw, bh in comp["blocks"]:
        # Geodesic distance จาก text bbox นี้
        seed = np.zeros_like(mask)
        seed[by:by+bh, bx:bx+bw] = 1
        dist_mine = geodesic_distance(mask, seed)
        
        # เริ่มต้นด้วย keep ทุกพิกเซล
        keep = (dist_mine >= 0)
        
        # แข่งกับ rivals
        for ridx, rx, ry, rw, rh in comp["blocks"]:
            if ridx == idx:
                continue
            rival_seed = np.zeros_like(mask)
            rival_seed[ry:ry+rh, rx:rx+rw] = 1
            dist_rival = geodesic_distance(mask, rival_seed)
            
            contested = (dist_mine >= 0) & (dist_rival >= 0)
            # ถ้า rival ใกล้กว่า → ทิ้ง
            keep &= ~(contested & (dist_rival < dist_mine))
        
        # ได้ mask ของบอลลูนนี้
        result[idx] = ((keep & (mask > 0)).astype(np.uint8) * 255)
    
    return result
```

### Phase 3: Assign to Blocks

```python
def assign_balloons_to_blocks(components, page_img, text_blocks):
    """แจก mask ให้แต่ละ text block"""
    
    block_masks = {}
    
    for comp in components:
        split_masks = split_component_if_shared(comp, page_img)
        
        for block_idx, mask in split_masks.items():
            # Crop เฉพาะ bbox ของ mask นี้
            nz = cv2.findNonZero(mask)
            if nz is None:
                continue
            x, y, w, h = cv2.boundingRect(nz)
            crop_mask = mask[y:y+h, x:x+w]
            crop_img = page_img[y:y+h, x:x+w]
            
            block_masks[block_idx] = {
                "mask": crop_mask,
                "crop": crop_img,
                "offset": (x, y),
            }
    
    return block_masks
```

## ข้อดี

1. **ไม่ต้องกังวล crop size** — ทำงานบน full page จึงเห็นทุกอย่าง
2. **Geodesic Voronoi ทำงานถูกต้อง** — seed ทุกตัวอยู่ใน frame เดียวกัน
3. **ประหยัด memory** — morphology ทำครั้งเดียวต่อหน้า แทนครั้งต่อบล็อก
4. **Robust** — ไม่แพ้ edge case แบบ #14/#15

## ข้อเสีย

1. **Refactor ใหญ่** — ต้องเขียน pipeline ใหม่ทั้งหมด
2. **ซับซ้อนกว่า** — ต้องจัดการ global components

## Implementation Path

### Option A: แก้น้อยที่สุด (Adaptive Crop)

แทน `crop_for(img, x, y, w, h)` ที่ pad คงที่ ให้:

```python
def adaptive_crop_for_cluster(img, own_box, sibling_boxes):
    """Crop ที่ครอบ own + siblings ที่ใกล้"""
    x, y, w, h = own_box
    all_boxes = [(x, y, w, h)]
    
    # เอาเฉพาะ siblings ที่ห่างไม่เกิน 300 px
    for sx, sy, sw, sh in sibling_boxes:
        dist = min(
            abs((sx + sw/2) - (x + w/2)),  # ระยะ center แนวนอน
            abs((sy + sh/2) - (y + h/2)),  # ระยะ center แนวตั้ง
        )
        if dist < 500:
            all_boxes.append((sx, sy, sw, sh))
    
    # หา union bbox
    min_x = min(bx for bx, _, _, _ in all_boxes) - 100
    min_y = min(by for _, by, _, _ in all_boxes) - 100
    max_x = max(bx + bw for bx, _, bw, _ in all_boxes) + 100
    max_y = max(by + bh for _, by, _, bh in all_boxes) + 100
    
    crop = img[max(0, min_y):max_y, max(0, min_x):max_x]
    return crop, max(0, min_x), max(0, min_y)
```

**ผลลัพธ์**: #15 จะ crop ครอบ #14 เต็มตัว → Geodesic ทำงาน

**Trade-off**: Crop ใหญ่ขึ้น แต่ยังเล็กกว่า full page

### Option B: ทำถูกต้องสุด (Full-Page)

Implement pipeline ด้านบนเต็มรูปแบบ

**ผลลัพธ์**: แม่นที่สุด ทุกเคส

**Trade-off**: เขียนใหม่ทั้งหมด

## คำแนะนำ

สำหรับ production ใน `detector.py` / `contour_fitting.py`:

**Phase 1 (quick win)**: Adaptive crop — แก้ไฟล์เดียว (`layout_region.py` หรือ caller ของ smart_balloon)

**Phase 2 (long-term)**: Full-page pipeline — เขียน `smart_balloon_full_page.py` ใหม่ แล้วค่อยแทนที่
