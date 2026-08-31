# คำถามที่พบบ่อย (FAQ) - ฮาร์ดแวร์และความเข้ากันได้

## การ์ดจอและการเร่งความเร็ว

### Q: ต้องมีการ์ดจอไหมถึงจะใช้ Houmi Studio ได้?
**A: ไม่ต้อง!** Houmi Studio รองรับการทำงานแบบ CPU-only ได้เต็มรูปแบบ แต่จะช้ากว่าใช้การ์ดจอประมาณ 3-10 เท่า

- ✅ **มีการ์ดจอ**: เร็ว 3-10x (แนะนำ)
- ✅ **ไม่มีการ์ดจอ**: ใช้งานได้ปกติ แต่ช้ากว่า

---

### Q: การ์ดจอรุ่นไหนบ้างที่รองรับ?
**A: รองรับเกือบทุกการ์ดจอที่มีขายในตลาด:**

#### Nvidia (แนะนำ - ความเร็วสูงสุด)
- GTX 1050 Ti ขึ้นไป
- RTX 2060, 3060, 4060 (ทุก series)
- GTX 1650, 1660 Ti
- Laptop รุ่น RTX 30xx Mobile, 40xx Mobile

#### AMD (รองรับผ่าน DirectML)
- RX 5600 XT ขึ้นไป
- RX 6600, 6700 XT, 6800 series
- RX 7600, 7700 XT, 7900 series

#### Intel (รองรับผ่าน DirectML)
- Iris Xe Graphics (11th gen ขึ้นไป)
- Arc A380, A750, A770

---

### Q: ต้องติดตั้งอะไรเพิ่มไหม?
**A: ขึ้นอยู่กับการ์ดจอของคุณ:**

#### การ์ดจอ Nvidia
ต้องติดตั้ง **NVIDIA CUDA Toolkit** เพื่อให้ใช้งานเต็มประสิทธิภาพ:
1. ดาวน์โหลด: https://developer.nvidia.com/cuda-downloads
2. เลือก CUDA 11.8 หรือ 12.x
3. ติดตั้งตามขั้นตอนปกติ
4. Restart เครื่อง → เปิด Houmi Studio → กด Auto-Optimize

#### การ์ดจอ AMD / Intel
**ไม่ต้องติดตั้งอะไรเพิ่ม!** DirectML มาพร้อม Windows 10/11 อยู่แล้ว
- อัปเดตไดรเวอร์การ์ดจอให้เป็นเวอร์ชันล่าสุด (แนะนำ)
- เปิด Houmi Studio → กด Auto-Optimize

---

### Q: ทำไมแอปช้ามาก?
**A: มีสาเหตุหลักๆ ดังนี้:**

#### 1. ใช้โหมด CPU Fallback
**วิธีเช็ค**: เปิด Settings → Hardware Status → ดูว่า "Execution Provider" เป็น "CPUExecutionProvider" หรือไม่

**วิธีแก้**:
- ติดตั้ง CUDA Toolkit (สำหรับ Nvidia)
- อัปเดตไดรเวอร์การ์ดจอ (AMD/Intel)
- กดปุ่ม **Auto-Optimize**

#### 2. Performance Profile ตั้งเป็น Eco
**วิธีแก้**: Settings → Performance → เปลี่ยนเป็น Balanced หรือ Performance

#### 3. เครื่องสเปคต่ำ
**วิธีแก้**:
- ปิดโปรแกรมอื่นที่ทำงานอยู่
- ประมวลผลทีละน้อยๆ (ไม่ต้องทั้งโปรเจกต์)
- ใช้ Eco Mode แทน

---

### Q: ต้องใช้ RAM เท่าไหร่?
**A:**
- **ขั้นต่ำ**: 8 GB (พอใช้งานได้)
- **แนะนำ**: 16 GB (ลื่นไหล)
- **เหมาะสำหรับงานหนัก**: 32 GB+

**เคล็ดลับ**: ถ้า RAM น้อยกว่า 8GB
1. ใช้ Eco Mode
2. ปิดโปรแกรมอื่นทั้งหมด
3. ประมวลผลทีละ 1-2 หน้า

---

### Q: VRAM ต้องมีเท่าไหร่? (การ์ดจอ)
**A:**
- **4 GB VRAM**: พอใช้งานได้ (ภาพขนาดปกติ)
- **6-8 GB VRAM**: เหมาะสำหรับงานทั่วไป
- **12 GB+ VRAM**: เหมาะสำหรับภาพความละเอียดสูง

**หมายเหตุ**: ถ้า VRAM ไม่พอ ระบบจะแบ่งงานเป็นส่วนย่อยๆ อัตโนมัติ (tile-based inpainting)

---

## การปรับแต่งและแก้ปัญหา

