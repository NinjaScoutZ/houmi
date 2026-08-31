# 🐛 วินิจฉัย: ทำไมกด Pipeline Clean แล้วค้างที่หน้าแรก

**วันที่**: 2026-08-17  
**อาการ**: กดปุ่ม Clean แล้ว UI แสดง "กำลังคลีนภาพเฉพาะบริเวณเบื้องหลัง…" แต่ค้างไม่จบ

---

## 📊 สิ่งที่ตรวจสอบแล้ว

### ✅ Backend ทำงานได้
```log
2026-08-17 22:00:38,773 [INFO] houmi-parallel-inpaint: Starting parallel inpainting with 4 workers for 9 regions
2026-08-17 22:00:38,806 [INFO] houmi-parallel-inpaint: Parallel inpainting completed: 9/9 regions
```

**Backend จบแล้ว!** แต่ frontend ไม่รู้

---

## 🔍 สาเหตุที่เป็นไปได้

### 1. **WebSocket message "success" ไม่ถูกส่ง**
Backend code (pipeline.py:1978-1982):
```python
clean_page_text(page_id, task_db, engine_override=engine)
logger.info("Completed background page clean page=%s", page_id)
ws_manager.broadcast_sync(project_id, {
    "type": "mask_progress", "status": "success", "page_id": page_id,
})
```

**ปัญหาที่เป็นไปได้**:
- ❌ `clean_page_text()` throw exception → ข้าม broadcast
- ❌ `ws_manager.broadcast_sync()` ล้มเหลวเงียบ ๆ
- ❌ `project_id` เป็น None → broadcast ไปไม่ถึง client

---

### 2. **Frontend ไม่ได้รับ WebSocket message**
Frontend code (App.tsx:2023-2037):
```typescript
} else if (lastMessage.type === 'mask_progress') {
  const { status, page_id, error } = lastMessage;
  if (status === 'running') {
    setStatus('กำลังคลีนภาพเฉพาะบริเวณเบื้องหลัง…', true);
  } else if (status === 'success') {
    setStatus('คลีนภาพเฉพาะบริเวณเสร็จสมบูรณ์เรียบร้อย', false);
    setCleanPreviewRevision(Date.now());
    showToast('อัปเดตภาพ Clean ล่าสุดเรียบร้อยแล้ว (Reclean Success)', 'success');
```

**ปัญหาที่เป็นไปได้**:
- ❌ WebSocket disconnected
- ❌ Message มา แต่ `lastMessage.type` ไม่ตรง
- ❌ `status !== 'success'` (เช่น `"Success"` หรือ `"SUCCESS"`)

---

### 3. **`clean_page_text()` throw exception แต่ไม่ล็อก**

Backend inpainter.py:1908-1910:
```python
if engine_name != "telea" and inpaint_service is None:
    logger.warning("Inpainting engine '%s' unavailable; using Telea fallback", engine_name)
```

**Log แสดง**:
```
[WARNING] houmi-inpainter: Inpainting engine 'manga_cleaner' unavailable; using Telea fallback
```

แต่ **Telea ใช้งานได้** และ **จบสมบูรณ์** → ไม่น่าจะเป็นสาเหตุ

---

## 🎯 สาเหตุที่น่าจะเป็นมากที่สุด

### **Exception ใน `clean_page_text()` ทำให้ข้าม broadcast "success"**

```python
try:
    clean_page_text(page_id, task_db, engine_override=engine)  # ← อาจ throw exception ที่นี่
    logger.info("Completed background page clean page=%s", page_id)  # ← ไม่ถึงบรรทัดนี้
    ws_manager.broadcast_sync(project_id, {
        "type": "mask_progress", "status": "success", "page_id": page_id,
    })  # ← ไม่ถึงบรรทัดนี้
except Exception as exc:
    logger.exception("Background page clean failed page=%s", page_id)  # ← ล็อก error
    if project_id:
        ws_manager.broadcast_sync(project_id, {
            "type": "mask_progress", "status": "error", "page_id": page_id,
            "error": str(exc),
        })
```

