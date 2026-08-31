# 🚀 Inpaint Strategy & GPU Health Check Upgrade

## สรุปการอัปเกรด (2026-08-18)

ระบบ Houmi Studio ได้รับการอัปเกรดครั้งใหญ่ในส่วน **Inpainting Architecture** และ **System Health Monitoring** เพื่อรองรับผู้ใช้ที่มีสเปค Hardware หลากหลาย (CPU-only, GPU แรง, GPU อ่อน)

---

## 🎯 สิ่งที่เพิ่มเข้ามา

### 1. **Inpaint Strategy System** (ระบบเลือกกลยุทธ์การคลีน)

เพิ่ม 3 โหมดให้ผู้ใช้เลือกได้ตาม Hardware:

| โหมด | วิธีการ | ความเร็ว | เสถียรภาพ | เหมาะสำหรับ |
|------|---------|----------|-----------|-------------|
| **Region-Based** (default) | รวมบอลลูนใกล้กันเป็น regions | ⚡⚡⚡ | ⭐⭐⭐ | GPU ทั่วไป (GTX 1060+) |
| **Per-Block** | ทีละบอลลูนแยกกัน | ⚡⚡ | ⭐⭐⭐⭐⭐ | CPU-only, GPU อ่อน |
| **Parallel** | หลาย regions พร้อมกัน | ⚡⚡⚡⚡⚡ | ⭐⭐⭐ | GPU แรง (RTX 3060+) |

#### **Backend Changes:**

1. **`backend/app/services/inpainter.py`**
   - เพิ่มฟังก์ชัน `_per_block_inpaint()` สำหรับโหมด per-block
   - แก้ไข `clean_page_text()` ให้รองรับ strategy routing:
     ```python
     strategy = project_settings.get("inpaint_strategy", "region")
     if strategy == "per_block":
         return _per_block_inpaint(...)
     elif strategy == "parallel":
         return _parallel_inpaint(...)
     else:
         return _region_based_inpaint(...)
     ```

2. **`backend/app/services/performance_presets.py`**
   - เพิ่ม `inpaint_strategy` เข้า Performance Presets:
     ```python
     "ultra_fast": {"inpaint_strategy": "per_block"}    # CPU
     "balanced": {"inpaint_strategy": "region"}         # GPU ทั่วไป
     "high_quality": {"inpaint_strategy": "parallel"}   # GPU แรง
     ```

3. **`backend/app/services/project_serializer.py`**
   - เพิ่ม `inpaint_strategy` เข้า `compute_clean_fingerprint()`:
     ```python
     fingerprint_data["inpaint_strategy"] = settings.get("inpaint_strategy", "region")
     ```
   - เมื่อเปลี่ยน strategy → cache invalidate → re-clean อัตโนมัติ

#### **Frontend Changes:**

4. **`frontend/src/components/SettingsModal.tsx`**
   - เพิ่ม **Inpaint Strategy Dropdown** ใน Pipeline Settings:
     ```tsx
     <select value={currentInpaintStrategy} onChange={...}>
       <option value="region">🎯 Region-Based (เร็ว - รวมบอลลูนใกล้กัน)</option>
       <option value="per_block">🔷 Per-Block (เสถียร - ทีละบอลลูน)</option>
       <option value="parallel">⚡ Parallel (เร็วมาก - หลายบอลลูนพร้อมกัน)</option>
     </select>
     ```

---

### 2. **GPU Inpaint Server Health Check** (ตรวจสอบสถานะ GPU Server)

เพิ่มระบบตรวจสอบ **GPU Inpaint Server** แบบ Real-time

#### **Backend Changes:**

5. **`backend/app/routes/diagnostics.py`**
   - แก้ไข `/api/diagnostics/health` endpoint:
     - ตรวจสอบ **Custom GPU URL** จาก settings ก่อน (พอร์ตที่ผู้ใช้ตั้งเอง)
     - ถ้าไม่มี → ตรวจสอบ Local Ports (2328, 2322, 2335)
     - ถ้าไม่เจอ → ตรวจสอบ ONNX fallback
     - ถ้าไม่มีอะไรเลย → รายงาน "Telea-only" (OpenCV fallback)
   
   - Response Structure:
     ```json
     {
       "status": "online",
       "checks": {
         "inpaint": {
           "status": "ok",
           "server_type": "custom_gpu" | "local_gpu" | "onnx_local" | "telea_only",
           "message": "Custom GPU server online at http://...",
           "latency_ms": 45.2
         }
       }
     }
     ```

#### **Frontend Changes:**

6. **`frontend/src/components/SettingsModal.tsx`**
   - อัปเดต Engine Health UI ให้แสดง GPU Server Status:
     - 🟢 **CUSTOM GPU** / **LOCAL GPU** (latency_ms) → GPU Server พร้อม
     - ⚠️ **ONNX FALLBACK** → ใช้ ONNX CPU
     - 🔶 **TELEA ONLY** → ใช้ OpenCV Telea (ช้าที่สุด)
     - 🔴 **ERROR** → มีปัญหา
   
   - แสดง `server_type` และ `message` เพิ่มเติมเพื่อให้ผู้ใช้รู้ว่ากำลังใช้อะไรอยู่

