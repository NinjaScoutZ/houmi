# Inpaint Strategy Feature

## Overview
เพิ่มตัวเลือกให้ผู้ใช้สามารถเลือก **กลยุทธ์การส่งรูปไปคลีน** ได้ 3 แบบ เพื่อรองรับทั้ง GPU และ CPU ทุกระดับ

## Inpaint Strategies

### 1. **Region-Based** (เร็ว - รวมบอลลูนใกล้กัน)
- **ใช้เมื่อ**: มี GPU ทั่วไป (DirectML, CUDA)
- **วิธีการ**: รวม text regions ที่อยู่ใกล้กันเป็น bounding boxes ขนาดใหญ่ แล้วส่งไปคลีน
- **ข้อดี**: เร็วกว่า per-block เพราะส่งน้อยครั้ง, ใช้ context ของบอลลูนข้างเคียง
- **ข้อเสี**: regions ใหญ่อาจช้าบน CPU อ่อน

**ตัวอย่างการทำงาน:**
```
Page with 10 balloons → Merge into 3-4 large regions → Inpaint 3-4 times → Composite back
```

### 2. **Per-Block** (เสถียร - ทีละบอลลูน)
- **ใช้เมื่อ**: CPU-only หรือ GPU อ่อน หรือต้องการความเสถียรสูงสุด
- **วิธีการ**: ส่งทีละ text block (บอลลูน) แยกกันอิสระ ไม่รวมกัน
- **ข้อดี**: 
  - เสถียรที่สุด - ไม่มีปัญหา memory overflow
  - รองรับ CPU อ่อน
  - แต่ละบอลลูนใช้ context เฉพาะตัว (ไม่กินพื้นที่ข้างเคียง)
- **ข้อเสี**: ช้ากว่า region-based นิดหน่อย (แต่เสถียรกว่า)

**ตัวอย่างการทำงาน:**
```
Page with 10 balloons → Inpaint block #1 → #2 → #3 → ... → #10 → Composite back
```

### 3. **Parallel** (เร็วมาก - หลายบอลลูนพร้อมกัน)
- **ใช้เมื่อ**: มี GPU แรง (CUDA) หรือ CPU multi-core แรงมาก
- **วิธีการ**: ใช้ `parallel_inpaint.py` ส่งหลาย regions พร้อมกัน (ThreadPoolExecutor)
- **ข้อดี**: เร็วที่สุด - ใช้ multi-core เต็มประสิทธิภาพ
- **ข้อเสี**: ใช้ RAM/VRAM มาก, อาจช้าบน CPU อ่อน

**ตัวอย่างการทำงาน:**
```
Page with 10 balloons → Split to 4 workers → Worker 1-4 inpaint 2-3 regions each (parallel) → Composite back
```

---

## Implementation Details

### Backend Changes

#### 1. New Function: `_per_block_inpaint()` 
**Location:** `backend/app/services/inpainter.py`

```python
def _per_block_inpaint(
    img: np.ndarray,
    mask: np.ndarray,
    text_blocks: list[Any],
    page_width: int,
    page_height: int,
    inpaint_service: Any,
    settings: dict,
    *,
    context_padding: int = 48,
    cancel_check: Any = None,
) -> np.ndarray:
    """ส่งทีละ text block แยกกัน (เสถียรที่สุดสำหรับ CPU/GPU ทุกระดับ)"""
```

#### 2. Modified: `clean_page_text()` Strategy Router
**Location:** `backend/app/services/inpainter.py:2194-2221`

```python
inpaint_strategy = project_settings.get("inpaint_strategy", "region")

if inpaint_strategy == "per_block":
    img_cleaned = _per_block_inpaint(...)
elif inpaint_strategy == "parallel":
    img_cleaned = inpaint_regions_parallel(...)
else:  # Default: "region"
    img_cleaned = _region_based_inpaint(...)
```

#### 3. Updated Performance Presets
**Location:** `backend/app/services/performance_presets.py`

```python
"ultra_fast": {
    "inpaint_strategy": "per_block",  # Stable for low-end CPUs
    ...
},
"balanced": {
    "inpaint_strategy": "region",  # Good balance
    ...
},
"high_quality": {
    "inpaint_strategy": "parallel",  # Fastest with GPU
    ...
}
```

