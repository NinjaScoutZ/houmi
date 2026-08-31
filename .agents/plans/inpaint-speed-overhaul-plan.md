# MangaToolPlus Speed Techniques — Full Remaining Port Plan

> **สถานะ**: Phase 1-4 เสร็จแล้ว (cluster merge, native ONNX, progressive padding, color-match blend)
> **เอกสารนี้**: วางแผน Phase 5-12 ที่เหลือทั้งหมด พร้อมวิเคราะห์ว่าอะไรคุ้มค่าที่สุด

---

## 📊 Impact / Effort Matrix

```
                          IMPACT สูง
                             ▲
                             │
     ┌───────────────────────┼───────────────────────┐
     │                       │                       │
     │  ★ Phase 5             │  Phase 9              │
     │  Feathered Solid Fill │  Viewport Culling     │
     │  (15 นาที, คุณภาพ++)   │  (2 ชม., FPS ++)      │
     │                       │                       │
     │  ★ Phase 6             │  Phase 10             │
     │  GPU Cache Cleanup    │  Zoom Snapshot        │
     │  (5 นาที, VRAM ++)    │  (1 ชม., UX ++)       │
     │                       │                       │
     │  ★ Phase 7             │  Phase 11             │
     │  Ring Histogram Fill  │  Parallel Batch Clean │
     │  (30 นาที, accuracy++)│  (1 ชม., 3x batch)    │
     │                       │                       │
     │  ★ Phase 8             │  Phase 12             │
     │  CC Solid Fill        │  ImageBitmap Blit     │
     │  (20 นาที, quality++) │  (30 นาที, RAM ++)     │
  ◄──┼───────────────────────┼───────────────────────┼──►
  ง่าย│                       │                       │ ยาก
     │                       │                       │
     │                       │  (Frontend Fabric.js  │
     │                       │   ต้อง refactor ใหญ่)  │
     │                       │                       │
     └───────────────────────┼───────────────────────┘
                             │
                          IMPACT ต่ำ
```

**★ = Best ROI (ทำง่าย ผลลัพธ์สูง) — แนะนำทำก่อน**

---

## ★ Phase 5 — Gaussian Feathered Solid Fill

