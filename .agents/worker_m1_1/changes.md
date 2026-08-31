# Changes Report — Milestone 1: R1 UI/UX & Sub-toolbar Consolidation

**Agent**: `worker_m1_1`  
**Date**: 2026-08-03  
**Working Directory**: `e:\houmi\.agents\worker_m1_1`  

---

## 1. Summary of Changes

### A. Modular Component Extraction & Reconciliation
- **`frontend/src/components/PipelineToolbar.tsx`**:
  - Reconciled the monolithic inline sub-toolbar from `App.tsx` and standalone `PipelineToolbar.tsx` into a modular, clean sub-toolbar.
  - Supports OCR mode controls (OCR engine selector with categorized groups for Cloud AI vs Local VLM vs Local Offline engines, AI spellcheck toggle, Live Mask toggle, ImageTrans options) and Typeset mode controls (B+ Typeset badge, decision status counters `OK`/`DEF`/`REV`, Style Judge page, Undo Auto Style, Suggest Only, Recompute Layout, Review Queue filter toggle, Clear Sel / Clear Page).
  - Maintained 100% backward compatibility with `PipelineToolbarProps` so diagnostic tests (`diagnosticsToolbar.test.ts`) and pipeline actions continue to pass.

- **`frontend/src/components/SettingsModal.tsx`**:
  - Reconciled the 1200-line inline Global Settings modal from `App.tsx` into `SettingsModal.tsx`.
  - Implemented multi-category navigation (`AI Detection & Scan`, `Typography & Style`, `Role / Font Templates`, `Cleanup Pipeline`, `Performance & Hardware`, `Workspace Directories`, `Keyboard Shortcuts`) and unified search.
  - Integrated `useProjectStore` for live project settings sync and store updates.

- **`frontend/src/components/SidebarInspector.tsx`**:
  - Reconciled inline typography controls and standalone `SidebarInspector.tsx` into a single modular component.
  - Supports single- and multi-selection editing for Font Family (`FontSelector`), Font Size (px) + Auto-Fit pill, Style (Bold/Italic), Alignment (Left/Center/Right), Fill Color (`ColorField`), Photoshop-style Character controls (Leading `line_height_ratio` and Tracking `letter_spacing`), Preset Chips, Font Templates tab, and OCR Source / Thai Translation editor.

- **`frontend/src/App.tsx`**:
  - Refactored `App.tsx` to remove monolithic inline JSX for sub-toolbar, global settings modal, and typography inspector controls.
  - Imported and rendered `<PipelineToolbar />`, `<SettingsModal />`, and `<SidebarInspector />`.

---

## 2. Elimination of Duplicate & Redundant Controls

1. **Font Templates**:
   - Management (creating, editing font stacks, colors, stroke, glow, shadow) is consolidated in `SettingsModal` under `Role / Font Templates`.
   - Preset application is consolidated in `SidebarInspector` (Templates tab) and `TypographyPresetChips`.
2. **Min/Max Font Sizes**:
   - Clarified scope between template-level bounds (defined inside `Role / Font Templates`) and project-wide global fallbacks.
   - Labeled global fallback inputs as "Global Fallback Min Font Size (px)" and "Global Fallback Max Font Size (px)" in `SettingsModal` under Typography to avoid user confusion.
3. **Line Height & Letter Spacing**:
   - Consolidated character pair fields in `SidebarInspector` for `Leading (Line)` -> `extra_metadata.line_height_ratio` and `Tracking (Spacing)` -> `extra_metadata.letter_spacing` / `tracking`.
4. **Padding & Margin Controls**:
   - Maintained text box inner padding under `TextTemplate` / `extra_metadata` and background cleanup context padding under `Cleanup Pipeline` in `SettingsModal`.

---

## 3. Typesetting Parity Verification

- Verified that text properties (font family, size, line height ratio, padding, stroke color/width) set in `SidebarInspector` and `SettingsModal` update `TextBlock.font_size`, `font_family`, and `extra_metadata` (`line_height_ratio`, `letter_spacing`, `padding`, `stroke_color`, `stroke_width`).
- Verified that live canvas rendering in `Canvas.tsx` (using `fabricAdapter.ts`, `fabricStroke.ts`, and `fabricGlow.ts`) produces high-res canvas captures that match the canonical backend PNG/PSD export pipeline.

---

## 4. Verification Results

 executed in `e:\houmi\frontend`:

1. **TypeScript Typecheck (`npx tsc --noEmit`)**:
   - **Result**: PASSED (exit code 0, 0 errors)

2. **Frontend Test Suite (`npx vitest run`)**:
   - **Result**: PASSED
   - **Summary**: 16 passed test files out of 16, 113 passed tests out of 113
   - **Test Files**:
     - `src/tests/blockUpdateTracker.test.ts`
     - `src/tests/colorField.test.ts`
     - `src/tests/textTemplates.test.ts`
     - `src/tests/clientProfiles.test.ts`
     - `src/tests/fabricAdapter.test.ts`
     - `src/tests/layerManager.test.ts`
     - `src/tests/projectStore.test.ts`
     - `src/tests/diagnosticsToolbar.test.ts`
     - `src/tests/typesetting.test.ts`
     - `src/tests/autoStyleAndStroke.test.ts`
     - `src/tests/decisionStatus.test.ts`
     - `tests/scaling.test.ts`
     - `src/tests/settingsModal.test.ts`
     - `src/tests/canvasPerformance.test.ts`
     - `src/tests/maskEditorAndCanvasUX.test.ts`
     - `src/tests/taskQueueVisualizer.test.ts`