#### 4. Updated Clean Fingerprint
Added `inpaint_strategy` to cache invalidation keys so changing strategy triggers re-clean.

---

### Frontend Changes

#### 1. New Setting in SettingsModal
**Location:** `frontend/src/components/SettingsModal.tsx:1080-1104`

```tsx
<select
  value={currentInpaintStrategy}
  onChange={(e) => handleUpdateSetting({ inpaint_strategy: e.target.value })}
>
  <option value="region">🎯 Region-Based (เร็ว - รวมบอลลูนใกล้กัน GPU)</option>
  <option value="per_block">🔷 Per-Block (เสถียร - ทีละบอลลูน CPU/GPU)</option>
  <option value="parallel">⚡ Parallel (เร็วมาก - หลายบอลลูนพร้อมกัน GPU)</option>
</select>
```

---

## Usage Guide

### For Users

1. **เปิด Settings Modal** (`Ctrl+,` หรือคลิก ⚙️ Settings)
2. ไปที่ **Pipeline Settings** → **Default Inpainter Engine**
3. เลือก **Inpaint Strategy** ตามสเปคคอม:
   - **CPU อ่อน**: เลือก **Per-Block** (เสถียรที่สุด)
   - **GPU ทั่วไป**: เลือก **Region-Based** (เร็วกว่า)
   - **GPU แรง + Multi-core**: เลือก **Parallel** (เร็วที่สุด)

### Performance Presets (Auto-Apply)

เมื่อเลือก Performance Preset, Inpaint Strategy จะถูกตั้งอัตโนมัติ:
- **Ultra Fast** → `per_block` (เหมาะ CPU)
- **Balanced** → `region` (เหมาะ GPU ทั่วไป)
- **High Quality** → `parallel` (เหมาะ GPU แรง)

---

## Testing

### Manual Test
1. สร้างโปรเจกต์ใหม่
2. เพิ่มหน้ามังงะที่มี 10+ บอลลูน
3. ทดสอบทั้ง 3 strategies:
   - **Region-Based**: ควรเร็วกว่า per-block นิดหน่อย
   - **Per-Block**: ควรเสถียร ไม่ crash
   - **Parallel**: ควรเร็วที่สุด (ถ้ามี GPU)

### Backend Validation
```bash
cd backend && python -c "
from app.services.inpainter import _per_block_inpaint
import inspect
print(inspect.signature(_per_block_inpaint))
"
```

---

## Rollback Plan

หากพบปัญหา สามารถ revert โดย:
1. ตั้ง `inpaint_strategy` เป็น `"region"` ใน project settings
2. หรือลบ key `inpaint_strategy` ออก (จะใช้ default = `"region"`)

---

## Future Enhancements

1. **Auto-Strategy Selection**: ตรวจจับ hardware แล้วเลือก strategy ที่เหมาะสมอัตโนมัติ
2. **Hybrid Strategy**: ใช้ parallel สำหรับบอลลูนเล็ก, per-block สำหรับบอลลูนใหญ่
3. **Progress Reporting**: แสดง progress bar ละเอียดขึ้นสำหรับแต่ละ strategy

---

## Changelog

### [v1.0.1] - 2026-08-18
#### Added
- ✨ เพิ่ม Inpaint Strategy selection (region / per_block / parallel)
- ✨ เพิ่มฟังก์ชัน `_per_block_inpaint()` สำหรับ CPU-friendly mode
- ✨ อัปเดต Performance Presets ให้มี `inpaint_strategy` auto-apply
- 🎨 เพิ่ม UI dropdown ใน Settings Modal → Pipeline Settings

#### Changed
- ♻️ Refactor `clean_page_text()` ให้รองรับ strategy routing
- 📝 เพิ่ม `inpaint_strategy` เข้า `compute_clean_fingerprint()` cache

#### Fixed
- 🐛 แก้ปัญหาการรวม regions ขนาดใหญ่ทำให้ช้าบน CPU อ่อน

---

## Credits
- **Author**: Claude (Opus 5)
- **Request**: ผู้ใช้ต้องการระบบแบบ "ส่งไปทีละบอลลูน แล้วคลีน จากนั้นยิงกลับมาแก้ไขภาพ"
- **Date**: 2026-08-18
