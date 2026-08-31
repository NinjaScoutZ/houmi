# Baseline Analysis Report: Frontend UI Layout & Settings Audit

**Target Project**: Houmi (Frontend)  
**Investigator**: explorer_m0_1  
**Date**: 2026-08-03  
**Working Directory**: `e:\houmi\.agents\explorer_m0_1`

---

## Executive Summary

This audit provides a comprehensive investigation of Houmi's Frontend UI layout components, settings definitions and rendering locations, state management structure, live preview vs export integration, and baseline test suite status.

### Key Finding
The frontend codebase exhibits a dual-structure pattern:
1. **Primary Operational UI**: Implemented directly as inline JSX inside `App.tsx` (6,852 lines).
2. **Orphaned Standalone Components**: Located in `src/components/` (e.g. `SettingsModal.tsx`, `SidebarInspector.tsx`, `PipelineToolbar.tsx`) which are not imported or rendered by `App.tsx`, leading to duplicate control definitions and maintenance ambiguity.

Both automated test suites (`npx vitest run`) and TypeScript typecheck (`npx tsc --noEmit`) pass cleanly with 100% success baseline.

---

## 1. UI Layout & Component Structure Audit

### 1.1 Architecture & Component Mapping

| Component Area | Inline Implementation in `App.tsx` | Standalone File in `src/components/` | Active Status in App |
|---|---|---|---|
| **Global Settings Modal** | Lines 5190–6470 (`showGlobalSettingsModal`) | `src/components/SettingsModal.tsx` (234 lines) | Inline only |
| **Sub-toolbar** | Lines 2850–3044 (under top `<nav>`) | `src/components/PipelineToolbar.tsx` (164 lines) | Inline only |
| **Sidebar Inspector / Typography** | Lines 3360–3634 (Floating Typography Inspector) & Lines 3695–4500 (Right Panel) | `src/components/SidebarInspector.tsx` (182 lines) | Inline only |
| **Canvas & Overlays** | Implemented via `<Canvas />` component call (Line 3322) | `src/components/Canvas.tsx`<br>`src/components/CanvasAlignmentToolbar.tsx`<br>`src/components/CanvasContextMenu.tsx` | Active & Imported |
| **Preset Chips & Font Selector** | Inline template buttons & font dropdowns | `src/components/TypographyPresetChips.tsx`<br>`src/components/FontSelector.tsx` | Components exist; `FontSelector` used in `SidebarInspector` |

---

### 1.2 Detailed Component Breakdown

#### A. Sub-toolbar (`App.tsx` Lines 2850–3044)
- **OCR Mode Controls**:
  - OCR Engine selector (`gemini`, `glm`, `deepseek`, `paddleocr`).
  - `AI spellcheck` checkbox (`aiOcrCorrection`).
  - `Live Mask` overlay checkbox (`liveMaskOverlay`).
  - Processing grid: `Vertical to horizontal`, `Strip furigana`, `Use Chinese punctuation`, `Remove spaces`, `Auto OCR`, `Auto remove line breaks`.
- **Typeset Mode Controls**:
  - `B+ Typeset` badge & decision counters (`OK`, `DEF`, `REV`).
  - Action buttons: `STYLE JUDGE PAGE`, `UNDO AUTO STYLE`, `SUGGEST ONLY`, `RECOMPUTE LAYOUT`, `REVIEW QUEUE`, `CLEAR SEL`, `CLEAR PAGE`.
- **Redundancy with `PipelineToolbar.tsx`**: `PipelineToolbar.tsx` defines step buttons (`Detect`, `OCR`, `Inpaint`, `Font Judge`, `Typeset`, `Sort RTL`, `Auto All`, Backend badge, Batch, Settings, Export). `App.tsx` does NOT import `PipelineToolbar.tsx`.

#### B. Canvas Control Overlays
- **`Canvas.tsx` (`src/components/Canvas.tsx`)**:
  - Renders interactive Fabric.js canvas (`useFabricCanvas`).
  - Manages zoom controls, bottom page navigator, inline `<textarea>` overlay for double-click text editing.
  - Implements canvas render capture hook (`getCanvasRenderCapture`) registered in Zustand store.
- **`CanvasAlignmentToolbar.tsx` (`src/components/CanvasAlignmentToolbar.tsx`)**:
  - Standalone top floating bar when 2+ blocks are selected.
  - Controls: `Merge Blocks`, `Align Left`, `Center`, `Right`, `Top`, `Distribute`.
