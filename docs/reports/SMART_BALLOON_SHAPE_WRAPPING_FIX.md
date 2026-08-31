# Smart Balloon Shape-Adaptive Text Wrapping Fix

## 🐛 ปัญหาที่พบ

Smart Balloon **ไม่ทำงานตาม shape จริง** ของบอลลูน ทำให้:
- ข้อความไม่ตัดบรรทัดตามรูปร่างของบอลลูน
- บอลลูนรูปดาว (star shape) ควรมีข้อความแบบ Short-Long-Short แต่กลับเป็นแบบ rectangular
- บอลลูนรูปไข่ (oval) ไม่ได้ follow ความโค้งของขอบ
- Selection handles ไม่ตาม contour จริง

## 🔍 Root Cause Analysis

### สาเหตุหลัก: **Data Flow Break**

```
Backend (Smart Balloon Service)
    ↓
  Computes row_width_constraints ✅
    ↓
  Stores in TypesettingSpec.metrics ✅
    ↓
  ❌ MISSING: Sync to block.extra_metadata.smart_balloon
    ↓
Frontend (Canvas.tsx)
    ↓
  Looks for block.extra_metadata.smart_balloon.row_width_constraints
    ↓
  ❌ Not found → Falls back to rectangular wrapping
```

**ปัญหาคือ:** `persist_typesetting_spec()` บันทึก `row_width_constraints` ใน `TypesettingSpec.metrics` แต่ **ไม่ได้ sync กลับไปที่ `block.extra_metadata.smart_balloon`** ซึ่งเป็นที่ที่ Frontend มองหา

### ไฟล์ที่เกี่ยวข้อง

**Backend:**
- `backend/app/services/smart_balloon.py:395-434` - คำนวณ `row_width_constraints`
- `backend/app/services/smart_balloon_typesetting.py:293` - เก็บใน `TypesettingSpec.metrics`
- `backend/app/services/typesetting/service.py:237-293` - **❌ Missing sync**

**Frontend:**
- `frontend/src/components/Canvas.tsx:3123,3447` - อ่านจาก `smart_balloon.row_width_constraints`
- `frontend/src/utils/smartBalloonCanvas.ts:105-163` - Apply shape-adaptive wrapping

---

## ✅ Solution Implemented

### แก้ไข `persist_typesetting_spec()` เพื่อ Sync ข้อมูล

**ไฟล์:** `backend/app/services/typesetting/service.py:291-298`

```python
metadata["typesetting_spec"] = spec_dump

# Sync Smart Balloon row_width_constraints to smart_balloon metadata for frontend access
if isinstance(metrics, dict) and metrics.get("is_smart_balloon"):
    row_width_constraints = metrics.get("row_width_constraints")
    if row_width_constraints is not None and "smart_balloon" in metadata:
        smart_balloon_meta = dict(metadata.get("smart_balloon") or {})
        smart_balloon_meta["row_width_constraints"] = row_width_constraints
        metadata["smart_balloon"] = smart_balloon_meta

block.extra_metadata = metadata
return metadata
```

### วิธีการทำงาน

1. **ตรวจสอบ** ว่า block นี้เป็น Smart Balloon (`is_smart_balloon` in metrics)
2. **ดึง** `row_width_constraints` จาก `TypesettingSpec.metrics`
3. **Sync** กลับไปที่ `block.extra_metadata.smart_balloon.row_width_constraints`
4. Frontend จะได้ข้อมูลผ่าน normal serialization flow

---

## 🎯 ผลลัพธ์ที่คาดหวัง

### ก่อนแก้ไข (Before)
- ❌ ข้อความใช้ความกว้างสม่ำเสมอทุกบรรทัด (rectangular)
- ❌ บอลลูนรูปดาวมีข้อความยาวเต็มจนชนแหลม
- ❌ Selection handles แสดงกรอบสี่เหลี่ยม
- ❌ ข้อความไม่ได้ centered ที่ visual centroid

### หลังแก้ไข (After)
- ✅ **Shape-Adaptive Line Wrapping**: ข้อความตัดบรรทัดตามรูปร่างจริง
  - บอลลูนรูปดาว: Short → Long → Short
  - บอลลูนรูปไข่: Follow ความโค้ง
  - บอลลูนรูปสี่เหลี่ยม: ความกว้างสม่ำเสมอ
- ✅ **Polygon Selection Handles**: Selection border ตามเส้น contour จริง
- ✅ **Centroid Positioning**: ข้อความอยู่ตรงกึ่งกลางมวลสายตา
- ✅ **Proper Padding**: ข้อความห่างจากขอบบอลลูนอย่างปลอดภัย

---

## 🧪 การทดสอบ

### Backend Tests
```bash
cd backend
python -m pytest tests/test_smart_balloon_v15.py -xvs
```

**ผลลัพธ์:** ✅ **12/12 PASSED** (0.79s)

#### New Test Cases Added
1. **`test_persist_spec_syncs_row_width_constraints`**: ✅ PASSED
   - ตรวจสอบว่า `row_width_constraints` ถูก sync จาก `TypesettingSpec.metrics` ไปยัง `block.extra_metadata.smart_balloon`
   - ตรวจสอบ structure และค่าของ constraints

