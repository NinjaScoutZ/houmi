# Font Template Anti-Alias Setting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `anti_alias` font smoothing control to Font Templates in Font Template Editor UI, defaulting to `'sharp'`.

**Architecture:** Extend `TextTemplate` interface in `frontend/src/utils/textTemplates.ts` with `anti_alias?: TextAntiAlias`, add an anti-alias selector inside the Typography section of `ProjectPresetModal` in `frontend/src/App.tsx`, and sync `anti_alias` when applying templates/presets.

**Tech Stack:** TypeScript, React, Vite, Tailwind CSS, FastAPI.

## Global Constraints

- Default `anti_alias` for Font Templates must be `'sharp'`.
- Valid values: `'smooth'`, `'crisp'`, `'strong'`, `'sharp'`, `'none'`.

---

### Task 1: Update `TextTemplate` Interface & Default Template Definitions

**Files:**
- Modify: `frontend/src/utils/textTemplates.ts:6-42`
- Test: `frontend/src/tests/textTemplates.test.ts`

**Interfaces:**
- Produces: `anti_alias?: 'smooth' | 'crisp' | 'strong' | 'sharp' | 'none'` in `TextTemplate`

- [ ] **Step 1: Add `anti_alias` property to `TextTemplate` interface**
Add `anti_alias?: 'smooth' | 'crisp' | 'strong' | 'sharp' | 'none';` to `TextTemplate` in `frontend/src/utils/textTemplates.ts`.

- [ ] **Step 2: Set default anti_alias to `'sharp'` in DEFAULT_TEXT_TEMPLATES**
Ensure built-in templates have `anti_alias: 'sharp'`.

- [ ] **Step 3: Run frontend tests**
Run: `npm --prefix frontend test`
Expected: PASS

---

### Task 2: Add Anti-Alias Control UI in Font Template Customizer

**Files:**
- Modify: `frontend/src/App.tsx:6585-6635`

- [ ] **Step 1: Add Anti-Alias dropdown select in Typography section**
In `frontend/src/App.tsx` (under `templateLayerStyleTab === 'type'`), add a label and select dropdown for `anti_alias` allowing choices: `sharp`, `smooth`, `crisp`, `strong`, `none`.

- [ ] **Step 2: Test frontend build**
Run: `npm run build` inside `frontend/`
Expected: PASS with 0 errors

---

### Task 3: Build & Release Patch v0.3.8

**Files:**
- Modify: `backend/scripts/build_patch.py`
- Modify: `data/update_manifest.json`
- Modify: `backend/data/update_manifest.json`

- [ ] **Step 1: Rebuild Rust CLI**
Run: `cargo build --release` in `manga-psd-cli/`

- [ ] **Step 2: Build frontend dist**
Run: `npm run build` in `frontend/`

- [ ] **Step 3: Create patch zip**
Run: `python backend/scripts/build_patch.py`

- [ ] **Step 4: Update version manifest to v0.3.8**
Set `latest_version` to `"0.3.8"` in `data/update_manifest.json` and `backend/data/update_manifest.json`.
