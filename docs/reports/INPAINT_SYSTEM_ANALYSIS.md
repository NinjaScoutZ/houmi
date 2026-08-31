# Inpaint System Analysis: GPU Server vs Local ONNX

## วิเคราะห์ระบบปัจจุบัน ✅

### 1. ลำดับการเลือก Inpaint Engine (Priority Order)

```python
def _get_lama(execution_provider, custom_url, force_onnx):
    # Priority 1: Force ONNX (เมื่อ engine_name == "lama_onnx")
    if force_onnx:
        return LamaONNXInpainter(...)  # Local ONNX only

    # Priority 2: Custom GPU URL (จาก settings.gpu_inpaint_url)
    if custom_url and custom_url.strip():
        try:
            return LamaCleanerClientInpainter(custom_url)
        except:
            logger.warning("Failed to connect to custom GPU URL")

    # Priority 3: Auto-detect Local GPU Server (ports 2328, 2322, 2335)
    for port in (2328, 2322, 2335):
        if _is_local_lama_cleaner_alive(port):
            return LamaCleanerClientInpainter(f"http://127.0.0.1:{port}/inpaint")

    # Priority 4: Try auto-start inpaint daemon
    from app.services.inpaint_server_manager import inpaint_manager
    inpaint_manager.start_server_if_needed()
    # ... check ports again

    # Priority 5: Fallback to Local ONNX LaMa (DirectML/CUDA/CPU)
    return LamaONNXInpainter(model_path, execution_provider)
```

---

## 2. สถานะปัจจุบัน: ✅ ถูกต้อง

### ✅ สิ่งที่ทำงานได้ดี

1. **Auto-Fallback Chain**:
   - GPU Server (custom URL) → Local ports → Auto-start → ONNX → Telea
   - มี fallback ครบทุกขั้น ไม่มีกรณีที่ crash

2. **Custom GPU URL Support**:
   - รองรับ `gpu_inpaint_url` ใน project settings
   - ตรวจสอบ `/health` endpoint ก่อนใช้
   - Timeout 1.0 วินาที (เหมาะสม)

3. **Local ONNX Fallback**:
   - ใช้ DirectML/CUDA/CPU ตาม execution_provider
   - มี `_get_fallback_lama_onnx()` สำหรับ emergency fallback

4. **LamaCleanerClientInpainter**:
   - รองรับ multipart/form-data POST
   - มี timeout 75 วินาที (เหมาะสำหรับ GPU inference)
   - Auto-resize output ให้ตรงกับ input

---

## 3. ปัญหาที่พบและควรแก้ไข ⚠️

### ⚠️ Issue #1: ONNX Fallback ใน LamaCleanerClient ไม่มี execution_provider

**Location:** `inpainter.py:1164-1173`

```python
def inpaint(self, image_bgr, mask_gray):
    try:
        # ... ส่งไป GPU Server
    except Exception as err:
        # ❌ ปัญหา: _get_fallback_lama_onnx() ไม่ได้รับ execution_provider
        fallback = _get_fallback_lama_onnx()
        if fallback:
            return fallback.inpaint(image_bgr, mask_gray)
```

**ผลกระทบ:**
- เมื่อ GPU Server ล้ม fallback จะใช้ CPU เสมอ (ไม่ใช้ DirectML/CUDA)
- ช้ากว่าที่ควรจะเป็น

**วิธีแก้:**
```python
def _get_fallback_lama_onnx(execution_provider: str | None = None) -> Any | None:
    """Retrieve ONNX with proper execution provider."""
    from app.config import MODELS_DIR
    for alt in (...):
        try:
            return LamaONNXInpainter(str(alt), execution_provider=execution_provider)
        except:
            pass
    return None
```

---

### ⚠️ Issue #2: Global `_lama` Caching ทำให้ custom_url เปลี่ยนไม่ได้ทันที

**Location:** `inpainter.py:1228-1230`

```python
if isinstance(_lama, LamaCleanerClientInpainter):
    if not custom_url or _lama.endpoint_url == custom_url:
        return _lama  # ❌ ใช้ cached instance เก่า
```

**ผลกระทบ:**
- ผู้ใช้เปลี่ยน `gpu_inpaint_url` ใน Settings
- ต้อง restart backend ถึงจะมีผล

**วิธีแก้:**
```python
if isinstance(_lama, LamaCleanerClientInpainter):
    if custom_url and _lama.endpoint_url != custom_url:
        # URL เปลี่ยน → ล้าง cache และลองใหม่
        _lama = None
        _lama_checked = False
    elif not custom_url:
        return _lama  # ไม่มี custom URL → ใช้ cached
```

---

### ⚠️ Issue #3: `force_onnx=True` ไม่ support custom_url

**Location:** `inpainter.py:1209-1226`

```python
if force_onnx:
    # ❌ ข้ามการตรวจสอบ custom_url ทันที
    if _lama_onnx is not None:
        return _lama_onnx
    # ... โหลด ONNX เท่านั้น
```

