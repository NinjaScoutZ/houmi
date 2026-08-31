# Project Context

## Project Overview
Houmi is a manga/comic translation and typesetting tool with a React/Vite frontend and a Python/FastAPI backend.

## Key Requirements & Scope
1. **R1 UI/UX Sub-toolbar**: Eliminate duplicate settings between Sub-toolbar, Canvas control overlays, and Global Settings modal (Font templates, Min/Max font size, Line height, Padding).
2. **R2 OCR Engines**: Categorize into Local Engines vs AI Cloud vs Local VLM API; disable/hide unconfigured/unusable options dynamically.
3. **R3 Backend Schemas**: Clean up `service.py`, `blocks.py`, `settings.py`, `schemas.py`; remove redundant keys, preserve backward compatibility for old project payloads.
4. **R4 Test Suite & Quality**: Ensure 100% test parity for pytest, vitest, and tsc --noEmit. Ensure rendering consistency between canvas live preview and export.