### Q: ปุ่ม "Auto-Optimize" ทำอะไร?
**A: ปุ่มนี้ตรวจจับฮาร์ดแวร์และตั้งค่าให้เหมาะสมอัตโนมัติ**

ระบบจะ:
1. ตรวจจับการ์ดจอ (Nvidia, AMD, Intel)
2. เลือก Execution Provider ที่เร็วที่สุด
3. ปรับจำนวน CPU Threads
4. ตั้งค่า Performance Profile ที่เหมาะสม

**คำแนะนำ**: กดทุกครั้งหลังจาก:
- ติดตั้ง Houmi Studio ครั้งแรก
- อัปเดตไดรเวอร์การ์ดจอ
- ติดตั้ง CUDA Toolkit

---

### Q: ทำไมการ์ดจอ Nvidia ไม่ทำงาน?
**A: มีสาเหตุหลัก 3 อย่าง:**

#### 1. ยังไม่ได้ติดตั้ง CUDA Toolkit
**วิธีแก้**:
- ดาวน์โหลด CUDA: https://developer.nvidia.com/cuda-downloads
- ติดตั้งและ Restart เครื่อง
- เปิดแอป → กด Auto-Optimize

#### 2. ไดรเวอร์การ์ดจอเก่า
**วิธีแก้**:
- ดาวน์โหลด GeForce Experience
- อัปเดต Game Ready Driver เป็นเวอร์ชันล่าสุด
- Restart → Auto-Optimize

#### 3. ระบบเลือก DirectML แทน
**วิธีแก้**:
- Settings → Hardware Status
- เช็คว่า "Available Providers" มี "CUDAExecutionProvider" หรือไม่
- ถ้ามี → กด Auto-Optimize
- ถ้าไม่มี → ติดตั้ง CUDA Toolkit

---

### Q: DirectML คืออะไร? แตกต่างจาก CUDA ยังไง?
**A:**

| | DirectML | CUDA |
|---|---|---|
| **รองรับการ์ดจอ** | AMD, Intel, Nvidia | Nvidia เท่านั้น |
| **ติดตั้งเพิ่ม** | ไม่ต้อง (มากับ Windows) | ต้องติดตั้ง CUDA Toolkit |
| **ความเร็ว** | 3-5x เร็วกว่า CPU | 5-10x เร็วกว่า CPU |
| **ความเสถียร** | ดีมาก | ดีมาก |

**สรุป**:
- Nvidia → ใช้ CUDA (เร็วที่สุด)
- AMD/Intel → ใช้ DirectML (เร็วดี รองรับทุกการ์ดจอ)

---

### Q: แอปค้างหรือ Not Responding
**A: แก้ไขได้หลายวิธี:**

#### 1. ลด CPU Thread Count
Settings → Advanced → CPU Threads → ตั้งเป็น `cpu_cores - 2`

ตัวอย่าง:
- CPU 8 cores → ตั้งเป็น 6 threads
- CPU 4 cores → ตั้งเป็น 2 threads

#### 2. ใช้ Eco Mode
Settings → Performance Profile → เลือก Eco

#### 3. ปิดโปรแกรมอื่น
- Google Chrome (กิน RAM มาก)
- Photoshop
- Video Editors

#### 4. Restart Houmi Studio
ปิดแอปแล้วเปิดใหม่ → กด Auto-Optimize

---

### Q: Out of Memory Error
**A: แก้ตามขั้นตอน:**

#### สำหรับ RAM Error
1. ปิดโปรแกรมอื่นที่ใช้ RAM มาก
2. ใช้ Eco Mode
3. ประมวลผลทีละน้อยๆ (1-5 หน้า)
4. Restart เครื่อง

#### สำหรับ VRAM Error (การ์ดจอ)
1. Settings → Inpainting → Enable "Tile-based Inpainting"
2. ลดขนาดภาพก่อนประมวลผล
3. ปิดโปรแกรมที่ใช้การ์ดจออื่นๆ (เกม, Video Editing)

---

## การทดสอบและตรวจสอบ

### Q: ตรวจสอบฮาร์ดแวร์ของตัวเองยังไง?
**A: เปิด Houmi Studio:**

1. ไป Settings → Hardware Status
2. ดูข้อมูล:
   - **GPU Name**: ชื่อการ์ดจอ
   - **GPU VRAM**: หน่วยความจำการ์ดจอ
   - **CPU Name & Cores**: ข้อมูล CPU
   - **RAM**: หน่วยความจำ
   - **Active Provider**: กำลังใช้ CUDA/DirectML/CPU
   - **Is Optimized**: ตั้งค่าเหมาะสมแล้วหรือยัง

3. ดู **Optimization Suggestions** ถ้ามีคำแนะนำให้ทำตาม

