# 🔄 วิธีรันโปรเจกต์ 112 ใหม่พร้อม Smart Balloon

## 📊 สถานะปัจจุบัน

**โปรเจกต์**: `E:\Chapter Download\Kuaikanmanhua\ดาว\112 [stitched]`

- ✅ มีรูปภาพต้นฉบับ: 7 หน้า
- ✅ มีคำแปลภาษาไทย: 69 blocks
- ❌ **ยังไม่มี Smart Balloon metadata**
- ❌ ยังไม่มี bboxes, masks, clean images

## 🎯 เป้าหมาย

รัน backend pipeline ใหม่เพื่อ:
1. Detect text bounding boxes
2. Generate masks และ clean images
3. **Detect Smart Balloons** (contour, safe_bbox, archetype)
4. **Run Smart Balloon typesetting** กับคำแปลไทย
5. ทดสอบว่าการแก้ไขที่ทำ (93px font, 3-line wrapping) ทำงานได้ดีกับภาษาไทย

## 🚀 วิธีการ

### Option 1: ใช้ Frontend UI (แนะนำ)

```bash
# 1. Start backend
cd E:/houmi/backend
python -m uvicorn app.main:app --reload

# 2. Start frontend (terminal ใหม่)
cd E:/houmi/frontend
npm run dev

# 3. เปิดเบราว์เซอร์ไปที่ http://localhost:5173
# 4. Load โปรเจกต์ 112
# 5. กด "Run Full Pipeline" หรือ "Re-detect"
# 6. รอให้ Smart Balloon detection เสร็จ
```

### Option 2: ใช้ Backend API

```bash
# ส่ง request ไปที่ backend (ต้อง start backend server ก่อน)
curl -X POST http://localhost:8000/api/pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "project_path": "E:/Chapter Download/Kuaikanmanhua/ดาว/112 [stitched]",
    "enable_smart_balloon": true,
    "language": "th"
  }'
```

### Option 3: Python Script

```python
# E:/houmi/backend/run_project_112.py
import sys
sys.path.append('E:/houmi/backend')

from app.services.pipeline import run_full_pipeline
from pathlib import Path

project_path = Path(r"E:\Chapter Download\Kuaikanmanhua\ดาว\112 [stitched]")
run_full_pipeline(str(project_path), enable_smart_balloon=True)
```

## ✅ หลังรัน Pipeline จะได้

### 1. Smart Balloon Metadata ใน project.json
```json
{
  "extra_metadata": {
    "smart_balloon": {
      "archetype": "SMOOTH_OVAL",
      "contour_points": [[x1,y1], [x2,y2], ...],
      "safe_bbox": {
        "x": 123, "y": 456,
        "width": 717, "height": 530
      },
      "row_width_constraints": {
        "enabled": true,
        "row_widths": [450.2, 611.1, 717.8, ...],
        "height": 530
      }
    }
  }
}
```

### 2. Thai Text Typesetting
- ขนาดฟอนต์ปรับตามรูปทรง Smart Balloon
- ข้อความแบ่งเป็นหลายบรรทัด (shape-adaptive wrapping)
- บรรทัดสั้น-ยาว-สั้น (short-long-short) ตามทรงบอลลูน

### 3. ไฟล์ที่สร้างขึ้น
- `masks/*.png` - mask images
- `clean/*.png` - cleaned images
- `previews/*.png` - preview images with typesetting

## 🔍 ตรวจสอบผลลัพธ์

```python
# ตรวจสอบว่า Smart Balloon ทำงานกับภาษาไทยหรือไม่
cd E:/houmi
python -c "
import json
with open('E:/Chapter Download/Kuaikanmanhua/ดาว/112 [stitched]/project.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    
sb_count = 0
thai_sb_count = 0

for page in data['pages']:
    for block in page['text_blocks']:
        sb = block.get('extra_metadata', {}).get('smart_balloon')
        if sb:
            sb_count += 1
            if block.get('translation'):
                thai_sb_count += 1
                
print(f'Smart Balloons: {sb_count}')
print(f'Thai text with Smart Balloon: {thai_sb_count}')
"
```

## 📊 ผลที่คาดหวัง

สำหรับ balloon ที่เป็นข้อความ **"ถูกสลายไปแบบนี้เนี่ยนะ??"** (เหมือนภาพที่แก้ไข):

**BEFORE (ถ้ายังใช้ constraint เดิม):**
- Font size: 130px
- Lines: 1 บรรทัดยาว
- ปัญหา: ข้อความชนขอบบอลลูน

**AFTER (ใช้ constraint ที่แก้แล้ว):**
- Font size: ~93px (ปรับตามขนาดบอลลูน)
- Lines: 2-3 บรรทัด
- ผลลัพธ์: ข้อความอยู่ในบอลลูนสวยงาม มี breathing room

## 🎨 Bonus: ดูสี Archetype

หลังรัน pipeline แล้ว บอลลูนจะถูกจัดประเภท:
- 💬 **SMOOTH_OVAL** (สีส้ม) - ทรงไข่เรียบ
- ⚡ **ANGULAR** (สีเขียว) - มุมแหลม
- 💥 **SPIKY_FUZZY** (สีม่วง) - หยักแหลม
- 🔲 **RECTANGULAR** (สีฟ้า) - สี่เหลี่ยม

Frontend จะแสดงสีตาม archetype โดยอัตโนมัติ!

---

**หมายเหตุ**: การแก้ไขที่เราทำไว้ใน `backend/app/services/smart_balloon_typesetting.py` จะทำงานทันทีเมื่อรัน pipeline ใหม่ ไม่ต้องแก้อะไรเพิ่ม!