**ผลกระทบ:**
- เมื่อเลือก engine = `"lama_onnx"` จะไม่มีทางใช้ GPU Server ได้เลย
- แม้จะตั้ง `gpu_inpaint_url` ไว้

**ข้อถกเถียง:**
- **ตั้งใจแบบนี้**: `lama_onnx` = force local only (ไม่ใช้ server)
- **หรือ bug**: ควรให้ `lama_onnx` fallback ไป server ได้

**แนะนำ:** ให้ชัดเจนในชื่อ:
- `lama_onnx` = Local ONNX only (no server)
- `lama` / `lama_manga` = Server → ONNX fallback

---

### ⚠️ Issue #4: Timeout 0.3s ใน `_is_local_lama_cleaner_alive` อาจสั้นเกินไป

**Location:** `inpainter.py:1188-1198`

```python
def _is_local_lama_cleaner_alive(port: int = 2328) -> bool:
    try:
        with urllib.request.urlopen(req, timeout=0.3) as resp:  # ❌ 300ms อาจสั้นไป
            return resp.status == 200
    except:
        return False
```

**ผลกระทบ:**
- GPU Server ที่ slow start (cold boot) อาจไม่ทันตอบใน 300ms
- ระบบจะข้ามไปใช้ ONNX ทันที

**แนะนำ:**
- Health check: `timeout=0.5` (500ms)
- Actual inference: `timeout=75.0` (เหมือนเดิม)

---

### ⚠️ Issue #5: inpaint_server_manager auto-start ไม่มี timeout

**Location:** `inpainter.py:1261-1272`

```python
try:
    from app.services.inpaint_server_manager import inpaint_manager
    inpaint_manager.start_server_if_needed()
    # ❌ ไม่มี timeout → อาจค้างนาน
    for port in (2328, 2322):
        if _is_local_lama_cleaner_alive(port):
            return LamaCleanerClientInpainter(...)
except:
    pass
```

**ผลกระทบ:**
- `start_server_if_needed()` อาจใช้เวลานาน (5-10 วินาที)
- ทำให้การ clean หน้าแรกช้ามาก

**แนะนำ:**
- ใช้ background thread สำหรับ auto-start
- หรือ skip auto-start และให้ผู้ใช้ start manual

---

## 4. Flow Chart: Inpaint Engine Selection

```
User selects engine in Settings
    ↓
┌─────────────────────────────────────┐
│ resolve_inpaint_engine_name()       │
│ Returns: "lama_onnx" / "mat" /      │
│          "lama" / "telea"            │
└──────────────┬──────────────────────┘
               ↓
        ┌──────────────┐
        │ engine_name  │
        └──────┬───────┘
               ↓
    ┌──────────────────────────┐
    │ if engine == "lama_onnx" │───→ _get_lama(force_onnx=True)
    │ elif engine == "mat"     │───→ _get_mat() → fallback _get_lama()
    │ elif engine == "lama"    │───→ _get_lama(custom_url=...)
    │ else (telea)             │───→ None (skip AI inpaint)
    └──────────┬───────────────┘
               ↓
    ┌──────────────────────────────────────────┐
    │ _get_lama(execution_provider, custom_url)│
    └──────────┬───────────────────────────────┘
               ↓
    ┌─────────────────────────────────────────┐
    │ Priority 1: custom_url?                 │──Yes→ LamaCleanerClient(custom_url)
    │                                         │                   ↓ (failed)
    │ Priority 2: Local GPU Server alive?    │──Yes→ LamaCleanerClient(127.0.0.1:2328)
    │                                         │                   ↓ (no server)
    │ Priority 3: Auto-start server?         │──Yes→ start_server_if_needed() → retry
    │                                         │                   ↓ (failed/timeout)
    │ Priority 4: Local ONNX fallback        │──Yes→ LamaONNXInpainter(lama_manga.onnx)
    │                                         │                   ↓ (model not found)
    │ Priority 5: Return None                │──→ Telea fallback in clean_page_text
    └─────────────────────────────────────────┘
```

---

## 5. แนะนำการแก้ไข (Recommended Fixes)

### ✅ Fix #1: ให้ LamaCleanerClient fallback รู้จัก execution_provider

```python
# เพิ่ม parameter ใน _get_fallback_lama_onnx
def _get_fallback_lama_onnx(execution_provider: str | None = None) -> Any | None:
    from app.config import MODELS_DIR
    for alt in (MODELS_DIR / "inpainting" / "lama_manga.onnx", MODELS_DIR / "inpainting" / "lama.onnx"):
        if alt.exists():
            try:
                return LamaONNXInpainter(str(alt), execution_provider=execution_provider)
            except Exception:
                pass
    return None

# แก้ไข LamaCleanerClientInpainter.inpaint()
class LamaCleanerClientInpainter:
    def __init__(self, endpoint_url, execution_provider=None):
        self.endpoint_url = endpoint_url
        self.execution_provider = execution_provider  # เก็บไว้

    def inpaint(self, image_bgr, mask_gray):
        try:
            # ... ส่งไป GPU Server
        except Exception as err:
            fallback = _get_fallback_lama_onnx(self.execution_provider)  # ✅ ส่ง EP
            if fallback:
                return fallback.inpaint(image_bgr, mask_gray)
```

