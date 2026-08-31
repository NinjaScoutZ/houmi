# Houmi Studio - System Requirements & Hardware Compatibility Guide

## ระบบขั้นต่ำ (Minimum Requirements)

### สำหรับการใช้งานพื้นฐาน
- **CPU**: Intel Core i5 / AMD Ryzen 5 (4 cores) หรือดีกว่า
- **RAM**: 8 GB DDR4
- **Storage**: 5 GB available space (SSD แนะนำ)
- **OS**: Windows 10 64-bit (Build 1809+) หรือ Windows 11
- **GPU**: ไม่บังคับ (ระบบจะใช้ CPU Fallback Mode)

### สำหรับการใช้งานเร็วและลื่นไหล (Recommended)
- **CPU**: Intel Core i7 / AMD Ryzen 7 (8+ cores)
- **RAM**: 16 GB DDR4+
- **GPU**: 
  - **Nvidia**: GTX 1650 / RTX 2060 ขึ้นไป (4 GB VRAM+)
  - **AMD**: RX 5600 XT ขึ้นไป (6 GB VRAM+)
  - **Intel**: Arc A380 ขึ้นไป
- **OS**: Windows 11 (recommended for DirectML)

---

## รองรับการ์ดจอ (GPU Acceleration Support)

Houmi Studio รองรับการเร่งความเร็วด้วย GPU 3 แบบ:

### 1. NVIDIA CUDA ⚡ (ความเร็วสูงสุด 5-10x)
- **การ์ดที่รองรับ**: GTX 10xx, RTX 20xx, RTX 30xx, RTX 40xx series
- **ต้องติดตั้ง**: [NVIDIA CUDA Toolkit 11.8+](https://developer.nvidia.com/cuda-downloads)
- **ไดรเวอร์**: GeForce Game Ready Driver 522.25+

### 2. DirectML 🚀 (รองรับทุกการ์ดบน Windows)
- **การ์ดที่รองรับ**: 
  - Nvidia (GTX 9xx+, RTX series)
  - AMD (RX 5xx+, Radeon VII, RX 6000/7000 series)
  - Intel (Iris Xe, Arc Alchemist)
- **ติดตั้งอัตโนมัติ**: มากับ Windows 10/11 แล้ว
- **ความเร็ว**: 3-5x เร็วกว่า CPU

### 3. CPU Fallback Mode 🐢 (สำหรับเครื่องไม่มีการ์ดจอ)
- รองรับ CPU ทุกรุ่น
- ใช้ Multi-Threading ป้องกันแอปค้าง
- ความเร็วช้ากว่า GPU แต่ทำงานได้ทุกเครื่อง

---

## การตรวจสอบและปรับแต่งระบบ

### 1. ตรวจสอบฮาร์ดแวร์ของคุณ
เปิด Houmi Studio → Settings → Hardware Status

ระบบจะแสดง:
- ชื่อการ์ดจอ (GPU Name)
- ขนาด VRAM
- Execution Provider ที่กำลังใช้งาน
- คำแนะนำการปรับปรุง (Optimization Suggestions)

### 2. ปรับแต่งอัตโนมัติ (Auto-Optimize) 🎯
กดปุ่ม **"Auto-Optimize"** ให้ระบบเลือก:
- Execution Provider ที่เหมาะสมที่สุด (CUDA/DirectML/CPU)
- จำนวน CPU Threads ที่เหมาะสม
- Performance Profile ที่เหมาะกับเครื่องของคุณ

### 3. ปรับ Performance Profile ด้วยตัวเอง
- **Eco Mode**: เครื่องสเปคต่ำ (4GB RAM, CPU-only)
- **Balanced Mode**: เครื่องทั่วไป (8-16GB RAM, DirectML)
- **Performance Mode**: เครื่องแรง (16GB+ RAM, CUDA/High-end GPU)

---

## แก้ปัญหาทั่วไป (Troubleshooting)

### ❌ "ระบบทำงานช้ามาก"
1. เช็คว่ากำลังใช้ CPU Fallback หรือไม่ → ลองกด Auto-Optimize
2. ติดตั้ง CUDA Toolkit (สำหรับ Nvidia) หรือ อัปเดตไดรเวอร์การ์ดจอ
3. ลด Performance Profile เป็น Eco หากเครื่องสเปคต่ำ

### ❌ "แอปค้างหรือ Not Responding"
1. ลด CPU Thread Count ใน Settings → Advanced
2. ปิดโปรแกรมอื่นที่กิน RAM มาก
3. ใช้ Eco Mode แทน Performance Mode

### ❌ "GPU ไม่ทำงาน แม้มีการ์ดจอ Nvidia"
1. ติดตั้ง NVIDIA CUDA Toolkit: https://developer.nvidia.com/cuda-downloads
2. อัปเดต GeForce Driver เป็นเวอร์ชันล่าสุด
3. Restart Houmi Studio → กด Auto-Optimize อีกครั้ง

### ❌ "หน่วยความจำเต็ม (Out of Memory)"
1. ลด Performance Profile เป็น Eco
2. ประมวลผลทีละน้อยแทนการทำทั้งโปรเจกต์
3. ปิดแท็บ/โปรแกรมอื่นขณะใช้งาน

---

## Hardware Compatibility Matrix

| Component | Minimum | Recommended | Optimal |
|-----------|---------|-------------|---------|
| **CPU** | 4 cores | 8 cores | 12+ cores |
| **RAM** | 8 GB | 16 GB | 32 GB+ |
| **GPU VRAM** | N/A (CPU) | 4 GB | 8 GB+ |
| **Acceleration** | CPU | DirectML | CUDA |
| **Speed** | 1x (baseline) | 3-5x | 5-10x |

---

## Tested Hardware Configurations ✅

### Confirmed Working Configurations:
- **Desktop Nvidia**: RTX 4090, RTX 4070, RTX 3080, RTX 3060, GTX 1660 Ti
- **Laptop Nvidia**: RTX 4060 Mobile, RTX 3060 Mobile, GTX 1650 Mobile
- **AMD GPU**: RX 6700 XT, RX 6600, RX 5600 XT (DirectML)
- **Intel GPU**: Arc A750, Arc A380, Iris Xe Graphics (DirectML)
- **CPU-only**: Intel i9-13900K, AMD Ryzen 9 5950X, Intel i5-10400

---

## สรุป: Houmi Studio รองรับฮาร์ดแวร์หลากหลาย

✅ **ทำงานได้ทุกเครื่อง** - มี CPU Fallback Mode  
✅ **ปรับตัวอัตโนมัติ** - ระบบเลือก Provider ที่เหมาะสมเอง  
✅ **รองรับทุกการ์ดจอ** - CUDA (Nvidia), DirectML (AMD/Intel/Nvidia), CPU  
✅ **ไม่แครช** - มี Thread Limiting และ Memory Management  
✅ **ปรับแต่งได้** - เลือก Performance Profile เองได้

**คำแนะนำ**: ให้ลูกค้ากดปุ่ม **Auto-Optimize** ครั้งแรกที่เปิดแอป ระบบจะปรับแต่งให้เหมาะกับเครื่องอัตโนมัติ
