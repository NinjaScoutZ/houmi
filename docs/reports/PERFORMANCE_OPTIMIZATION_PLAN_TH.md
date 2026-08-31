# 🚀 แผนการเพิ่มประสิทธิภาพ Houmi (ภาษาไทย)

**วันที่:** 2026-08-14  
**เป้าหมาย:** ลดเวลาการประมวลผลให้เหมาะกับคอมพิวเตอร์ที่มี CPU และ RAM น้อย

---

## 📊 สรุปปัญหาประสิทธิภาพปัจจุบัน

### ⏱️ เวลาที่ใช้ในการประมวลผล (1 หน้า):

| ขั้นตอน | เวลา (คอมปกติ) | เวลา (คอมช้า) | ไฟล์ที่เกี่ยวข้อง |
|---------|----------------|---------------|-----------------|
| **1. Text Detection** | 2-5 วินาที | 5-10 วินาที | `detector.py` |
| **2. Mask Generation** | 3-8 วินาที | 8-15 วินาที | `inpainter.py` |
| **3. Inpainting (Clean)** | 10-30 วินาที | 30-90 วินาที | `inpainter.py` |
| **4. OCR** | 15-40 วินาที | 40-120 วินาที | `ocr.py` |
| **5. Typesetting** | 2-5 วินาті | 5-10 วินาที | `typesetting/service.py` |
| **รวมทั้งหมด** | **32-88 วินาที** | **88-245 วินาที** | **(1.5-4 นาที!)** |

### 🔴 จุดคอขวดสำคัญ 3 อันดับแรก:

1. **🥇 Inpainting (30-90 วินาที)**
   - LaMa/MAT ONNX model ทำงานช้าบน CPU
   - Resize ทุก region เป็น 512×512
   - ไม่มี parallel processing
   - DirectML GPU disabled (เพราะ bug)

2. **🥈 OCR (40-120 วินาที)**
   - เรียก Gemini API ทีละ block (serial)
   - ไม่ใช้ batch processing
   - HTTP overhead สูง
   - Retry logic ช้า (3 attempts × 120s timeout)

3. **🥉 Mask Generation (8-15 วินาที)**
   - Adaptive thresholding ช้า
   - ไม่ cache mask results
   - รัน text detection หลายรอบ

---

## 🎯 แนวทางแก้ไข (เรียงตามความสำคัญ)

### **Phase 1: Quick Wins (Impact สูง, Effort ต่ำ)** ⚡

#### 1.1 เพิ่ม Performance Presets (1-2 ชั่วโมง)

สร้างโหมดการทำงาน 3 แบบ:

```python
# backend/app/services/performance_presets.py
PERFORMANCE_PRESETS = {
    "ultra_fast": {
        "inpaint_engine": "telea",           # ใช้ OpenCV แทน LaMa
        "mask_gen_method": "rectangle",      # ใช้ rectangle แทน adaptive
        "skip_mask_cache": False,
        "parallel_inpaint_workers": 2,
        "preview_width": 1200,
        "description": "⚡ เร็วที่สุด (สำหรับคอม CPU น้อย)"
    },
    "balanced": {
        "inpaint_engine": "lama",
        "mask_gen_method": "hybrid",
        "parallel_inpaint_workers": 3,
        "preview_width": 1600,
        "description": "⚖️ สมดุล (แนะนำ)"
    },
    "high_quality": {
        "inpaint_engine": "mat",
        "mask_gen_method": "hybrid",
        "parallel_inpaint_workers": 4,
        "preview_width": 2400,
        "description": "💎 คุณภาพสูงสุด (ต้องการ GPU)"
    }
}
```

**ผลลัพธ์ที่คาดหวัง:**
- Ultra Fast Mode: ลดเวลา Inpainting จาก 30 วินาที → **5-8 วินาที**

---

#### 1.2 เพิ่ม Async OCR (2-3 ชั่วโมง)

ใช้ `asyncio` + `httpx` แทน `requests`:

```python
# backend/app/services/ocr_async.py
import asyncio
import httpx
from typing import List

async def crop_and_ocr_blocks_async(
    img_path: str, 
    blocks: List[TextBlock], 
    max_concurrent: int = 5
) -> List[str]:
    """OCR หลาย blocks พร้อมกัน"""
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # สร้าง tasks สำหรับทุก blocks
        tasks = [
            ocr_single_block_async(client, img_path, block)
            for block in blocks
        ]
        
        # รัน max 5 requests พร้อมกัน
        results = []
        for i in range(0, len(tasks), max_concurrent):
            batch = tasks[i:i+max_concurrent]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            results.extend(batch_results)
        
        return results

async def ocr_single_block_async(
    client: httpx.AsyncClient, 
    img_path: str, 
    block: TextBlock
) -> str:
    """OCR block เดียว"""
    crop = extract_crop(img_path, block)
    base64_img = encode_image_base64(crop)
    
    response = await client.post(
        OCR_API_URL,
        json={"image": base64_img},
        timeout=30.0
    )
    
    return response.json()["text"]
```

**ผลลัพธ์ที่คาดหวัง:**
- OCR 20 blocks: ลดเวลาจาก 60 วินาที → **15-20 วินาที**

---

#### 1.3 ใช้ Gemini Batch API (1-2 ชั่วโมง)

ส่งหลาย blocks ใน 1 request:

```python
# backend/app/services/ocr.py (line 915)
def batch_ocr_with_gemini(img_path: str, blocks: List[TextBlock]) -> List[str]:
    """ส่ง grid image ที่มีหลาย blocks พร้อมกัน"""
    
    # สร้าง grid image (4×4 = 16 blocks ต่อ request)
    grid_img = create_grid_image(img_path, blocks, grid_size=(4, 4))
    
    # เรียก Gemini 1 ครั้ง
    response = call_gemini_api(grid_img, prompt="""
    OCR all text in this 4×4 grid. Return JSON:
    {"blocks": ["text1", "text2", ...]}
    """)
    
    return response["blocks"]
```

**ผลลัพธ์ที่คาดหวัง:**
- OCR 16 blocks: ลดจาก 16 requests → **1 request** (เร็วขึ้น 5-8 เท่า)

---

### **Phase 2: Major Improvements (Impact สูง, Effort ปานกลาง)** 🚀

#### 2.1 Parallel Inpainting (3-4 ชั่วโมง)

ทำ inpainting หลาย regions พร้อมกัน:

```python
# backend/app/services/inpainter.py (line 1700+)
from concurrent.futures import ThreadPoolExecutor
import os

def clean_page_text_parallel(page_id: str, db: Session) -> Path:
    """Clean page โดยใช้ parallel processing"""
    
    # ... (setup code)
    
    regions = _find_inpaint_regions(mask)
    max_workers = min(4, os.cpu_count() or 2)
    
    # Inpaint หลาย regions พร้อมกัน
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        
        for cx, cy, cw, ch in regions:
            crop_img = img[by0:by1, bx0:bx1]
            crop_mask = mask[by0:by1, bx0:bx1]
            
            future = executor.submit(
                lama_service.inpaint, 
                crop_img, 
                crop_mask
            )
            futures[future] = (by0, by1, bx0, bx1)
        
        # รอผลลัพธ์และ composite
        for future, (by0, by1, bx0, bx1) in futures.items():
            result = future.result()
            img_cleaned[by0:by1, bx0:bx1] = result
    
    return output_path
```

**ผลลัพธ์ที่คาดหวัง:**
- Inpaint 10 regions: ลดเวลาจาก 30 วินาที → **10-15 วินาที**

---

#### 2.2 Disk Cache สำหรับ Inpaint & OCR (3-4 ชั่วโมง)

Cache ผลลัพธ์ที่ใช้เวลานาน:

```python
# backend/app/services/cache_manager.py
import hashlib
import json
from pathlib import Path

class InpaintCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_cache_key(self, page_id: str, block_id: str, mask_fp: str) -> str:
        """Generate unique cache key"""
        data = f"{page_id}_{block_id}_{mask_fp}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def get(self, cache_key: str) -> np.ndarray | None:
        """Get cached inpaint result"""
        cache_file = self.cache_dir / f"{cache_key}.png"
        if cache_file.exists():
            return cv2_imread_unicode(str(cache_file))
        return None
    
    def set(self, cache_key: str, result: np.ndarray):
        """Save inpaint result to cache"""
        cache_file = self.cache_dir / f"{cache_key}.png"
        cv2_imwrite_unicode(str(cache_file), result)

# Usage
inpaint_cache = InpaintCache(Path("cache/inpaint"))

def clean_page_with_cache(page_id: str, db: Session):
    for block in page.text_blocks:
        mask_fp = compute_mask_fingerprint(block)
        cache_key = inpaint_cache.get_cache_key(page_id, block.id, mask_fp)
        
        # Check cache first
        cached = inpaint_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Using cached inpaint for block {block.id}")
            img_cleaned[y0:y1, x0:x1] = cached
            continue
        
        # Inpaint และ save to cache
        result = lama_service.inpaint(crop, mask)
        inpaint_cache.set(cache_key, result)
        img_cleaned[y0:y1, x0:x1] = result
```

**ประโยชน์:**
- Block ที่ไม่เปลี่ยน mask: **0 วินาที** (ใช้ cache)
- Re-editing workflow เร็วขึ้นมาก

---

#### 2.3 WebSocket Progress Updates (2-3 ชั่วโมง)

แสดง real-time progress bar:

```python
# backend/app/routes/pipeline.py
from fastapi import WebSocket

@router.websocket("/ws/pipeline/{project_id}")
async def pipeline_progress(websocket: WebSocket, project_id: str):
    await websocket.accept()
    
    try:
        # Run pipeline with progress callback
        await run_pipeline_with_progress(
            project_id,
            progress_callback=lambda data: websocket.send_json(data)
        )
    finally:
        await websocket.close()

async def run_pipeline_with_progress(project_id: str, progress_callback):
    pages = get_pages(project_id)
    
    for idx, page in enumerate(pages):
        # OCR Progress
        await progress_callback({
            "stage": "ocr",
            "page": idx + 1,
            "total_pages": len(pages),
            "progress": 0.0
        })
        
        ocr_blocks(page, progress_callback=lambda p: progress_callback({
            "stage": "ocr",
            "progress": p
        }))
        
        # Inpainting Progress
        await progress_callback({
            "stage": "inpaint",
            "progress": 0.0
        })
        
        clean_page(page, progress_callback=lambda p: progress_callback({
            "stage": "inpaint",
            "progress": p
        }))
```

**Frontend:**
```typescript
// frontend/src/hooks/usePipelineProgress.ts
const ws = new WebSocket(`ws://localhost:8000/ws/pipeline/${projectId}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  setProgress({
    stage: data.stage,
    progress: data.progress,
    page: data.page
  });
};
```

---

### **Phase 3: Advanced Optimizations (Impact ปานกลาง, Effort สูง)** 🔬

#### 3.1 Lazy Clean (Clean on Demand) (4-6 ชั่วโมง)

ไม่ clean ทั้งหน้าทีเดียว แต่ clean เฉพาะ block ที่ user เปิดดู:

```python
# backend/app/services/lazy_clean.py
def get_clean_preview_for_block(page_id: str, block_id: str, db: Session):
    """Clean เฉพาะ block นี้ (lazy loading)"""
    
    # Check cache first
    cached = get_block_clean_cache(page_id, block_id)
    if cached:
        return cached
    
    # Clean only this block region
    page = db.query(Page).filter(Page.id == page_id).first()
    block = get_block(block_id)
    
    source_img = load_image(page.source_image_path)
    block_crop = extract_crop(source_img, block)
    block_mask = get_block_mask(block)
    
    # Inpaint
    clean_crop = lama_service.inpaint(block_crop, block_mask)
    
    # Cache
    save_block_clean_cache(page_id, block_id, clean_crop)
    
    return clean_crop