---

### ✅ Fix #2: ล้าง cache เมื่อ custom_url เปลี่ยน

```python
def _get_lama(execution_provider, custom_url, force_onnx):
    global _lama, _lama_checked

    if isinstance(_lama, LamaCleanerClientInpainter):
        # ✅ ตรวจสอบว่า URL เปลี่ยนหรือไม่
        if custom_url and _lama.endpoint_url != custom_url:
            logger.info("Custom GPU URL changed, clearing cache and reconnecting")
            _lama = None
            _lama_checked = False
        elif not custom_url:
            return _lama  # ไม่มี custom URL → ใช้ cached instance
```

---

### ✅ Fix #3: เพิ่ม timeout ให้ _is_local_lama_cleaner_alive

```python
def _is_local_lama_cleaner_alive(port: int = 2328, timeout: float = 0.5) -> bool:
    try:
        req = urllib.request.Request(...)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # ✅ 500ms
            ...
```

---

### ✅ Fix #4: ข้าม auto-start ถ้าใช้เวลานาน

```python
# Option A: Background auto-start (non-blocking)
import threading

def _try_auto_start_server():
    try:
        from app.services.inpaint_server_manager import inpaint_manager
        inpaint_manager.start_server_if_needed()
    except Exception as e:
        logger.debug(f"Background auto-start failed: {e}")

# ใน _get_lama():
if not _lama_checked:
    # ✅ Start server in background (don't block)
    threading.Thread(target=_try_auto_start_server, daemon=True).start()
```

---

## 6. สรุประบบปัจจุบัน

### ✅ จุดแข็ง (Strengths)

1. **Robust Fallback Chain**: GPU Server → ONNX → Telea
2. **Custom URL Support**: รองรับ external GPU servers
3. **Auto-detect Local Server**: ตรวจจับ ports 2328, 2322, 2335
4. **Emergency Fallback**: Telea ไม่มีทางล้มเลย
5. **Strategy Selection**: region / per_block / parallel

### ⚠️ จุดอ่อน (Weaknesses)

1. **Fallback ไม่ได้ใช้ GPU**: `_get_fallback_lama_onnx()` ไม่รับ `execution_provider`
2. **Cache Invalidation**: เปลี่ยน `gpu_inpaint_url` ต้อง restart
3. **Timeout สั้นเกินไป**: 300ms อาจไม่พอสำหรับ cold start
4. **Auto-start Blocking**: `start_server_if_needed()` ทำให้ช้า
5. **Force ONNX ไม่รองรับ Server**: `lama_onnx` ไม่สามารถ fallback ไป server

---

## 7. Action Items

### Priority 1 (Critical):
- [ ] แก้ `_get_fallback_lama_onnx()` ให้รับ `execution_provider`
- [ ] แก้ cache invalidation เมื่อ `custom_url` เปลี่ยน

### Priority 2 (Important):
- [ ] เพิ่ม timeout ของ `_is_local_lama_cleaner_alive` เป็น 500ms
- [ ] ทำ auto-start แบบ non-blocking

### Priority 3 (Nice to have):
- [ ] เพิ่ม retry logic สำหรับ GPU Server (ลองอีกครั้งถ้า timeout)
- [ ] แสดง status ของ GPU Server ใน Settings UI
- [ ] เพิ่ม health check endpoint ใน backend สำหรับ frontend polling

---

## 8. ตัวอย่าง Configuration

### การตั้งค่าแนะนำ:

```json
// สำหรับ GPU แรง (NVIDIA RTX 4060+)
{
  "inpaint_engine": "lama_manga",
  "inpaint_strategy": "parallel",
  "gpu_inpaint_url": "http://127.0.0.1:2328",
  "execution_provider": "CUDA"
}

// สำหรับ GPU ทั่วไป (DirectML)
{
  "inpaint_engine": "lama_manga",
  "inpaint_strategy": "region",
  "execution_provider": "DirectML"
}

// สำหรับ CPU อ่อน
{
  "inpaint_engine": "telea",
  "inpaint_strategy": "per_block"
}

// Force Local ONNX only (ไม่ใช้ server)
{
  "inpaint_engine": "lama_onnx",
  "inpaint_strategy": "per_block",
  "execution_provider": "DirectML"
}
```

---

## 9. Conclusion

**สถานะรวม: ✅ ระบบโดยรวมถูกต้อง แต่มีจุดปรับปรุง**

ระบบ Inpaint ปัจจุบันมี architecture ที่ดี มี fallback ครบถ้วน แต่มีปัญหาเล็กน้อยเกี่ยวกับ:
1. ONNX fallback ไม่ได้ใช้ GPU
2. Cache invalidation ไม่ทันที
3. Timeout อาจสั้นเกินไป

**แนะนำ:** แก้ Priority 1-2 ก่อน จะทำให้ระบบเสถียรและเร็วขึ้นมาก
