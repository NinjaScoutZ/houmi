# 🚀 แผนสถาปัตยกรรมและแผนงาน: การปรับปรุง Performance และความเสถียรของระบบ Houmi

แผนงานนี้มุ่งเน้นการยกระดับประสิทธิภาพและความเสถียรของโปรแกรม Houmi ทั้งระบบ (End-to-End Performance & Stability Engine) ให้ทำงานได้รวดเร็ว ลื่นไหล ไม่กินแรม และไม่เกิดปัญหาข้อมูลสูญหายแม้ใช้งานบนเครื่องสเปกเริ่มต้น (Low-spec CPU / Low RAM)

---

## 🏗️ Architecture & High-Level Design

```mermaid
graph TD
    subgraph Frontend["🖥️ Frontend (React / Canvas)"]
        UI[Canvas & Inspector UI]
        MemMgr[Asset ObjectURL GC & Memory Guard]
        VList[Virtualized Page & Layer Loader]
        WSClient[Resilient WebSocket Client with Backoff]
        UI --> MemMgr
        UI --> VList
        UI --> WSClient
    end

    subgraph Backend["⚙️ Backend (FastAPI / Worker Runtime)"]
        WSRouter[WebSocket & Event Dispatcher]
        JobQueue[Persistent Job & Cancellation Queue]
        AtomicIO[Atomic Project State Serializer]
        
        subgraph PipelineEngines["⚡ High-Performance Pipeline"]
            InpaintWorker[Adaptive Inpainting Engine (Parallel / Fast Region)]
            OCRWorker[Rate-Limited Batch OCR & Hash Cache]
            CacheMgr[Multi-Tier Memory & Disk LRU Cache]
        end
        
        WSClient <--> WSRouter
        WSRouter --> JobQueue
        JobQueue --> InpaintWorker
        JobQueue --> OCRWorker
        InpaintWorker --> CacheMgr
        OCRWorker --> CacheMgr
        JobQueue --> AtomicIO
    end
```

---

## 🎯 4 เสาหลักของการปรับปรุง (Core Optimization Pillars)

| เสาหลัก (Pillar) | ปัญหาปัจจุบัน | โซลูชันสถาปัตยกรรมใหม่ | ผลลัพธ์ที่คาดหวัง |
| :--- | :--- | :--- | :--- |
| **1. Inpainting & Clean Engine** | ประมวลผลภาพขนาดใหญ่ช้า, กินแรมสูง, สลับหน้าแล้วงานเก่ายังค้างรัน | Adaptive Tile Inpainting + Region Dirty-Tracking + Instant Task Cancellation | เร็วขึ้น 60–80%, ไม่กินแรมเกินพิกัด |
| **2. OCR Engine & Network** | ยิง API ถี่จนติด Rate Limit 429, ใช้เวลานานต่อหน้า | Token-Bucket Concurrency + Batch Grid 4x4 + Image Hash Caching | ลดเวลา OCR ลง 70%, ไม่มีปัญหา Request หลุด |
| **3. Frontend Canvas & Memory** | เลื่อนหน้าไปมาแล้วแรมพุ่งขึ้นเรื่อยๆ (Memory Leak จาก ObjectURL) | Strict ObjectURL Lifecycle Management + Render Viewport Throttling | แรมเบราว์เซอร์คงที่ ไม่สะสม (Zero Leak) |
| **4. Data Integrity & Resilience** | โปรแกรมดับ/เน็ตหลุดอาจทำให้ไฟล์โปรเจกต์เสียหาย หรือ WebSocket ค้าง | Atomic JSON Persistence (`tmp -> atomic replace`) + Auto Reconnect Queue | ป้องกันไฟล์พัง 100%, ทำงานต่อได้ทันทีเมื่อต่อติด |

---

## 📋 Phased Execution Plan (ตามข้อกำหนด GODKILLER Protocol)

### Phase 1 — Memory Safety & Frontend Asset Lifecycle (ป้องกัน Memory Leaks)
- **เป้าหมาย:** จัดการทรัพยากรฝั่ง Frontend Canvas และรูปภาพ ให้คืนหน่วยความจำทันทีเมื่อไม่ได้ใช้งาน
- **ไฟล์เป้าหมาย:**
  - `frontend/src/components/Canvas.tsx`
  - `frontend/src/hooks/useAssetUrl.ts` (หรือ Asset loader)
