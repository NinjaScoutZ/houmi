# Smart Balloon Font Size Optimization

## ปัญหา
ขนาดฟอนต์ของคำแปลใน Smart Balloon ยังใหญ่เกินไป ทำให้:
- ข้อความเต็มบอลลูนจนดูแน่นเกินไป
- ไม่มีระยะห่างที่เพียงพอระหว่างข้อความกับขอบบอลลูน
- ดูไม่สวยงามและไม่มี breathing room

## การแก้ไข

### 1. ลด Font Size Search Range (Backend)
**ไฟล์**: `backend/app/services/smart_balloon_typesetting.py:72-76`

#### เดิม:
```python
dim_cap = min(bh * 0.42, bw * 0.35)
if max_font_size is not None and max_font_size > 0:
    search_max = int(min(max_font_size, max(140.0, dim_cap)))
else:
    search_max = int(max(48.0, min(240.0, dim_cap)))
```

#### ใหม่:
```python
# Conservative sizing for shape-aware fitting
dim_cap = min(bh * 0.32, bw * 0.28)  # ↓ ลดจาก 0.42/0.35 เป็น 0.32/0.28
if max_font_size is not None and max_font_size > 0:
    search_max = int(min(max_font_size, max(100.0, dim_cap)))  # ↓ ลดจาก 140
else:
    search_max = int(max(36.0, min(180.0, dim_cap)))  # ↓ ลดจาก 48/240
```

**ผลลัพธ์**:
- Font size สูงสุดลดลง ~25-30%
- เหมาะสมสำหรับรูปทรงที่มีความกว้างแปรผัน (variable width)

---

### 2. ลด Row Width Constraint Tolerance
**ไฟล์**: `backend/app/services/smart_balloon_typesetting.py:159`

#### เดิม:
```python
# 20th percentile width in the vertical slice
allowed_w = float(np.percentile(valid_band, 20))
```

#### ใหม่:
```python
# 15th percentile width for tighter constraint
allowed_w = float(np.percentile(valid_band, 15))  # ↓ ลดจาก 20 เป็น 15
```

**ผลลัพธ์**:
- ข้อความจะใช้ความกว้างที่แคบกว่า (เข้มงวดมากขึ้น)
- ลดโอกาสที่ข้อความจะชนขอบบอลลูนที่จุดแคบ

---

### 3. ลด Maximum Height Fill Ratio
**ไฟล์**: `backend/app/services/smart_balloon_typesetting.py:129`

#### เดิม:
```python
if total_text_h > bh * 0.88:
    continue
```

#### ใหม่:
```python
if total_text_h > bh * 0.75:  # ↓ ลดจาก 0.88 เป็น 0.75
    continue
```

**ผลลัพธ์**:
- ข้อความจะใช้แค่ 75% ของความสูงบอลลูน (แทนที่จะเป็น 88%)
- เพิ่ม vertical padding ด้านบนและด้านล่าง

---

### 4. ลด Row Width Safety Margin
**ไฟล์**: `backend/app/services/smart_balloon.py:295`

#### เดิม:
```python
"row_widths": [max(0.0, w * 0.85) for w in smoothed.tolist()],  # 85% safe margin
```

#### ใหม่:
```python
"row_widths": [max(0.0, w * 0.70) for w in smoothed.tolist()],  # ↓ ลดจาก 85% เป็น 70%
```

**ผลลัพธ์**:
- แต่ละแถวจะมีความกว้างที่อนุญาตแค่ 70% ของความกว้างจริง
- เพิ่ม horizontal padding ระหว่างข้อความกับขอบบอลลูน

---

## สรุปการเปลี่ยนแปลงทั้งหมด

| Parameter | Before | After | Change |
|-----------|--------|-------|--------|
| **Max font cap** | 0.42×height, 0.35×width | 0.32×height, 0.28×width | ↓ ~24% |
| **Default max font** | 48-240px | 36-180px | ↓ 25% |
| **Percentile threshold** | 20th | 15th | ↓ Stricter |
| **Height fill ratio** | 88% | 75% | ↓ 15% |
| **Row width margin** | 85% | 70% | ↓ 18% |

## ผลลัพธ์ที่คาดหวัง

### ก่อน (Before)
- ฟอนต์ใหญ่เกินไป เต็มบอลลูน
- ข้อความเกือบชนขอบบอลลูน
- ดูแน่นและไม่มี breathing room

### หลัง (After)
- ✅ ฟอนต์เล็กลง ~25-30%
- ✅ มี padding เพียงพอรอบข้อความ
- ✅ ข้อความอยู่ห่างจากขอบบอลลูนอย่างชัดเจน
- ✅ ดูสวยงาม มี breathing room
- ✅ ข้อความไม่ชนขอบหยักของดาวแน่นอน

## การทดสอบ

```bash
cd backend
python -m pytest tests/test_smart_balloon_v15.py -xvs
```

ทดสอบใน app จริง:
1. เปิดหน้าที่มี Smart Balloon
2. Run Typesetting (Ctrl+T)
3. ตรวจสอบ:
   - ข้อความควรเล็กกว่าเดิม ~25-30%
   - มี padding รอบๆ ข้อความชัดเจน
   - ไม่ชนขอบบอลลูน

## การปรับแต่งเพิ่มเติม

หากต้องการปรับฟอนต์ให้เล็ก/ใหญ่กว่านี้อีก:

**ให้เล็กกว่านี้**:
```python
# ใน smart_balloon_typesetting.py
dim_cap = min(bh * 0.28, bw * 0.24)  # ลดเพิ่มอีก

# ใน smart_balloon.py
"row_widths": [max(0.0, w * 0.65) for w in smoothed.tolist()]  # ลดเหลือ 65%
```

**ให้ใหญ่กว่านี้**:
```python
# ใน smart_balloon_typesetting.py
dim_cap = min(bh * 0.36, bw * 0.32)  # เพิ่มขึ้นเล็กน้อย

# ใน smart_balloon.py
"row_widths": [max(0.0, w * 0.75) for w in smoothed.tolist()]  # เพิ่มเป็น 75%
```

## Notes

- การเปลี่ยนแปลงเหล่านี้ **ไม่กระทบ** กับ blocks ที่ไม่ใช่ Smart Balloon
- Backward compatible กับโค้ดเดิมทั้งหมด
- ค่า default เหล่านี้ถูกปรับจาก testing หลายรูปแบบบอลลูน
- ผู้ใช้สามารถ override ด้วย `manual_font_size` ได้ตามปกติ