**ถ้า exception เกิดหลัง inpainting เสร็จ** → log แสดง "completed" แต่ Python throw exception → ไม่ส่ง "success"

---

## 🔧 วิธีแก้ไข

### วิธีที่ 1: ตรวจสอบ Backend Log
```bash
tail -100 backend/logs/server.log | grep -A 10 "clean_page_text\|mask_progress\|Background page clean"
```

หา:
- `"Completed background page clean"` ← ถ้ามี = broadcast ควรส่ง
- `"Background page clean failed"` ← ถ้ามี = exception เกิด

---

### วิธีที่ 2: เพิ่ม Logging ใน `ws_manager.broadcast_sync`
```python
# backend/app/ws_manager.py
def broadcast_sync(self, project_id: str, message: dict):
    logger.info(f"📡 Broadcasting to project {project_id}: {message}")
    # ... existing code
```

---

### วิธีที่ 3: เพิ่ม Timeout ใน Frontend
```typescript
// Set timeout fallback
const cleanTimeout = setTimeout(() => {
  setStatus('Clean completed (timeout fallback)', false);
  setCleanPreviewRevision(Date.now());
  showToast('Clean may have completed - refreshing...', 'info');
  if (activePage) selectPage(activePage.id);
}, 30000); // 30 seconds

// Clear timeout when success received
if (status === 'success') {
  clearTimeout(cleanTimeout);
  // ... existing code
}
```

---

### วิธีที่ 4: เพิ่ม Polling Fallback
ถ้า WebSocket ไม่มา → Poll API ตรวจสอบว่า inpainted_image_path อัปเดตแล้วหรือยัง

```typescript
// Poll every 2 seconds while "running"
useEffect(() => {
  if (isProcessing && activePage) {
    const interval = setInterval(async () => {
      const updated = await fetchPage(activePage.id);
      if (updated.inpainted_image_path) {
        setStatus('Clean completed!', false);
        setCleanPreviewRevision(Date.now());
        clearInterval(interval);
      }
    }, 2000);
    return () => clearInterval(interval);
  }
}, [isProcessing, activePage]);
```

---

## 🚀 แนวทางแก้ปัญหาเร่งด่วน

### ✅ ทำทันที: Reload หน้าจอ
กด **F5** หรือ **Refresh** → ภาพ clean จะโหลดมาแสดง (เพราะ backend จบแล้ว)

### ✅ แก้ใน Code (Quick Fix):
เพิ่ม **timeout + auto-refresh** ใน frontend:

```typescript
// App.tsx - เพิ่มใน mask_progress handler
if (status === 'running') {
  setStatus('กำลังคลีนภาพเฉพาะบริเวณเบื้องหลัง…', true);
  
  // Auto-refresh after 30s if no success message
  setTimeout(() => {
    if (activePage?.id === page_id) {
      setStatus('Refreshing page...', false);
      selectPage(page_id);  // Force refresh
    }
  }, 30000);
}
```

---

## 📝 Action Items

1. ✅ ตรวจสอบ backend log หา exception
2. ✅ เพิ่ม logging ใน `ws_manager.broadcast_sync`
3. ✅ เพิ่ม timeout fallback ใน frontend
4. ⚠️ ทดสอบ WebSocket connection stability
5. ⚠️ เพิ่ม health check indicator ใน UI

---

## 💡 สรุป

**ปัญหาหลัก**: Backend จบแล้ว แต่ frontend ไม่ได้รับ WebSocket message "success"

**สาเหตุที่เป็นไปได้สูงสุด**: 
1. Exception เกิดหลัง inpainting จบ → ข้าม broadcast
2. WebSocket message สูญหาย
3. Frontend ไม่ handle message ถูกต้อง (แต่โค้ดดูโอเค)

**แก้ชั่วคราว**: กด Refresh หน้าเว็บ  
**แก้ถาวร**: เพิ่ม timeout + polling fallback + better logging
