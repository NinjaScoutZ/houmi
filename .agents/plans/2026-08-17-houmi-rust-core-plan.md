# 🦀 สถาปัตยกรรมและแผนการพัฒนา: Standalone Rust Core & Server สำหรับ Houmi (`houmi-rust`)

แผนงานนี้จัดทำขึ้นเพื่อแยกส่วนพัฒนาโมดูลประสิทธิภาพสูงของ Houmi ออกเป็นโปรเจกต์ Standalone บนภาษา **Rust** (โฟลเดอร์ปลายทาง: `C:\Users\dansa\Desktop\houmi-rust`) มุ่งเน้นการประมวลผล Geometry, Mask Morphology, Thai Word Segmentation/Typesetting, และ High-throughput Local API Server เพื่อประสิทธิภาพและความเสถียรสูงสุด

---

## 🏗️ Architecture & High-Level Design (Cargo Workspace)

```mermaid
graph TD
    subgraph ClientLayer ["🖥️ Client / UI Layer"]
        Frontend["Web UI / Desktop WebView"]
        CLI["houmi-cli (Batch Tool)"]
    end

    subgraph Workspace ["📦 Cargo Workspace: houmi-rust"]
        Server["crates/houmi-server (Axum + WebSocket + Tokio)"]
        
        subgraph CoreCrates ["Core Computation Engines"]
            Core["crates/houmi-core (Data Models & State)"]
            Geometry["crates/houmi-geometry (Smart Balloon & Ray Casting)"]
            Mask["crates/houmi-mask (SIMD / Rayon Morphology & Contours)"]
            Typesetting["crates/houmi-typesetting (nlpO3 + Thai Word Wrap)"]
            PSD["crates/houmi-psd (Native PSD Binary Generation)"]
        end
    end

    subgraph ExternalAI ["🤖 External AI Bridge (Optional / Fallback)"]
        Gemini["Gemini / Cloud OCR API"]
        ONNX["ONNX Runtime / ORT (Inpaint & YOLO)"]
    end

    Frontend <--> |HTTP / WebSocket (Port 4000)| Server
    CLI --> CoreCrates
    Server --> Core
    Server --> Geometry
    Server --> Mask
    Server --> Typesetting
    Server --> PSD
    Server --> ExternalAI
```

---

## 📦 Modular Workspace Breakdown

| Crate Name | หน้าที่หลัก (Responsibility) | เทคโนโลยีสำคัญ (Key Dependencies) |
| :--- | :--- | :--- |
| **`houmi-core`** | Model โครงสร้างข้อมูล Project, Page, TextBlock, Layer, Serializer | `serde`, `serde_json`, `uuid`, `thiserror` |
| **`houmi-geometry`** | อัลกอริทึม Ray casting, Polygon waist cutting, Convex hull, Balloon fitting | `geo`, `euclid`, `parry2d` |
| **`houmi-mask`** | High-performance Grayscale/Binary Mask Morphological ops, Connected Components | `image`, `imageproc`, `rayon` |
| **`houmi-typesetting`** | Thai Word Segmentation, Line Breaking, Font Metrics | `nlpo3`, `unicode-segmentation`, `rustybuzz` |
| **`houmi-psd`** | สร้างไฟล์ Photoshop PSD พร้อม Text Layers & EngineData แบบ Native | Zero-copy byte writer, PackBits stream |
| **`houmi-server`** | Local HTTP REST API + WebSocket Server แบบ High-throughput | `axum (0.8)`, `tokio`, `tower-http` |
| **`houmi-cli`** | Command Line Tool สำหรับรัน Batch & Diagnostic Tests | `clap` |

---

## 📋 Phased Execution Plan (ตามข้อกำหนด GODKILLER Protocol)

### Phase 1 — Project Scaffold & Core Workspace Architecture
- **เป้าหมาย:** สร้างโครงสร้าง Cargo Workspace สมบูรณ์ที่ `C:\Users\dansa\Desktop\houmi-rust` พร้อม Data Models และ serialization
- **สิ่งที่ดำเนินการ:**
  1. สร้าง root `Cargo.toml` แบบ multi-crate workspace
  2. Implement `houmi-core` (Data Structures: `Project`, `Page`, `TextBlock`, `BalloonStyle`, `MaskData`)
  3. เขียน Unit Tests สำหรับ Data Serialization & Round-trip JSON

### Phase 2 — Geometry & Mask Kernel (Morphology & Smart Balloon)
- **เป้าหมาย:** พอร์ตและ Optimize อัลกอริทึม Shape Fitting, Waist Cut และ Mask Processing ด้วย Pure Rust + Rayon
- **สิ่งที่ดำเนินการ:**
  1. Implement `houmi-geometry`: Ray casting calculation จากจุดศูนย์กลางบอลลูน, Finding bounding waist polygon
  2. Implement `houmi-mask`: Dilation, Erosion, Adaptive Threshold, Connected Components แบบ Multi-threaded
  3. เขียน Unit Tests ทดสอบความแม่นยำเทียบกับกรณีทดสอบรูปทรงบอลลูน

### Phase 3 — Thai NLP Segmentation & Typesetting Engine
- **เป้าหมาย:** พอร์ตระบบตัดคำและคำนวณการจัดวางข้อความภาษาไทยด้วย `nlpO3` + Dictionary
- **สิ่งที่ดำเนินการ:**
  1. Setup `nlpO3` tokenizer พร้อม Dictionary `words_th.txt`
  2. Implement Algorithm แบ่งบรรทัด (Line-wrapping) ภายในขอบเขต Polygon ของบอลลูน
  3. จัดการกฎสระ-วรรณยุกต์และคำนวณ Font Bounding Box

### Phase 4 — Axum High-Performance Local Server & WebSocket Bridge
- **เป้าหมาย:** สร้าง Local Server ที่มีทั้ง REST API และ WebSocket สำหรับส่ง Progress/State แบบ Real-time
- **สิ่งที่ดำเนินการ:**
  1. Implement `houmi-server` ด้วย `axum` + `tokio`
  2. Endpoints: CRUD Projects, Health, Run Geometry Fitting, Run Mask Morph, Export PSD
  3. WebSocket Channel สำหรับ Event Streaming และ Cancellation Token

### Phase 5 — Verification, Benchmark & Test Suite
- **เป้าหมาย:** รัน Benchmark เปรียบเทียบความเร็วและการใช้หน่วยความจำ และยืนยันความถูกต้อง 100%
- **สิ่งที่ดำเนินการ:**
  1. วัด Throughput และ Latency ในการคำนวณ Geometry & Mask (เทียบเป้าหมาย <5ms)
  2. ทดสอบ Zero Memory Leak ในการประมวลผลภาพ 100+ requests
  3. รัน `cargo test --workspace` และเก็บผลลัพธ์ผ่าน `gk_verify.exit`
