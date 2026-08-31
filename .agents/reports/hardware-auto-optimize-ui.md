# Hardware Auto-Optimize UI Feature

## สรุปการเพิ่มฟีเจอร์

เพิ่มปุ่ม **Auto-Optimize Hardware** ใน UI Settings Modal (Performance Category) เพื่อให้ผู้ใช้กดปุ่มเดียวเพื่อตรวจจับฮาร์ดแวร์และปรับแต่งการตั้งค่าให้เหมาะสมอัตโนมัติ

---

## 🎯 ฟีเจอร์ที่เพิ่ม

### 1. **UI Component ใน Settings Modal**

ตำแหน่ง: `frontend/src/components/SettingsModal.tsx` → Performance Category

#### หน้าตา UI:
- **Section Header**: "Hardware Auto-Optimization" พร้อมไอคอน 🚀
- **Description**: อธิบายว่าระบบจะตรวจจับ GPU/CPU แล้วปรับแต่ง Parallel Inpainting, AI Detection, OCR
- **ปุ่ม**: "⚡ Auto-Optimize Hardware" (สีเหลือง-ส้ม gradient)
- **Loading State**: แสดง spinner และข้อความ "Optimizing..." ขณะทำงาน
- **Hardware Report**: แสดงผลลัพธ์หลังการ optimize:
  - Execution Provider (CUDA/DirectML/CPU)
  - CPU Cores
  - Optimal Threads
  - GPU Name (ถ้ามี)
  - Acceleration Type (ถ้ามี)

---

## 🔧 การทำงาน

### Flow:
1. ผู้ใช้เปิด Settings → Performance Category
2. กดปุ่ม "Auto-Optimize Hardware"
3. Frontend เรียก `POST /api/diagnostics/auto-optimize`
4. Backend:
   - ตรวจจับ GPU (NVIDIA/AMD/Intel)
   - นับ CPU cores
   - คำนวณ optimal thread count
   - เลือก execution provider ที่ดีที่สุด (CUDA > DirectML > CPU)
   - บันทึกการตั้งค่าลง `backend/ai_provider_settings.json`
5. Frontend แสดงผลลัพธ์ใน UI พร้อม alert message

---

## 📊 Hardware Report Fields

```typescript
{
  optimal_provider: string,       // "CUDA" | "DirectML" | "CPU"
  execution_provider: string,     // สำรอง fallback
  cpu_cores: number,              // จำนวน CPU cores
  optimal_thread_count: number,  // จำนวน threads ที่แนะนำ
  gpu_name: string | null,        // ชื่อ GPU (ถ้ามี)
  acceleration_type: string,      // "NVIDIA CUDA" | "DirectML" | "CPU"
}
```

---

## 🎨 Design

- **สี**: Yellow-Orange gradient (เข้ากับ theme ของ Houmi)
- **Typography**: ฟอนต์ bold uppercase สำหรับปุ่ม
- **Border**: Yellow glow เพื่อดึงความสนใจ
- **Animation**: Spinner ขณะ loading
- **Responsive**: ใช้ flexbox และ grid สำหรับ hardware report

---

## ✅ Testing

### Manual Test:
1. เปิด Houmi Desktop App
2. เปิด Settings (⚙️)
3. ไปที่ "Performance & Hardware" category
4. กดปุ่ม "⚡ Auto-Optimize Hardware"
5. รอ 1-2 วินาที
6. ดู alert message แจ้งผลสำเร็จ
7. เช็คว่า Hardware Report แสดงข้อมูลถูกต้อง

### Expected Results:
- ✅ ปุ่มแสดง loading state ขณะทำงาน
- ✅ Alert แสดงข้อความภาษาไทย (เช่น "ปรับแต่งระบบเรียบร้อยแล้ว!")
- ✅ Hardware Report แสดงข้อมูล CPU/GPU ถูกต้อง
- ✅ ไฟล์ `backend/ai_provider_settings.json` ถูกอัพเดท

---

## 📁 ไฟล์ที่แก้ไข

1. **`frontend/src/components/SettingsModal.tsx`**:
   - เพิ่ม `hardwareReport` state
   - เพิ่ม `handleAutoOptimize()` function
   - เพิ่ม UI section ใน Performance category
   - เพิ่ม search keywords: "Auto Optimize GPU CPU Parallel Inpaint"

2. **Backend** (ไม่ต้องแก้):
   - API endpoint `/api/diagnostics/auto-optimize` มีอยู่แล้ว
   - ดูรายละเอียดใน `backend/app/routes/diagnostics.py:598-642`

---

## 🚀 Benefits

1. **UX ดีขึ้น**: ผู้ใช้ไม่ต้องตั้งค่า GPU/CPU เอง
2. **Performance**: ระบบจะใช้ hardware ได้เต็มประสิทธิภาพ
3. **Accessibility**: มือใหม่สามารถ optimize ได้โดยไม่ต้องมีความรู้เชิง technical
4. **Transparency**: แสดงผลลัพธ์ชัดเจนว่าระบบตรวจจับอะไรได้บ้าง

---

## 🎉 สถานะ

✅ **เสร็จสมบูรณ์** - Frontend build สำเร็จ, พร้อมใช้งาน
