# 🏛️ HOUMI STUDIO - FULLSTACK WORKSPACE ARCHITECTURE

---

## 📁 โครงสร้าง `workspaces/`

```
e:\houmi\
│
├── workspaces\
│   ├── v2.0.0-dev\                  🌟 Next-Gen Luxury Studio
│   │   ├── frontend\                React + Vite + Fabric.js
│   │   ├── backend\                 Python FastAPI (AI Pipeline)
│   │   ├── Launch-v2.0.0-dev.bat     Rust Desktop Shell (wry+tao)
│   │   └── Start-v2.0.0-dev-Dev.bat  Fullstack Dev Server
│   │
│   ├── v1.0.4\                      📦 Staging Release
│   │   ├── frontend\                Google Drive dist bundle
│   │   ├── backend\                 Python FastAPI
│   │   └── Launch-v1.0.4.bat         Rust Desktop Shell (wry+tao)
│   │
│   └── v1.0.0\                      🏛️ Classic Stable
│       ├── frontend\                UI คลาสสิก
│       ├── backend\                 Python FastAPI
│       └── Launch-v1.0.0.bat         Python pywebview (ตัวเก่า)
│
├── backend-rust\                    Rust Desktop Shell (wry+tao)
│   ├── src\main.rs                  Spawn Python backend + WebView2 window
│   └── target\release\houmi-backend.exe  Compiled binary (13MB)
│
├── backend\                         Python AI Backend (FastAPI + DirectML)
│
├── Launch-v2.0.0-NextGen.bat        🚀 ทางลัด Root
├── Launch-v1.0.4-Staging.bat        📦 ทางลัด Root
├── Launch-v1.0.0-Classic.bat        🏛️ ทางลัด Root
└── Start-Dev-Studio.bat             🎛️ เมนูเลือกเวอร์ชัน
```

---

## ⚡ สรุปสถาปัตยกรรม Desktop Shell

| เวอร์ชัน | Desktop Shell | AI Backend | Frontend |
|---|---|---|---|
| **v2.0.0-dev** | **Rust** `wry` + `tao` (`houmi-backend.exe`) | Python FastAPI | Next-Gen Luxury + Photoshop Balloon |
| **v1.0.4** | **Rust** `wry` + `tao` (`houmi-backend.exe`) | Python FastAPI | Google Drive Staging |
| **v1.0.0** | **Python** `pywebview` (`run_desktop.py`) | Python FastAPI | Classic Monolithic |

---

## 🛡️ กฎ
- แก้โค้ดใหม่ใน `workspaces/v2.0.0-dev/` เท่านั้น
- v1.0.4 และ v1.0.0 ล็อกไว้เป็น Reference
- ตั้งแต่ v1.0.4 ขึ้นไป ใช้ Rust Desktop Shell เท่านั้น ไม่ใช้ Python pywebview