2. **`test_persist_spec_no_sync_for_non_smart_balloon`**: ✅ PASSED
   - ตรวจสอบว่า blocks ที่ไม่ใช่ Smart Balloon ไม่ได้รับผลกระทบ
   - ยืนยัน backward compatibility

### Manual Testing

1. **เปิด app** และโหลดหน้าที่มี Smart Balloon blocks
2. **Run Typesetting** (Ctrl+T หรือผ่าน Pipeline Controls)
3. **ตรวจสอบ:**
   - Selection handles ตาม balloon contour
   - ข้อความตัดบรรทัดตาม shape (star = short-long-short)
   - ข้อความอยู่ตรงกลางบอลลูน
   - ไม่ชนขอบบอลลูน

### ตรวจสอบ Data Flow

```python
# ใน Python console หรือ debug
block = db.query(TextBlock).filter(TextBlock.id == "some_smart_balloon_id").first()
smart_balloon = block.extra_metadata.get("smart_balloon")
print(smart_balloon.get("row_width_constraints"))
# ✅ Should return: {"enabled": True, "row_widths": [...], "height": ...}
```

---

## 📊 Technical Details

### Row Width Constraints Structure

```typescript
{
  "enabled": boolean,
  "row_widths": number[],  // Width in pixels for each vertical row
  "height": number         // Total height in pixels
}
```

**Example** (Star Balloon):
```json
{
  "enabled": true,
  "row_widths": [
    45.2,   // Top narrow point
    68.5,
    92.3,   
    120.8,  // Wide middle section
    98.6,
    71.4,
    48.9    // Bottom narrow point
  ],
  "height": 180
}
```

### Frontend Usage

```typescript
// Canvas.tsx automatically applies if row_width_constraints exists
if (sbMeta.row_width_constraints?.enabled && sbMeta.safe_bbox) {
  applyShapeAdaptiveWrapping(
    textbox,
    sbMeta.row_width_constraints,
    scaleFactor,
    sbMeta.safe_bbox
  );
}
```

---

## 🔄 Backward Compatibility

- ✅ **Blocks ที่ไม่ใช่ Smart Balloon** ไม่ได้รับผลกระทบ
- ✅ **Smart Balloons เดิม** จะได้ constraints ใหม่เมื่อ re-typeset
- ✅ **Fallback behavior** ยังคงทำงาน (rectangular wrapping) ถ้าข้อมูลไม่มี
- ✅ **API contract** ไม่เปลี่ยน - เป็นการ sync internal data เท่านั้น

---

## 🚀 Deployment Checklist

- [x] Root cause analysis completed
- [x] Fix implemented in `persist_typesetting_spec()`
- [x] Backend tests passing (12/12) ✅
- [x] New tests added for row_width_constraints sync
- [x] Backward compatibility verified
- [x] No breaking changes to API
- [x] Documentation updated
- [ ] Manual testing with real manga images (recommended)
- [ ] Performance impact assessment (minimal - just data copy)

---

## 📝 Files Modified

### Backend
1. **`backend/app/services/typesetting/service.py`** (line 291-298)
   - Added sync logic to copy `row_width_constraints` from `TypesettingSpec.metrics` to `block.extra_metadata.smart_balloon`
   
2. **`backend/tests/test_smart_balloon_v15.py`** (line 119-168)
   - Added import for `persist_typesetting_spec` and `TypesettingSpec`
   - Added new test class `TestSmartBalloonRowWidthSync` with 2 test cases
   - Total tests increased from 10 to 12

### Frontend
- ไม่มีการแก้ไข (โค้ดเดิมทำงานถูกต้องแล้ว - เพียงแค่ขาดข้อมูล)

---

## 💡 Related Features

การแก้ไขนี้ทำให้ features ต่อไปนี้ทำงานได้เต็มรูปแบบ:

1. **Shape-Adaptive Text Wrapping** - ข้อความปรับตามรูปร่างบอลลูน
2. **Polygon Selection Handles** - Selection border ตาม contour
3. **Visual Centroid Positioning** - จัดข้อความที่กึ่งกลางมวลสายตา
4. **Smart Balloon V15 Pipeline** - ระบบตรวจจับและจำแนก archetypes

---

## 🎉 สรุป

การแก้ไขนี้แก้ปัญหาการขาดการ sync ข้อมูล `row_width_constraints` จาก backend ไปยัง frontend โดย:

1. **เพิ่ม sync logic** ใน `persist_typesetting_spec()`
2. **Copy data** จาก `TypesettingSpec.metrics` ไปยัง `block.extra_metadata.smart_balloon`
3. **Frontend อ่านข้อมูลได้** ผ่าน standard serialization flow
4. **Shape-adaptive wrapping ทำงาน** ตามที่ออกแบบไว้

ผลลัพธ์: Smart Balloon ตัดบรรทัดข้อความตามรูปร่างจริงของบอลลูนอย่างถูกต้อง ✨
