# 🚀 Quick Fix: Clean Pipeline Stuck - Add Timeout Fallback

## สรุปปัญหา
กด Clean แล้ว UI ค้างที่ "กำลังคลีนภาพเฉพาะบริเวณเบื้องหลัง…" ไม่จบ

## สาเหตุ
WebSocket message "success" ไม่ถึง frontend → UI ไม่รู้ว่าจบแล้ว

## วิธีแก้ Quick Fix
เพิ่ม **timeout + auto-refresh** เมื่อค้างเกิน 30 วินาที

---

## แก้ไขไฟล์: frontend/src/App.tsx

หาบรรทัดนี้ (ประมาณ line 2023-2037):

```typescript
} else if (lastMessage.type === 'mask_progress') {
  const { status, page_id, error } = lastMessage;
  if (status === 'running') {
    setStatus('กำลังคลีนภาพเฉพาะบริเวณเบื้องหลัง…', true);
  } else if (status === 'success') {
    setStatus('คลีนภาพเฉพาะบริเวณเสร็จสมบูรณ์เรียบร้อย', false);
    setCleanPreviewRevision(Date.now());
    showToast('อัปเดตภาพ Clean ล่าสุดเรียบร้อยแล้ว (Reclean Success)', 'success');
    if (activePage?.id === page_id) {
      selectPage(page_id);
    }
  } else if (status === 'error') {
    setStatus(`คลีนภาพเฉพาะบริเวณไม่สำเร็จ: ${error}`, false);
    showToast(`คลีนภาพเฉพาะบริเวณไม่สำเร็จ: ${error}`, 'error');
  }
}
```

แก้เป็น:

```typescript
} else if (lastMessage.type === 'mask_progress') {
  const { status, page_id, error } = lastMessage;
  if (status === 'running') {
    setStatus('กำลังคลีนภาพเฉพาะบริเวณเบื้องหลัง…', true);
    
    // ✅ FIX: Auto-refresh after 30s if WebSocket message lost
    setTimeout(() => {
      setStatus('Refreshing page (WebSocket timeout)...', false);
      if (activePage?.id === page_id) {
        selectPage(page_id);
        showToast('Clean may have completed - page refreshed', 'info');
      }
    }, 30000);
    
  } else if (status === 'success') {
    setStatus('คลีนภาพเฉพาะบริเวณเสร็จสมบูรณ์เรียบร้อย', false);
    setCleanPreviewRevision(Date.now());
    showToast('อัปเดตภาพ Clean ล่าสุดเรียบร้อยแล้ว (Reclean Success)', 'success');
    if (activePage?.id === page_id) {
      selectPage(page_id);
    }
  } else if (status === 'error') {
    setStatus(`คลีนภาพเฉพาะบริเวณไม่สำเร็จ: ${error}`, false);
    showToast(`คลีนภาพเฉพาะบริเวณไม่สำเร็จ: ${error}`, 'error');
  }
}
```

---

## ทดสอบ
1. Build frontend ใหม่
2. กด Clean
3. หลังจาก 30 วินาที → ควรจะ auto-refresh และแสดงภาพ clean

---

## Better Fix (ทำทีหลัง)
1. เพิ่ม logging ใน ws_manager.broadcast_sync
2. เพิ่ม WebSocket reconnect logic
3. เพิ่ม health check indicator