**Target**: [`inpainter.py`](file:///e:/houmi/backend/app/services/inpainter.py) — `_clean_page_text_impl()` L2599-2601

**ปัญหาตอนนี้**:
```python
img[block_mask > 0] = solid_color  # Hard edge! เหมือนเอาสี่เหลี่ยมแปะทับ
```

**แก้เป็น**: Gaussian blur mask ก่อนใช้เป็น alpha → ได้ขอบ feathered เนียนสนิท

```python
# สิ่งที่ต้องเพิ่ม:
blur_r = max(7, int(max(bw, bh) * 0.04) | 1)
mask_blur = cv2.GaussianBlur(block_mask, (blur_r, blur_r), 0)
mask_f = (mask_blur.astype(np.float32) / 255.0)[:, :, np.newaxis]
fill = np.full_like(img, solid_color, dtype=np.float32)
img[:] = np.clip(fill * mask_f + img.astype(np.float32) * (1.0 - mask_f), 0, 255).astype(np.uint8)
```

| Effort | Impact | Risk |
|---|---|---|
| 15 นาที | คุณภาพ solid fill ดีขึ้นมาก (ไม่เห็นขอบ) | ต่ำมาก |

---

## ★ Phase 6 — GPU VRAM Cache Cleanup

**Target**: [`inpainter.py`](file:///e:/houmi/backend/app/services/inpainter.py) — `_cluster_inpaint()` / `_per_block_inpaint()`

**เพิ่ม 3 บรรทัดหลัง batch loop**:
```python
try:
    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
except ImportError:
    pass
```

| Effort | Impact | Risk |
|---|---|---|
| 5 นาที | ป้องกัน VRAM leak ใน long batch | ต่ำมาก (try/except) |

---

## ★ Phase 7 — Ring Extraction + 16-Step Histogram Color Estimation

**Target**: [`inpainter.py`](file:///e:/houmi/backend/app/services/inpainter.py) — `_detect_uniform_fill_color()` L447-490

**ปัญหาตอนนี้**: ใช้ simple median ของพิกเซลนอก mask — อาจจับสีจากตัวอักษรที่ยังอยู่ในกรอบ

**แก้เป็น** (เหมือน MangaToolPlus `_estimate_flat_fill_color_bgr`):
1. Dilate mask สร้าง **ring** รอบข้อความ (เฉพาะขอบนอก ไม่เอาตัวอักษร)
2. Quantize BGR ลง 16³ bins → หา dominant color mode
3. Verify ด้วย luma spread ≤28 + channel spread ≤28

| Effort | Impact | Risk |
|---|---|---|
| 30 นาที | Solid fill สีแม่นกว่า โดยเฉพาะบอลลูนสีเทา/ครีม | ต่ำ |

---

## ★ Phase 8 — Connected-Component Solid Fill

**Target**: [`inpainter.py`](file:///e:/houmi/backend/app/services/inpainter.py) — solid fill section in `_clean_page_text_impl()`

**ปัญหาตอนนี้**: Fill ทั้ง `block_mask` ด้วยสีเดียว — แต่ถ้า block mask มี 2+ ก้อนข้อความ (เช่น 2 บรรทัดห่างกัน) พื้นที่ระหว่างก้อนก็ถูกเฉลี่ยรวมด้วย

**แก้เป็น**: `cv2.connectedComponentsWithStats(block_mask)` → fill ทีละ component ด้วยสีที่ estimate จาก ring รอบๆ component นั้นๆ

| Effort | Impact | Risk |
|---|---|---|
| 20 นาที | สีถูกต้องกว่าในบอลลูนที่มีพื้นหลังเปลี่ยนระดับสี | ต่ำ |

---

## Phase 9 — Fabric.js Viewport Culling

**Target**: [`frontend/src/components/Canvas.tsx`](file:///e:/houmi/frontend/src/components/Canvas.tsx)

**สิ่งที่ต้องทำ**: เมื่อ zoom เข้ามาในเว็บตูนยาว → ไม่ render Fabric objects ที่อยู่นอก viewport

```typescript
// Fabric.js มี objectCaching built-in, แต่ไม่มี viewport culling
// ต้องเพิ่ม: ก่อน renderAll, filter objects ที่ intersect viewport
canvas.on('before:render', () => {
  const vpt = canvas.viewportTransform;
  canvas.getObjects().forEach(obj => {
    obj.visible = isInViewport(obj, vpt, canvas.width, canvas.height);
  });
});
```

| Effort | Impact | Risk |
|---|---|---|
| 2 ชั่วโมง | FPS เพิ่มมากเมื่อ zoom เว็บตูน (100+ text blocks) | ปานกลาง (ต้อง test edge cases) |

> [!WARNING]
> Fabric.js `objectCaching` ทำ bitmap cache ต่อ object แล้ว — Viewport culling เพิ่มอีกชั้นช่วยได้ก็ต่อเมื่อมี objects มากกว่า ~50 ขึ้นไป

---

## Phase 10 — Zoom Snapshot Fast Path

**Target**: [`frontend/src/components/Canvas.tsx`](file:///e:/houmi/frontend/src/components/Canvas.tsx) — wheel zoom handler

**สิ่งที่ต้องทำ**: ตอน scroll wheel zoom → จับ snapshot ของ canvas ปัจจุบัน → stretch snapshot ตาม scale ใน rAF → render จริงเฉพาะตอนหยุด scroll

```typescript
let zoomTimeout: number;
canvas.on('mouse:wheel', (opt) => {
  // Stretch cached snapshot (cheap)
  stretchSnapshot(snapshotCanvas, newZoom);
  // Debounce real render
  clearTimeout(zoomTimeout);
  zoomTimeout = setTimeout(() => renderFullQuality(), 150);
});
```

| Effort | Impact | Risk |
|---|---|---|
| 1 ชั่วโมง | Zoom ไม่กระตุกเลย (ลด 20+ re-renders ต่อ scroll) | ต่ำ |

---

## Phase 11 — Parallel Batch Clean (Frontend)

**Target**: Frontend batch pipeline call

**ปัญหาตอนนี้**: Clean ทีละหน้า sequential → 15 หน้า × 2.5s = 37.5s

**แก้เป็น**: ส่ง 2-3 หน้าพร้อมกันด้วย `Promise.all` (backend มี thread lock อยู่แล้ว ดังนั้นจริงๆ จะ queue ใน backend, แต่ HTTP roundtrip overlap กัน)

> [!IMPORTANT]
> **Backend ใช้ `_inpaint_thread_lock`** serializes inference อยู่แล้ว — Parallel frontend requests จะ overlap ได้เฉพาะ HTTP overhead + mask generation ส่วนหน้า inference ยังคง serial ดังนั้น speedup จริง ~1.3-1.5x ไม่ใช่ 3x

| Effort | Impact | Risk |
|---|---|---|
| 1 ชั่วโมง | ~1.3x เร็วขึ้นตอน batch (overlap HTTP) | ต่ำ |

---

## Phase 12 — ImageBitmap GPU Blitting

**Target**: Frontend image loading paths

**แก้เป็น**: แทนที่ `new Image()` + `img.src = url` ด้วย `createImageBitmap(blob)` สำหรับ inpainted images ที่โหลดจาก backend → GPU-direct zero-copy

| Effort | Impact | Risk |
|---|---|---|
| 30 นาที | ลด GC spikes + RAM usage เมื่อสลับหน้า | ต่ำ |

---

## 🏆 คำแนะนำ: ลำดับที่ดีที่สุด

```
เร็ว + คุ้มค่าสูง (ทำได้ภายใน 1 ชั่วโมง):
  ★ Phase 6  — GPU Cache Cleanup         (5 นาที)
  ★ Phase 5  — Feathered Solid Fill      (15 นาที)
  ★ Phase 8  — CC Solid Fill             (20 นาที)
  ★ Phase 7  — Ring Histogram Fill       (30 นาที)
  ─────────────────────────────────────────────
  รวม: ~70 นาที → คุณภาพ solid fill ดีขึ้นมาก + VRAM ไม่ leak

ปานกลาง (ทำเพิ่มถ้ามีเวลา):
  Phase 12 — ImageBitmap Blit           (30 นาที)
  Phase 10 — Zoom Snapshot              (1 ชั่วโมง)
  Phase 11 — Parallel Batch Clean       (1 ชั่วโมง)

ยาก (ต้อง refactor / risk สูง):
  Phase 9  — Viewport Culling           (2 ชั่วโมง)
```

---

## สรุป Budget Time

| กลุ่ม | เวลารวม | ผลลัพธ์ |
|---|---|---|
| **★ Quick Wins (Phase 5-8)** | ~70 นาที | Solid fill คุณภาพเทียบ MangaToolPlus + ไม่ leak VRAM |
| **Medium (Phase 10-12)** | ~2.5 ชั่วโมง | Zoom ลื่น + batch เร็วขึ้น + RAM ดีขึ้น |
| **Hard (Phase 9)** | ~2 ชั่วโมง | FPS ++ ตอน zoom เว็บตูนยาว |
| **รวมทั้งหมด** | **~5.5 ชั่วโมง** | **ปิดช่องว่างกับ MangaToolPlus 100%** |