- **`CanvasContextMenu.tsx` & Inline Context Menus**:
  - Right-click canvas context menu (`Run OCR`, `Clean Mask`, `Auto-Fit Font`, `Visibility`, `Lock`, `Z-Index order`, `Delete`).
  - Duplicate context menu rendered inline in `App.tsx` (Lines 3636–3664) for right panel layer list.

#### C. Global Settings Modal (`App.tsx` Lines 5190–6470)
- Categories in sidebar:
  1. `AI Detection & Scan`: Avoid breaking words, restrain within image, infer direction, convert vertical.
  2. `Balloon Detection Options`: YOLO model selection, expand after detection, model params priority.
  3. `OCR Engine & Scanning`: Auto OCR, binary threshold, auto compute threshold.
  4. `Typography & Style`: Rich text toggle, CJK vertical engine.
  5. `Font Style Defaults`: Default template selector, lock box translation, match source font size, source font scale, auto font resize, Min Font Size, Max Font Size.
  6. `Role / Font Templates`: Interactive template editor (add/delete role, template name, semantic tag, font family, default size, min size, max size, bold/italic, alignment, leading, tracking, fill color, stroke width/color, outer glow, drop shadow).
  7. `Cleanup Pipeline`: Inpaint engine selection, context padding.
  8. `Performance`: Performance profile selection (Eco, Balanced, Quality, Custom), preview width, typesetting candidates, OCR workers, GPU preference.
  9. `Workspace Directories & Keyboard Shortcuts`.

---

## 2. Settings Mapping & Render Locations

| Setting Parameter | Primary Definition File | Rendering & Control Locations in UI |
|---|---|---|
| **Font Templates** | `src/utils/textTemplates.ts` (`DEFAULT_TEXT_TEMPLATES`) | 1. Global Settings Modal -> `Role / Font Templates` (`App.tsx:5433`)<br>2. Floating Inspector -> `Templates` tab (`App.tsx:3585`)<br>3. Right Panel -> Layer List preset buttons (`App.tsx:3789`) |
| **Min / Max Font Sizes** | 1. Per-template: `TextTemplate` in `textTemplates.ts`<br>2. Global: `settingsMinFontSize` & `settingsMaxFontSize` in `App.tsx` | 1. Global Settings Modal -> `Role / Font Templates` inputs (`App.tsx:5582`)<br>2. Global Settings Modal -> `Font Style Defaults` (`App.tsx:5932–5956`)<br>3. `Canvas.tsx` auto-fit calculation (`line 2517`) |
| **Line Height (Leading)** | `line_height_ratio` in `TextTemplate` & `extra_metadata` | 1. Global Settings Modal -> `Role / Font Templates` leading input (`App.tsx:5585`)<br>2. Floating Inspector -> `Leading (Line)` input (`App.tsx:3536–3546`) |
| **Tracking (Letter Spacing)** | `letter_spacing` in `TextTemplate` & `extra_metadata` | 1. Global Settings Modal -> `Role / Font Templates` tracking input (`App.tsx:5586`)<br>2. Floating Inspector -> `Tracking (Spacing)` input (`App.tsx:3555–3568`) |
| **Padding** | 1. Text Box Padding: `padding` in `TextTemplate`<br>2. Inpaint Context Padding: `settingsInpaintContextPadding` in `App.tsx` | 1. Global Settings Modal -> `Cleanup Pipeline` (`inpaint_context_padding`)<br>2. Fabric.js text rendering adapter (`fabricAdapter.ts`) |

---

## 3. Duplicate Setting Inputs & Redundancy Analysis

```
+-----------------------------------------------------------------------------------+
|                              DUPLICATE CONTROLS MATRIX                             |
+--------------------------+----------------------------+---------------------------+
| Control Category         | Location A                 | Location B                |
+--------------------------+----------------------------+---------------------------+
| Global Settings Modal    | App.tsx (inline, L5190)    | src/components/           |
|                          |                            |   SettingsModal.tsx       |
| Sub-toolbar              | App.tsx (inline, L2850)    | src/components/           |
|                          |                            |   PipelineToolbar.tsx     |
| Sidebar Inspector        | App.tsx (inline, L3360/    | src/components/           |
|                          |   L3695)                   |   SidebarInspector.tsx    |
| Min/Max Font Sizes       | Template Draft (L5582)     | Global Defaults (L5932)   |
| Alignment / Merge        | CanvasAlignmentToolbar.tsx | CanvasContextMenu.tsx &   |
|                          |                            |   Layer Context Menu      |
| Font Templates Management| Global Settings Modal      | Typesetting Floating      |
|                          |                            |   Inspector               |
+--------------------------+----------------------------+---------------------------+
```