---

### Q: ต้องการทดสอบว่าใช้การ์ดจอจริงไหม?
**A: วิธีเช็ค:**

#### วิธีที่ 1: ดูใน Task Manager (แนะนำ)
1. กด `Ctrl + Shift + Esc` เปิด Task Manager
2. ไปแท็บ Performance → เลือก GPU
3. ประมวลผลภาพใน Houmi Studio
4. ดูว่า GPU Usage เพิ่มขึ้นหรือไม่

#### วิธีที่ 2: ดูใน Houmi Studio
1. Settings → Hardware Status
2. ดู "Acceleration Type":
   - ⚡ **Nvidia CUDA Acceleration** = กำลังใช้การ์ดจอ Nvidia (เร็วสุด)
   - 🚀 **DirectML Acceleration** = กำลังใช้การ์ดจอ AMD/Intel
   - 🐢 **CPU Fallback Mode** = ไม่ได้ใช้การ์ดจอ (ช้า)

---

### Q: Performance Mode ต่างกันยังไง?
**A:**

| Mode | Preview Size | OCR Workers | GPU | เหมาะสำหรับ |
|------|--------------|-------------|-----|------------|
| **Eco** | 800px | 1 | ไม่บังคับ | เครื่องสเปคต่ำ, RAM 8GB |
| **Balanced** | 1200px | 2 | แนะนำ | เครื่องทั่วไป, RAM 16GB |
| **Performance** | 1800px | 4 | ต้องมี | เครื่องแรง, RAM 32GB+ |

**คำแนะนำ**: ให้ Auto-Optimize เลือกให้ แต่ถ้าต้องการ:
- **ช้าเกินไป** → เลือก Performance
- **ค้างหรือแครช** → เลือก Eco

---

## เทียบสเปคตัวอย่าง

### เครื่องของฉันใช้ได้ไหม?

#### ✅ ตัวอย่าง 1: เครื่องออฟฟิศ
- CPU: Intel i5-10400
- RAM: 8 GB
- GPU: Intel UHD Graphics 630
- **ผลลัพธ์**: ใช้งานได้ แต่ช้า → ใช้ Eco Mode, DirectML หรือ CPU

#### ✅ ตัวอย่าง 2: Gaming Laptop
- CPU: Intel i7-12700H
- RAM: 16 GB
- GPU: RTX 3060 Mobile (6GB)
- **ผลลัพธ์**: ลื่นไหลมาก → ติดตั้ง CUDA Toolkit, ใช้ Balanced/Performance Mode

#### ✅ ตัวอย่าง 3: Workstation
- CPU: AMD Ryzen 9 5950X
- RAM: 32 GB
- GPU: RTX 4080 (16GB)
- **ผลลัพธ์**: เร็วสุด → CUDA, Performance Mode เต็มประสิทธิภาพ

#### ✅ ตัวอย่าง 4: AMD Gaming Desktop
- CPU: Ryzen 7 5800X
- RAM: 16 GB
- GPU: RX 6700 XT (12GB)
- **ผลลัพธ์**: เร็วดี → DirectML, Balanced Mode

---

## ติดต่อ Support

### Q: ยังแก้ไม่ได้ ติดต่อยังไง?
**A: ส่งข้อมูลเหล่านี้มาที่ Support:**

1. **Hardware Report**: 
   - Settings → Hardware Status → Copy ข้อมูลทั้งหมด

2. **Error Logs**: 
   - Settings → Diagnostics → Latest Crash Report

3. **ข้อมูลระบบ**:
   - Windows version
   - Houmi Studio version
   - อาการที่เกิด (ช้า/ค้าง/แครช)

---

## สรุป Quick Reference

| ปัญหา | แก้ไขเบื้องต้น |
|-------|----------------|
| 🐌 ช้ามาก | กด Auto-Optimize → ติดตั้ง CUDA (Nvidia) |
| 🚫 แอปค้าง | ลด CPU Threads → ใช้ Eco Mode → ปิดโปรแกรมอื่น |
| 💾 Out of Memory | ปิดโปรแกรมอื่น → ใช้ Eco Mode → ประมวลผลทีละน้อย |
| ⚡ GPU ไม่ทำงาน | ติดตั้ง CUDA Toolkit → อัปเดตไดรเวอร์ → Auto-Optimize |
| ❓ ไม่แน่ใจ | กด Auto-Optimize ก่อนเสมอ! |

---

**คำแนะนำสุดท้าย**: 
**กดปุ่ม Auto-Optimize ทุกครั้งที่เปิดใช้งาน Houmi Studio ครั้งแรก** 
ระบบจะตรวจจับและตั้งค่าให้เหมาะสมอัตโนมัติ แก้ปัญหาส่วนใหญ่ได้เลย!
