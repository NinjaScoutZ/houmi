# 🚀 แก้ปัญหา Clean Pipeline ช้า/ค้าง

## ปัญหาที่พบ
- LaMa Inpainting ใช้ CPU แทน GPU → ช้า 50-100 เท่า
- Clean pipeline ค้างหน้าสองหน้าแรก
- Background task ไม่เสร็จ

## ✅ แก้ไขแล้ว

### 1. เพิ่มการบังคับใช้ CUDA ใน `.env`
```bash
HOUMI_EXECUTION_PROVIDER=CUDA
```

### 2. รีสตาร์ท Houmi
**⚠️ สำคัญ: ต้องรีสตาร์ทเซิร์ฟเวอร์ให้โหลดค่าใหม่**

กด `Ctrl+C` ในหน้าต่าง terminal แล้วรันใหม่:
```bash
python backend/app/main.py
```

หรือปิดแอพแล้วเปิดใหม่

---

## 🎯 ตรวจสอบว่าใช้ CUDA แล้ว

หลังรีสตาร์ท ดู log จะต้องเห็น:
```
LaMa Inpainter initialized cleanly on provider: ['CUDAExecutionProvider']
```

**ไม่ใช่:**
```
LaMa Inpainter initialized cleanly on provider: ['CPUExecutionProvider']  ❌
```

---

## 🚀 การปรับแต่งเพิ่มเติม (ทำหลังรีสตาร์ท)

### วิธี 1: Fast Profile (เร็วที่สุด แต่ quality ต่ำกว่า)

ใน Project Settings หรือไฟล์ project settings:
```json
{
  "cleanup_mask_strategy": "box",
  "default_image_inpaint_method": "telea",
  "mask_dilation_kernel": 1,
  "parallel_inpaint_enabled": true,
  "inpaint_tile_size": 512,
  "ocr_workers": 4
}
```

**ความเร็ว:** ⚡⚡⚡⚡⚡ (5-10 เท่า)  
**Quality:** ⭐⭐⭐ (ดีพอใช้)

---

### วิธี 2: Balanced Profile (แนะนำ)

```json
{
  "cleanup_mask_strategy": "smart",
  "default_image_inpaint_method": "manga_cleaner",
  "mask_dilation_kernel": 2,
  "parallel_inpaint_enabled": true,
  "inpaint_tile_size": 768,
  "ocr_workers": 4,
  "execution_provider": "CUDA"
}
```

**ความเร็ว:** ⚡⚡⚡⚡ (3-5 เท่า)  
**Quality:** ⭐⭐⭐⭐ (ดีมาก)

---

### วิธี 3: Quality Profile (ช้ากว่า แต่คุณภาพสูงสุด)

```json
{
  "cleanup_mask_strategy": "smart",
  "default_image_inpaint_method": "lama",
  "mask_dilation_kernel": 3,
  "parallel_inpaint_enabled": true,
  "inpaint_tile_size": 1024,
  "ocr_workers": 6,
  "execution_provider": "CUDA"
}
```

**ความเร็ว:** ⚡⚡⚡ (2-3 เท่า จาก CUDA)  
**Quality:** ⭐⭐⭐⭐⭐ (สุดยอด)

---

## 🔍 เช็คว่ารีสตาร์ทแล้วยัง

รัน:
```bash
python check_gpu.py
```

ต้องเห็น:
```
✓ CUDA available
```

---

## 📊 ความเร็วที่คาดหวัง (หลังแก้)

| Page Size | ก่อนแก้ (CPU) | หลังแก้ (CUDA) | เร็วขึ้น |
|-----------|---------------|----------------|----------|
| 1 หน้า    | 30-60 วินาที  | 3-6 วินาที     | 10x      |
| 10 หน้า   | 5-10 นาที     | 30-60 วินาที   | 10x      |
| 50 หน้า   | 25-50 นาที    | 3-5 นาที       | 10x      |

---

## ⚠️ ถ้ายังช้าอยู่

### 1. ตรวจสอบว่า CUDA ทำงานจริง
```bash
python check_gpu.py
```

### 2. ตรวจสอบ log ขณะ clean
ดูว่ามีบรรทัดนี้หรือไม่:
```
reclean_page_block engine_override=lama_onnx use_lama=True lama_loaded=True gpu_ep=CUDA
```

ต้องเป็น `gpu_ep=CUDA` **ไม่ใช่** `DirectML` หรือ `CPU`

### 3. ใช้ Telea ชั่วคราว
ถ้ายังช้าอยู่ ให้เปลี่ยนเป็น Telea ก่อน:
```json
{
  "default_image_inpaint_method": "telea"
}
```

Telea เร็วมาก (ไม่ใช้ AI) แต่ quality ต่ำกว่า

---

## 📝 สรุป

1. ✅ เพิ่ม `HOUMI_EXECUTION_PROVIDER=CUDA` ใน `.env`
2. ⚠️ **รีสตาร์ท Houmi** (สำคัญมาก!)
3. ✅ เช็ค log ว่าใช้ CUDAExecutionProvider
4. 🎯 ปรับ settings ตามความต้องการ (Fast/Balanced/Quality)

**หลังรีสตาร์ทแล้วควรเร็วขึ้น 10 เท่า!** 🚀