---

## 📊 ตัวอย่างการทำงาน

### **หน้าที่มี 10 บอลลูน:**

#### **Region-Based** (default):
```
[Balloon 1, 2, 3] → Region A
[Balloon 4, 5]    → Region B
[Balloon 6, 7, 8] → Region C
[Balloon 9, 10]   → Region D

Total Inpaint Calls: 4 ครั้ง
```

#### **Per-Block**:
```
Balloon 1 → Inpaint
Balloon 2 → Inpaint
...
Balloon 10 → Inpaint

Total Inpaint Calls: 10 ครั้ง (แต่เสถียร)
```

#### **Parallel**:
```
Worker 1: [Balloon 1, 2, 3] (พร้อมกัน)
Worker 2: [Balloon 4, 5]    (พร้อมกัน)
Worker 3: [Balloon 6, 7, 8] (พร้อมกัน)
Worker 4: [Balloon 9, 10]   (พร้อมกัน)

Total Wall-Clock Time: เร็วที่สุด (ขนาน)
```

---

## 🎛️ การใช้งาน

### **สำหรับผู้ใช้ CPU-only / GPU อ่อน:**

1. เปิด **Settings** (`Ctrl+,`)
2. ไปที่ **Pipeline Settings**
3. เลือก **Inpaint Strategy** = **🔷 Per-Block (เสถียร - ทีละบอลลูน)**
4. กด **Clean** หน้าใหม่

### **สำหรับผู้ใช้ GPU แรง (RTX 3060+):**

1. เปิด **Settings**
2. เลือก **Inpaint Strategy** = **⚡ Parallel (เร็วมาก - หลายบอลลูนพร้อมกัน)**
3. กด **Clean** หน้าใหม่

### **ตรวจสอบ GPU Server Status:**

1. เปิด **Settings**
2. ไปที่ **Engine Health** tab
3. ดูส่วน **"2. GPU Inpaint Server"**:
   - 🟢 **CUSTOM GPU / LOCAL GPU** → GPU พร้อมใช้งาน
   - ⚠️ **ONNX FALLBACK** → กำลังใช้ CPU ONNX
   - 🔶 **TELEA ONLY** → กำลังใช้ OpenCV (ควรติดตั้ง GPU Server)

---

## 🔧 Technical Details

### **Cache Invalidation:**

เมื่อเปลี่ยน `inpaint_strategy`, ระบบจะ:
1. คำนวณ `compute_clean_fingerprint()` ใหม่
2. ตรวจพบว่า fingerprint เปลี่ยน
3. ทำให้ cache invalidate
4. Re-clean หน้าใหม่ทั้งหมด (ไม่ใช้ผลลัพธ์เก่า)

### **Performance Preset Auto-Apply:**

เมื่อผู้ใช้เลือก Performance Preset:
- **Ultra Fast** → `inpaint_strategy = "per_block"`
- **Balanced** → `inpaint_strategy = "region"`
- **High Quality** → `inpaint_strategy = "parallel"`

### **GPU Server Detection Priority:**

1. **Custom URL** (จาก AI Provider Settings) → ตรวจสอบก่อน
2. **Local Ports** (2328, 2322, 2335) → ตรวจสอบถ้าไม่มี Custom URL
3. **ONNX Fallback** (lama_manga.onnx) → ถ้าไม่เจอ GPU Server
4. **Telea Fallback** (OpenCV) → ถ้าไม่มีอะไรเลย

---

## 📝 Breaking Changes

**ไม่มี Breaking Changes!**

- Default strategy = `region` (เหมือนเดิม)
- ผู้ใช้ที่ไม่ได้เลือก strategy จะยังใช้ region-based เหมือนเดิม
- สามารถ opt-in ใช้ per-block หรือ parallel ได้ตามต้องการ

---

## 🚀 Next Steps (Future Work)

1. **Auto-Detect Strategy** จาก Hardware (ตรวจสอบ GPU แล้วแนะนำ strategy)
2. **Adaptive Strategy** (เริ่มจาก parallel → fallback เป็น per-block ถ้า GPU OOM)
3. **Per-Page Strategy Override** (เลือก strategy ต่างกันในแต่ละหน้า)

---

## 📚 เอกสารที่เกี่ยวข้อง

- `backend/app/services/inpainter.py` → Core inpainting logic
- `backend/app/services/performance_presets.py` → Performance preset configurations
- `backend/app/services/project_serializer.py` → Cache fingerprint computation
- `frontend/src/components/SettingsModal.tsx` → Settings UI
- `backend/app/routes/diagnostics.py` → Health check API

---

**เวอร์ชัน:** v1.0.1-alpha (2026-08-18)  
**ผู้พัฒนา:** Houmi Studio Team  
**สถานะ:** ✅ Stable - Ready for Production
