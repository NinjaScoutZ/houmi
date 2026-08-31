# Houmi Studio (ほうみ)

> **Next-Generation Manga & Webtoon Translation & Typesetting Desktop Studio**  
> AI-Assisted Text Detection · GPU DirectML OCR · Deep-Learning Background Cleaning · Intelligent Speech Balloon Fitting · Native Photoshop PSD & JSX Export

[![Release](https://img.shields.io/github/v/release/NinjaScoutZ/houmi?color=blue&style=flat-square)](https://github.com/NinjaScoutZ/houmi/releases)
[![Architecture](https://img.shields.io/badge/Architecture-4--Domain%20Clean%20Worktree-emerald?style=flat-square)](#-repository-architecture)
[![Python](https://img.shields.io/badge/Backend-FastAPI%20%7C%20PyWebView-yellow?style=flat-square)](backend/)
[![Rust](https://img.shields.io/badge/PSD%20Engine-Rust%20%28houmi--psd--cli%29-orange?style=flat-square)](houmi-psd-cli/)

---

## 🏛️ Repository Architecture

The project is structured according to the **4-Domain Clean Architecture** to guarantee absolute isolation between active workspaces, client runtimes, and customer release distributions:

```text
E:\houmi/
├── workspaces/              # 1️⃣ Code & UI Workspaces (Branch / Version Isolated)
│   ├── v1.0.4/              #     Production Staging Workspace
│   ├── v1.0.5/              #     Current Stable Production Workspace
│   └── v2.0.0-dev/          #     Next-Gen Experimental Workspace
│
├── releases/                # 2️⃣ Single-Source Release Packages & Manifests
│   └── v1.0.5/
│       ├── manifest.json    #     Canonical SHA-256 metadata
│       ├── RELEASE_NOTES.md #     Full changelog & highlights
│       └── patches/         #     Compiled patch zip distribution
│
├── deploy/                  # 3️⃣ Release & Distribution Tooling
│   └── build_release_patch.py  #  Deterministic single-source patch builder
│
├── backend/                 # 4️⃣ Backend Core Services & Fallback Engine
│   └── app/                 #     FastAPI Routes, AI Handlers, SQLite Engine
│
├── houmi-psd-cli/           # Standalone High-Performance Rust PSD CLI
├── docs/                    # Architecture Specs & User Documentation
├── design-system/           # Design tokens & UI specifications
└── CHANGELOG.md             # Complete Semantic Versioning changelog
```

---

## 🚀 Quick Start (Running v1.0.5 Workspace)

To launch the 100% self-contained **Houmi Studio v1.0.5**:

```cmd
cd workspaces\v1.0.5
Launch-v1.0.5.bat
```

The launcher will:
1. Initialize the workspace environment (`HOUMI_APP_DIR`, `HOUMI_FRONTEND_DIST`, `HOUMI_DATA_DIR`).
2. Start the local Python AI Engine on port `4000`.
3. Launch the native GPU-accelerated desktop window.

---

## 📦 Building Customer Releases & Patches

To package a new release from a designated workspace with automatic SHA-256 manifest generation:

```bash
# Package v1.0.5 into releases/v1.0.5/patches/
python deploy/build_release_patch.py --worktree v1.0.5 --patch-tag p1
```

Strict allowlist packaging ensures zero `.env`, test files, or database caches leak into customer bundles.

---

## 🛠️ Key Features

- **5-Step Automated AI Pipeline**: 1-Click Detect ➔ OCR ➔ Mask ➔ Clean ➔ AI Typeset.
- **DirectML GPU OCR**: RapidOCR integration for Japanese, Chinese, Korean, and English.
- **Smart Balloon Boundary Clamping**: Adaptive speech bubble contour segmentation with zero text clipping.
- **Multi-Key Priority Pool**: Intelligent AI API key failover on rate limit (429).
- **ExtendScript (.JSX) & Rust PSD Generator**: Generates native Photoshop documents with editable text layers.

---

## 📄 License & Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history and release notes.
