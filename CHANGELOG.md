# Houmi Studio — Release Changelog

All notable changes to Houmi Studio are documented in this file following the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) standard and [Semantic Versioning](https://semver.org/).

---

## [v1.0.5] - 2026-08-31 (Stable Production Release)

### 🏛️ Architecture & Workspace Isolation
- **4-Domain Clean Architecture**: Separated repository into `workspaces/` (code), `runtime/` (execution data), `releases/` (customer packages), and `shared/` (AI models & dependencies).
- **Deterministic Frontend Resolver**: Replaced non-deterministic file timestamp (`mtime`) sorting in `main.py` with strict 4-tier hierarchy bound to `HOUMI_FRONTEND_DIST`.
- **100% Self-Contained Launchers**: Redesigned `Launch-v1.0.5.bat` and `Launch-v1.0.4.bat` to run locally via `%~dp0` without touching root paths or executing cross-folder copies.
- **Single-Source Release Builder**: Added `deploy/build_release_patch.py` with strict allowlists, generating single release zip packages and canonical `manifest.json` with SHA-256 verification.
- **Legacy Quarantine**: Quarantined legacy frontends and test previews into `archive/legacy-ui/` to prevent path collisions.

### ✨ AI & Translation Pipeline
- **Multi-Key Priority & Auto-Failover Pool**: Intelligent API key pooling with priority weighting and automatic fallback on rate limit (429).
- **Gemini Quota Exceeded Protection**: Immediate graceful cancellation and user notification on quota exhaustion instead of indefinite retry loops.
- **Text Engine Mode & ExtendScript (.JSX) Integration**: Consolidated Photoshop ExtendScript formatters with support for both Paragraph and Point Text layers.
- **Single-Screen Combined Export Scope**: Unified export dialog supporting Current Page and Entire Project export in a single interface.
- **Photoshop Dock Rail Anchored Flyout**: Floating text formatting controls firmly anchored to the Photoshop dock rail sidebar.

---

## [v1.0.4] - 2026-08-20 (Production Staging)

### ✨ Core Features
- **GPU DirectML & RapidOCR**: Native GPU-accelerated OCR with support for Chinese (zh), Korean (ko), Japanese (ja), and English (en).
- **Character Studio & Color Studio**: Rich typography inspector with real-time Fill, Stroke, Shadow, and Glow controls.
- **5-Step Automated AI Pipeline**: Integrated 1-Click execution for Detect ➔ OCR ➔ Mask ➔ Clean ➔ AI Font Typeset.
- **Smart Stitch (AI Webtoon)**: Automated long-strip webtoon splitting, resizing, and bounding-box preservation.
- **Standalone Rust PSD CLI Engine**: High-performance multi-layer Photoshop PSD generator with non-destructive text styling.

---

## [v1.0.1] - 2026-08-18 (Incremental Update)

### 🎨 Masking & Inpainting Enhancements
- **ImageTrans Mask Engine**: High-precision connected component binarization for clean text edge extraction.
- **Smart Balloon V15 Zero Distortion**: Enhanced speech bubble contour fitting with boundary clamping and tail rejection.
- **Batch Pipeline Timeout Fix**: Cleaned up uncancelled timeout toasts in batch translation mode.
- **Persistent Block Selection**: Maintained active text block selection through OCR rescan passes.

---

## [v1.0.0] - 2026-08-16 (Initial Desktop Release)

### 🚀 Initial Release
- **Offline Desktop Studio**: Dual-engine architecture featuring FastAPI local server paired with native GPU-accelerated PyWebView window.
- **LaMa Manga Inpainting Engine**: Deep-learning background cleaning and text erasing.
- **Thai Typography & Word Wrapping**: Dictionary-assisted line-breaking tailored for Thai comic typography.
- **Local SQLite Database**: Multi-project asset management and serialized layer tracking.