### Key Redundancy Findings:
1. **Orphaned Component Files**: `SettingsModal.tsx`, `SidebarInspector.tsx`, and `PipelineToolbar.tsx` in `src/components/` duplicate significant UI logic and state bindings present in `App.tsx`, but are not active in `App.tsx`.
2. **Min/Max Font Size Confusion**: Min and max font sizes exist both as template-specific constraints (in Font Templates) AND as global project-wide settings (in Font Style Defaults).
3. **Scatter of Action Buttons**: OCR and pipeline controls are split across top sub-toolbar checkboxes, menu bar items, right-panel tabs, and context menus.

---

## 4. State Management & Live Preview to Export Pipeline

### 4.1 State Management Structure
- **Zustand (`src/stores/projectStore.ts`)**:
  - Global project state (`projects`, `activeProject`, `activePage`, `selectedBlock`, `selectedBlocks`).
  - Async API actions (`fetchProjects`, `selectProject`, `uploadPage`, `updateBlock`, `updateBlocksBulk`, `deleteBlock`, `updateProjectSettings`).
  - Optimistic UI updates with mutation tracking (`blockUpdateTracker.ts`).
  - Canvas capture callback registration (`getCanvasRenderCapture`).
- **React Local State (`App.tsx`)**:
  - Menu toggles, modal open flags (`showGlobalSettingsModal`, `showNewProjModal`).
  - Active global settings (`settingsMinFontSize`, `settingsMaxFontSize`, `settingsDefaultTextTemplateId`, `stylePresets`, `selectedTemplateKey`).
  - Workspace modes (`workspaceMode`: `'ocr'` vs `'typeset'`).

### 4.2 Live Preview vs PNG/PSD Export Flow

```
[User UI Edit: Typography/Font/Style]
           │
           ▼
[Zustand Store / React State Update]
           │
           ▼
[Fabric.js Canvas (`Canvas.tsx` / `fabricAdapter.ts`)] ──► Live Screen Preview
           │
           ▼ (When User clicks Export PNG/PSD)
[handleExport() in `App.tsx`]
           │
           ▼
[captureAndUploadExactPage()] ──► [waitForCanvasRenderCapture()]
                                              │
                                              ▼
                             [Fabric Canvas Capture Blob (PNG)]
                                              │
                                              ▼
                             [PUT /api/pages/{id}/rendered-overlay]
                                              │
                                              ▼
[POST /api/export/psd OR /api/projects/{id}/export/images]
           │
           ▼
[Backend Compositor generates canonical PSD / PNG file]
```

- **Styling Parity**: Live canvas preview rendering in `Canvas.tsx` (using `fabricAdapter.ts`) produces the exact high-res overlay blob captured for export. The backend receives this rendered overlay alongside canonical typesetting specifications, ensuring visual parity between canvas preview and exported PNG/PSD outputs.

---

## 5. Baseline Test & Typecheck Status

Baseline commands executed in `e:\houmi\frontend`:

1. **Frontend Test Suite (`npx vitest run`)**:
   - **Result**: PASSED
   - **Files**: 16 passed out of 16
   - **Tests**: 113 passed out of 113
   - **Duration**: ~1.39s

2. **TypeScript Typecheck (`npx tsc --noEmit`)**:
   - **Result**: PASSED
   - **Exit Code**: 0 (zero errors)

---

## Summary Recommendations for Refactoring

1. **Consolidate Sub-toolbar**: Extract inline sub-toolbar logic into a unified, modular `PipelineToolbar` component and remove duplicate orphan code.
2. **Consolidate Settings Modal**: Unify the inline Global Settings modal in `App.tsx` and `src/components/SettingsModal.tsx` into a single, clean Settings component.
3. **Unify Min/Max Font Size Settings**: Clarify scope between template-level min/max size limits and project-wide fallback limits.
4. **Clean Standalone Components**: Either refactor `SidebarInspector.tsx` to be used by `App.tsx` or clean up unused legacy component code.