```

**ประโยชน์:**
- User เห็น preview เร็วขึ้น (ไม่ต้องรอ clean ทั้งหน้า)
- ประหยัดเวลาสำหรับ blocks ที่ไม่เคยเปิดดู

---

#### 3.2 ONNX Model Quantization (6-8 ชั่วโมง)

ใช้ quantized models เพื่อลด memory และเพิ่มความเร็ว:

```python
# backend/models/quantize_lama.py
import onnx
from onnxruntime.quantization import quantize_dynamic, QuantType

def quantize_lama_model():
    model_path = "models/lama_fp32.onnx"
    quantized_path = "models/lama_int8.onnx"
    
    quantize_dynamic(
        model_path,
        quantized_path,
        weight_type=QuantType.QUInt8
    )
    
    print(f"Quantized model saved to {quantized_path}")
```

**ผลลัพธ์:**
- Model size: ลดจาก 200MB → **50MB**
- Inference speed: เร็วขึ้น **30-50%** บน CPU
- Memory usage: ลดลง **40-60%**

---

#### 3.3 GPU DirectML Debugging (8-12 ชั่วโมง)

แก้ไข DirectML bugs เพื่อใช้ GPU:

```python
# backend/app/services/inpainter.py (line 770+)
def _get_lama(execution_provider: str | None = None):
    opts = create_onnx_session_options()
    
    providers = get_execution_providers(execution_provider)
    
    # Fix: DirectML with proper configuration
    if "DmlExecutionProvider" in providers:
        dml_options = {
            'device_id': 0,
            'enable_graph_capture': True,
            'disable_metacommands': False  # ← Fix for LaMa
        }
        providers_with_options = [
            ('DmlExecutionProvider', dml_options),
            'CPUExecutionProvider'
        ]
        
        try:
            session = ort.InferenceSession(
                model_path, 
                sess_options=opts, 
                providers=providers_with_options
            )
            logger.info("LaMa loaded with DirectML GPU")
            return LamaONNXInpainter(session)
        except Exception as e:
            logger.warning(f"DirectML failed: {e}, fallback to CPU")
    
    # CPU fallback
    session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    return LamaONNXInpainter(session)
```

**ผลลัพธ์:**
- Inpaint speed: เร็วขึ้น **5-10 เท่า** (GPU vs CPU)

---

## 📈 สรุปผลลัพธ์ที่คาดหวัง

### ก่อนแก้ไข (คอม CPU น้อย):
| ขั้นตอน | เวลา |
|---------|------|
| Mask Generation | 8-15 วินาที |
| Inpainting | 30-90 วินาที |
| OCR | 40-120 วินาที |
| **รวม** | **78-225 วินาที** (~1.5-4 นาที) |

### หลังแก้ไข Phase 1 (Ultra Fast Mode):
| ขั้นตอน | เวลา | การเปลี่ยนแปลง |
|---------|------|----------------|
| Mask Generation | 2-4 วินาที | ↓ 75% (ใช้ rectangle) |
| Inpainting | 5-8 วินาที | ↓ 85% (ใช้ Telea) |
| OCR | 12-20 วินาที | ↓ 70% (ใช้ async + batch) |
| **รวม** | **19-32 วินาที** | **↓ 75-86%** |

### หลังแก้ไข Phase 2 (Balanced + Cache):
| ขั้นตอน | เวลา | การเปลี่ยนแปลง |
|---------|------|----------------|
| Mask Generation | 1-2 วินาที | ↓ 87% (ใช้ cache) |
| Inpainting | 8-12 วินาที | ↓ 73% (parallel + cache) |
| OCR | 10-15 วินาที | ↓ 75% (async + batch) |
| **รวม** | **19-29 วินาที** | **↓ 76-87%** |

### หลังแก้ไข Phase 3 (GPU + All Optimizations):
| ขั้นตอน | เวลา | การเปลี่ยนแปลง |
|---------|------|----------------|
| Mask Generation | 0.5-1 วินาที | ↓ 93% (cache + lazy) |
| Inpainting | 2-5 วินาที | ↓ 93% (GPU + parallel) |
| OCR | 8-12 วินาที | ↓ 80% (async + batch + cache) |
| **รวม** | **10.5-18 วินาที** | **↓ 87-92%** |

---

## 🚀 Implementation Roadmap

### Sprint 1 (1 สัปดาห์):
- [x] วิเคราะห์ bottlenecks
- [ ] Implement Performance Presets (Ultra Fast Mode)
- [ ] Implement Async OCR
- [ ] Implement Gemini Batch API

**Expected Result**: ลดเวลาจาก 4 นาที → **30-40 วินาที**

### Sprint 2 (1 สัปดาห์):
- [ ] Implement Parallel Inpainting
- [ ] Implement Disk Cache (Inpaint + OCR)
- [ ] Implement WebSocket Progress

**Expected Result**: ลดเวลาจาก 30-40 วินาที → **20-30 วินาที**

### Sprint 3 (2 สัปดาห์):
- [ ] Implement Lazy Clean
- [ ] ONNX Model Quantization
- [ ] GPU DirectML Debugging

**Expected Result**: ลดเวลาจาก 20-30 วินาที → **10-18 วินาที**

---

## 💻 วิธีใช้งาน Performance Modes

### สำหรับ End User (Frontend):

```typescript
// SettingsModal.tsx
<select 
  value={settings.performance_preset} 
  onChange={handlePresetChange}