- **สิ่งที่ดำเนินการ:**
  1. สร้างระบบตรวจจับและสั่ง `URL.revokeObjectURL()` อย่างเข้มงวดเมื่อเปลี่ยนหน้าหรือภาพ Clean ถูกสร้างใหม่
  2. ปรับปรุง Fabric/Canvas Layer disposal ป้องกัน Event Listener ตกค้าง
  3. Throttling การวาด Mask และการซูม Pan ป้องกัน React re-render ซ้ำซ้อน

### Phase 2 — Parallel Inpainting & Smart Region Cancellation (เร่งความเร็ว Clean Mask)
- **เป้าหมาย:** ประมวลผล Clean ภาพอย่างรวดเร็วและยกเลิกงานทันทีเมื่อเปลี่ยนหน้า
- **ไฟล์เป้าหมาย:**
  - `backend/app/services/inpainter.py`
  - `backend/app/services/parallel_inpaint.py`
  - `backend/app/services/memory_cache.py`
- **สิ่งที่ดำเนินการ:**
  1. ปรับ Worker Pool ให้สอดคล้องกับจำนวน Physical CPU Cores แบบ Real-time
  2. ระบบ Dirty-Region Caching: หาก Mask ส่วนไหนไม่เปลี่ยน ให้ดึงผลลัพธ์เดิม ไม่ต้องรัน Inpaint ซ้ำ
  3. Cancellation Token ที่แทรกตัวในระดับ Loop ของ Inpainting เมื่อ User กดยกเลิกหรือสลับหน้าทันที

### Phase 3 — Async Batch OCR with Token-Bucket Rate Limiter (เร่งความเร็วและเสถียรภาพ OCR)
- **เป้าหมาย:** ลดจำนวน HTTP Request และป้องกัน 429 Too Many Requests
- **ไฟล์เป้าหมาย:**
  - `backend/app/services/ocr.py`
  - `backend/app/services/ocr_async.py`
- **สิ่งที่ดำเนินการ:**
  1. รวมกล่องข้อความใกล้เคียงเข้าเป็น Grid 4x4 ส่ง Gemini ภายใน Request เดียว
  2. ติดตั้ง Token Bucket Rate Limiter ควบคุมปริมาณ Request ไม่ให้เกินโควตาต่อนาที
  3. Cache ผลลัพธ์ OCR ด้วย Perceptual Hash (dHash/pHash) ของ Crop Image

### Phase 4 — Atomic File Persistence & WebSocket Auto-Healing (ความเสถียรของข้อมูลและการเชื่อมต่อ)
- **เป้าหมาย:** ป้องกันโปรเจกต์เสียหายจากการบันทึกไม่สมบูรณ์ และรักษาการเชื่อมต่อ
- **ไฟล์เป้าหมาย:**
  - `backend/app/services/project_serializer.py`
  - `backend/app/ws_manager.py`
  - `frontend/src/App.tsx` (WebSocket Client)
- **สิ่งที่ดำเนินการ:**
  1. ปรับการบันทึกไฟล์ `.json` ทุกจุดให้เป็น Atomic Write (`Write to .tmp` -> `os.replace`)
  2. เพิ่ม Reconnection Exponential Backoff พร้อม Message Ack/Resend Queue ฝั่ง WebSocket

### Phase 5 — Soak Testing, Performance Benchmark & Verification
- **เป้าหมาย:** ทดสอบความเสถียรต่อเนื่อง (Soak Test) และวัดผลเปรียบเทียบก่อน-หลัง
- **สิ่งที่ดำเนินการ:**
  1. ทดสอบรันโปรเจกต์ขนาดใหญ่ (30+ หน้า) ต่อเนื่อง 30 นาที
  2. วัดการใช้งาน Memory, CPU และ Response Time
  3. บันทึกผลลัพธ์ผ่าน `gk_verify.exit` เพื่อยืนยันว่าไม่มี Memory Leak หรือ Data Corruption