>
  <option value="ultra_fast">
    ⚡ เร็วที่สุด - สำหรับคอม CPU น้อย (Telea, Rectangle Mask)
  </option>
  <option value="balanced">
    ⚖️ สมดุล - แนะนำสำหรับคอมทั่วไป (LaMa, Hybrid Mask)
  </option>
  <option value="high_quality">
    💎 คุณภาพสูง - ต้องการ GPU (MAT, Adaptive Mask)
  </option>
</select>
```

### สำหรับ Developer:

```bash
# Ultra Fast Mode
export PERFORMANCE_PRESET=ultra_fast
python -m uvicorn app.main:app --reload

# Balanced Mode (default)
python -m uvicorn app.main:app --reload

# High Quality Mode
export PERFORMANCE_PRESET=high_quality
export ENABLE_GPU=true
python -m uvicorn app.main:app --reload
```

---

## 📝 Notes & Warnings

### ⚠️ Trade-offs:
- **Ultra Fast Mode**: คุณภาพต่ำกว่า (Telea smudging, rectangle mask ไม่แม่นยำ)
- **Parallel Processing**: ใช้ RAM มากขึ้น (ต้อง limit max_workers)
- **Cache**: ใช้ disk space (ต้องมี cleanup strategy)

### ✅ Best Practices:
- ใช้ **Balanced Mode** เป็น default
- ใช้ **Ultra Fast Mode** สำหรับ preview/draft
- ใช้ **High Quality Mode** สำหรับ final export
- ตั้ง **cache TTL** = 7 วัน (auto cleanup)

---

## 🔗 Related Files

### Backend:
- `backend/app/services/inpainter.py` (2,328 lines)
- `backend/app/services/ocr.py` (1,200+ lines)
- `backend/app/services/detector.py`
- `backend/app/routes/pipeline.py`

### Frontend:
- `frontend/src/components/Canvas.tsx` (3,830 lines)
- `frontend/src/components/SettingsModal.tsx`
- `frontend/src/components/PipelineControlsPanel.tsx`

---

**สรุป**: การแก้ไขที่สำคัญที่สุดคือ **Performance Presets + Async OCR + Parallel Inpainting** เพราะจะช่วยให้คอมช้าใช้งานได้ดีขึ้นทันที โดยไม่ต้องเปลี่ยนโครงสร้างมาก

**ผลลัพธ์รวม**: ลดเวลาจาก **1.5-4 นาที** → **10-30 วินาที** (เร็วขึ้น **3-24 เท่า**)
