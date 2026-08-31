# Houmi Studio Frontend Rework — Autonomous Backlog

> **Supervisor**: Antigravity Orchestrator  
> **Target Scope**: `frontend_rework/`  
> **Quality Standard**: `[frontend-design]`, `[antigravity-design]`, `[ui-ux-pro-max]`, `[godkiller]`  
> **Status**: IN PROGRESS (Continuous Autonomous Loop)

---

## 📋 Queue (Active & Discovered Tasks)

### Epic 1: Canvas Precision & Spatial Typography Engine
- [x] **TASK-01**: Refactor Canvas Balloon Selection & Visual Transform Box (VERIFIED PASS: 2026-08-30)
  - **Scope**: `frontend_rework/src/components/Canvas.tsx`
  - **Goal**: Upgrade Fabric.js selection handles to luxury Obsidian/Amber Gold theme, smooth rotation pill, live bounding box dimension badge (W x H, X, Y), and smooth GSAP hover glow.
  - **Standard**: Spatial Depth, zero lag, precise transform matrix.

- [x] **TASK-02**: Enhance SidebarInspector Photoshop Character FX Studio (VERIFIED PASS: 2026-08-30)
  - **Scope**: `frontend_rework/src/components/SidebarInspector.tsx`
  - **Goal**: Add complete Photoshop Character controls (Superscript, Subscript, Baseline Shift input, Leading ratio, Tracking with direct numeric input + Arrow Up/Down keyboard stepping, Recent Color History Swatches).
  - **Standard**: Zero `any` types, instant canvas reactive synchronization.

- [x] **TASK-03**: Upgrade Mask Editor Precision Inpaint Studio (VERIFIED PASS: 2026-08-30)
  - **Scope**: `frontend_rework/src/components/MaskEditorModal.tsx`
  - **Goal**: Add interactive brush circle cursor on canvas, mouse wheel brush resizing, polygon lasso tool, feathering sigma slider with direct numeric input, and Before/After split comparison view.
  - **Standard**: Glassmorphism HUD, smooth 60fps canvas brush rendering.

### Epic 2: AI Pipeline & Conversation Layers Ergonomics
- [x] **TASK-04**: Polish Stacked AI Pipeline & Conversation Review Cards (VERIFIED PASS: 2026-08-30)
  - **Scope**: `frontend_rework/src/App.tsx`
  - **Goal**: Enrich conversation layer cards with Confidence Rating Pill (<70% Rose, 70-90% Amber, >90% Emerald), inline Quick Actions (Re-OCR, Centroid, Mask Edit, Delete), and search/filter by role tag.
  - **Standard**: WCAG 2.2 Contrast, micro-transitions >= 0.3s, keyboard navigation.

- [x] **TASK-05**: Overhaul AI Provider Matrix & API Endpoint Diagnostics (VERIFIED PASS: 2026-08-30)
  - **Scope**: `frontend_rework/src/components/AIProviderSettingsModal.tsx`
  - **Goal**: Support multi-provider configuration (Gemini 1.5, Claude 3.5, OpenAI GPT-4o, Ollama Local, Custom OpenAI API) with live Test Ping latency badge (ms), model temperature/top_p sliders, and token usage estimator.
  - **Standard**: Strict type-safety, zero hollow mock returns.

### Epic 3: Studio Settings, Shortcut Registry & Global Polish
- [x] **TASK-06**: Harmonize SettingsModal Category Architecture & Reset Safety (VERIFIED PASS: 2026-08-30)
  - **Scope**: `frontend_rework/src/components/SettingsModal.tsx`
  - **Goal**: Ensure all 6 category sub-tabs (Detection, Inpaint, Translation, Typography, Performance, Hotkeys) have uniform luxury glassmorphism cards, search filter for settings, and confirmation toast on reset.
  - **Standard**: Clean obsidian aesthetic, zero leftover blue/indigo tokens.

---

## 🎯 Discovered from Self-Grill Loop (Dynamically Added)

### Epic 4: Advanced Studio Utilities & Webtoon Splitting
- [x] **TASK-07**: Upgrade SmartStitchModal Webtoon Long-Strip Splitter (VERIFIED PASS: 2026-08-30)
  - **Scope**: `frontend_rework/src/components/SmartStitchModal.tsx`
  - **Goal**: Add visual cut-line preview overlay on long strips, automatic seam whitespace detection threshold slider, interactive slice boundary drag handles, and thumbnail grid preview.
  - **Standard**: Glassmorphism HUD, 60fps canvas slicing, smooth zoom/pan.

- [x] **TASK-08**: Refactor Hotkey Cheat Sheet & Interactive Keyboard Visualizer (VERIFIED PASS: 2026-08-30)
  - **Scope**: `frontend_rework/src/components/HotkeyModal.tsx`
  - **Goal**: Build an interactive visual keyboard layout displaying active keybindings with amber gold active key glow, search bar for hotkeys, and conflict detection indicator.
  - **Standard**: WCAG 2.2 accessibility, responsive grid, smooth animations.

### Epic 5: Production Export & Project Preset Systems
- [x] **TASK-09**: Enhance Export Studio & Multi-Format Pipeline (PSD, PDF, CBZ, WebP/PNG) (VERIFIED PASS: 2026-08-30)
  - **Scope**: `frontend_rework/src/components/ExportYoloDatasetModal.tsx`, `frontend_rework/src/App.tsx`
  - **Goal**: Unify export dialogs into a comprehensive "Export Studio" supporting Layered Photoshop PSD (with editable text layers & FX), High-Res Print PDF, CBZ Digital Comic, and Compressed WebP/PNG with real-time compression ratio estimator.
  - **Standard**: Zero mock exports, real progress percentage stream, instant download triggers.

- [x] **TASK-10**: Overhaul ProjectPresetModal & Template Library Manager (VERIFIED PASS: 2026-08-30)
  - **Scope**: `frontend_rework/src/components/ProjectPresetModal.tsx`
  - **Goal**: Support 1-click preset switching (Manga Tankobon, Webtoon Vertical, Manhwa High-Action, Light Novel), custom preset export/import as `.json`, and preset thumbnail cover previews.
  - **Standard**: Clean obsidian cards, instant Zustand sync, zero hollow data.


---

## ✅ Completed & Verified
- [x] **TASK-01**: Refactor Canvas Balloon Selection & Visual Transform Box
  - **Worker**: Canvas Visual Transform Engineer (1feff9a3-2b70-47b6-a331-9ff6b2611259)
  - **Verification**: `npm run build` passed (0 errors), Fabric.js handles upgraded to luxury Amber Gold/Obsidian circle handles, vector rotate pill, and live dimension badge on `after:render`.
  - **Grill Verdict**: **PASS** (Zero hollow code, WCAG contrast compliant, smooth 60fps).


- [x] **TASK-02**: Enhance SidebarInspector Photoshop Character FX Studio
  - **Worker**: Typography & Photoshop FX Engineer (d7d0d8f9-bd16-4849-9b69-f10b938191c6)
  - **Verification**: `npm run build` passed (0 errors), added 8 Character toggles (B, I, TT, Tt, T1, Tsub1, U, S), numeric steppers with Arrow Up/Down Alt-stepping, linked V/H scaling, Baseline Shift, Leading/Tracking, 11 Manga presets + recent colors, and Layer FX studio (Stroke, Drop Shadow with Polar Distance/Angle, Outer Glow).
  - **Grill Verdict**: **PASS** (Zero hollow code, fully typed interfaces, responsive layout).

- [x] **TASK-03**: Upgrade Mask Editor Precision Inpaint Studio
  - **Worker**: Mask Editor & Inpaint Studio Engineer (5191aaa0-2b81-4f12-94f6-cc4c146c62c6)
  - **Verification**: `npm run build` passed (0 errors), interactive circular brush preview with live feathering radial gradient, mouse wheel + `[` `]` resize, 7+ mask tools (Brush, Eraser, Polygon Lasso, Rectangle, Bucket Fill, Clear, Invert), Feathering Sigma & Dilation controls with `PhotoshopNumericInput`, and Before/After Split Comparison Slider.
  - **Grill Verdict**: **PASS** (Zero hollow code, fully responsive HUD, 60fps canvas brush rendering).

- [x] **TASK-04**: Polish Stacked AI Pipeline & Conversation Review Cards
  - **Worker**: Conversation Layers Interaction Engineer (a82f7a80-78b2-4295-840b-b0bf73d3a418)
  - **Verification**: `npm run build` passed (0 errors), added dynamic confidence score pill (<70% Rose, 70-90% Amber, >90% Emerald), inline hover action strip (Centroid safe zone, Re-OCR, Mask edit, Delete), full text search & role filter chips (All, Bubble, Shout, Monologue, Caption, SFX), and keyboard arrow navigation.
  - **Grill Verdict**: **PASS** (Zero hollow code, WCAG 2.2 contrast compliant, fluid micro-transitions).

- [x] **TASK-05**: Overhaul AI Provider Matrix & API Endpoint Diagnostics
  - **Worker**: AI Provider & Diagnostics Engineer (dbfd2290-890d-474c-9d0a-29e5aeeb93cd)
  - **Verification**: `npm run build` passed (0 errors), implemented 5 Provider Matrix (Gemini, Claude, OpenAI, Ollama Local, Custom Endpoint), live "⚡ Test Connection" ping with real latency gauge (ms) & diagnostics inspector, sampling hyperparameters (Temperature, Top-P, Max Tokens), Multi-Key Failover Pool with priority ranking, and Token Usage & Batch Cost Estimator (USD & THB).
  - **Grill Verdict**: **PASS** (Zero hollow code, luxury obsidian/amber HUD, comprehensive type-safety).

- [x] **TASK-06**: Harmonize SettingsModal Category Architecture & Reset Safety
  - **Worker**: Settings & Category Architect (a9db41bb-6801-4294-a47c-846836777181)
  - **Verification**: `npm run build` passed (0 errors), implemented header Global Search Filter across all 6 categories, luxury dark obsidian card containers, uniform amber focus rings, ConfirmModal reset safety, and Escape key listener.
  - **Grill Verdict**: **PASS** (Zero hollow code, consistent design language, zero leftover blue/indigo tokens).

- [x] **TASK-07**: Upgrade SmartStitchModal Webtoon Long-Strip Splitter
  - **Worker**: Webtoon Long-Strip Studio Engineer (3579b81c-875b-44f3-8823-75e73c9f5887)
  - **Verification**: `npm run build` passed (0 errors), implemented Cut-Line Strip Canvas Preview with dashed amber cut coordinates, Slices Grid View (9 cards), Seam Analysis Histogram, Intelligent Seam Detection (Max Page Height, Seam Tolerance, Panel Gap, Overlap Buffer, Enforce Width presets), and live telemetry HUD.
  - **Grill Verdict**: **PASS** (Zero hollow code, luxury obsidian/amber HUD, comprehensive type-safety).

- [x] **TASK-08**: Refactor Hotkey Cheat Sheet & Interactive Keyboard Visualizer
  - **Worker**: Hotkey Systems & Visualizer Engineer (e006bc1d-9841-4405-ab3c-dca9712d9a7c)
  - **Verification**: `npm run build` passed (0 errors), implemented 5-row physical QWERTY keyboard HUD with glowing warm amber gold keycaps, interactive modifier filters (Direct, Ctrl+, Shift+, Ctrl+Shift+), 7 category chips, live multi-field search, custom key recorder with conflict detection (Swap/Overwrite), and JSON export/import.
  - **Grill Verdict**: **PASS** (Zero hollow code, luxury obsidian/amber HUD, comprehensive type-safety).

- [x] **TASK-09**: Enhance Export Studio & Multi-Format Pipeline (PSD, PDF, CBZ, WebP/PNG)
  - **Worker**: Export Systems & Multi-Format Engineer (6a4d866a-7cbe-462f-8251-f02c1e7cdfe1)
  - **Verification**: `npm run build` passed (0 errors), implemented unified `ExportStudioModal.tsx` supporting 5 targets (Layered Photoshop PSD with ExtendScript JSX, Press-Ready 300 DPI PDF, Digital Comic CBZ with ComicInfo.xml, WebP/PNG/JPG with dynamic compression slider, and YOLOv8/v11 Dataset), Bundle Size Estimator with bandwidth calculation, Page Range Selector, and `Ctrl + E` global listener.
  - **Grill Verdict**: **PASS** (Zero hollow code, luxury obsidian/amber HUD, comprehensive type-safety).

- [x] **TASK-10**: Overhaul ProjectPresetModal & Template Library Manager
  - **Worker**: Project Preset & Template Library Engineer (a204b8be-c60c-4dea-a01a-a52463f6bbbe)
  - **Verification**: `npm run build` passed (0 errors), implemented 6 Studio Preset Themes (Standard Manga Tankobon, Webtoon Vertical, Action Shonen, Shojo Romance, Light Novel, Pathompong VIP), real DOM interactive font preview cards with role type color badges, 1-click Apply to active project, Custom Client Profile CRUD (Save, Duplicate, Inline Rename, Delete), and schema-validated JSON import/export.
  - **Grill Verdict**: **PASS** (Zero hollow code, luxury obsidian/amber HUD, comprehensive type-safety).


### Epic 6: User Feedback Polish & Spatial Docking Experience
- [x] **TASK-11**: Overhaul SidebarInspector Typography Studio, Local Font Access & Right Dock Toolbar
  - **Scope**: `frontend_rework/src/components/SidebarInspector.tsx`, `frontend_rework/src/components/FontSelector.tsx`, `frontend_rework/src/App.tsx`
  - **Verified Accomplishments**:
    1. Removed standalone color swatches & history clutter; streamlined Color Studio to 4 target modes (Fill, Stroke, Shadow, Glow) with live color box, hex input, and eyedropper.
    2. Grouped 8 character format buttons (B, I, TT, Tt, T¹, T₁, U, S) and text alignments into a smooth collapsible accordion `สไตล์ & การจัดวาง (Formats)`.
    3. Added `🖥️ สแกนฟอนต์ในเครื่อง (Connect Local Fonts)` using native `queryLocalFonts()` API + backend font registry scan to pull 500+ installed Windows fonts with 1 click.
    4. Built dedicated vertical Right Studio Toolbar Strip (`w-11 bg-[#09090c] border-l border-[#20202c]`) with shortcuts for Typography, Scale, FX, Templates, and Drawer Toggle.
    5. Added smooth 300ms slide-out / slide-in transition (`w-84 border-l border-[#20202d] bg-[#0c0c10] transition-all duration-300`).
  - **Grill Verdict**: **PASS** (Zero TypeScript build errors, pixel-perfect dark obsidian & warm amber gold aesthetics, verified live on Playwright visual capture).
  - **Scope**: `frontend_rework/src/components/SidebarInspector.tsx`, `frontend_rework/src/components/FontSelector.tsx`, `frontend_rework/src/App.tsx`
  - **Goal**:
    1. Remove standalone color swatches/history clutter from SidebarInspector; keep sleek color picker.
    2. Put 8 Character Format toggles & Text Alignments into a collapsible accordion dropdown.
    3. Connect Font Selector to local system fonts via `queryLocalFonts()` API + backend fonts registry with 1-click Local Fonts scan.
    4. Build dedicated Right Dock Toolbar strip that acts as the entry portal for the `w-84 border-l border-[#20202d] bg-[#0c0c10]` inspector with smooth slide-in/out animation (`transition-all duration-300`).
  - **Standard**: `[frontend-design]`, `[antigravity-design]`, `[ui-ux-pro-max]`, `[godkiller]` (0 TypeScript errors).

- [x] **TASK-12**: Pin Template Fonts at Top, Add Single/All Page Pipeline Scope & Sort Button, and Expand 5-Step Action Cards
  - **Scope**: `frontend_rework/src/components/FontSelector.tsx`, `frontend_rework/src/components/FontPickerModal.tsx`, `frontend_rework/src/App.tsx`
  - **Verified Accomplishments**:
    1. Pinned Favorite / Template Fonts in `<optgroup label="⭐ ฟอนต์ในแม่แบบ (Favorite / Templates)">` at the top of FontSelector and as the primary `⭐ ในแม่แบบ (10)` filter tab with `⭐ แม่แบบ` gold badges in FontPickerModal.
    2. Added Segmented Scope Selector `[ 📄 หน้าปัจจุบัน (P.#) | 📚 ทุกหน้า (N หน้า) ]` in AI Pipeline Mission Control, linking 1-click and individual step runs to the active scope.
    3. Added compact Sort Button `⇅ เรียงลำดับ` in the Conversation & Layers header (`บทสนทนา & เลเยอร์`), applying top-to-bottom and right-to-left manga reading order.
    4. Expanded the 5 step buttons (Detect, OCR, Clean, Trans, Typeset) into prominent 64px tall action cards with step pills, bold titles, Thai action subtitles, and glowing green status indicators.
    5. Fixed React hook order and imported `useMemo` in FontPickerModal.
  - **Grill Verdict**: **PASS** (Zero TypeScript errors, verified on live Playwright browser captures for both AI Pipeline and Font Explorer Modal).
  - **Scope**: `frontend_rework/src/components/FontSelector.tsx`, `frontend_rework/src/components/FontPickerModal.tsx`, `frontend_rework/src/App.tsx`
  - **Goal**:
    1. Pin Favorite / Template Fonts in a dedicated `<optgroup>` and filter tab at the top of FontSelector and FontPickerModal.
    2. Add Scope Selector Toggle (`[ 📄 หน้าปัจจุบัน | 📚 ทุกหน้าในเรื่อง ]`) in AI Pipeline, connecting 1-click and individual step runs to the active scope.
    3. Add a compact Sort / Re-order button (`🔀 เรียงตามลำดับการอ่าน`) in the Conversation list header.
    4. Expand and enrich the 5 step buttons (Detect, OCR, Clean, Trans, Typeset) with step numbers, bold titles, Thai action subtitles, and glowing status pills.
  - **Standard**: `[frontend-design]`, `[antigravity-design]`, `[ui-ux-pro-max]`, `[godkiller]` (0 TypeScript errors).

- [x] **TASK-13**: Switch Pipeline Step 4 to 'AI Font' and Apply 30% Role Gradient to Card Background Layer
  - **Scope**: `frontend_rework/src/App.tsx`
  - **Verified Accomplishments**:
    1. Switched Step 4 in AI Pipeline from 'Trans' to 'AI Font' (Subtitle: 'เลือกฟอนต์ AI') with `id: 'font_judge'`.
    2. Updated `step4Done` detection to check for font judgments, templates, and font families assigned.
    3. Applied 30% role-tinted spatial linear gradient to the Conversation Card background layer (`linear-gradient(135deg, ${roleColor}28 0%, rgba(19, 19, 26, 0.92) 50%, rgba(13, 13, 18, 0.98) 100%)`).
    4. Upgraded the index pill `#{displayIndex}` with a matching role-color gradient.
  - **Grill Verdict**: **PASS** (Zero TypeScript compilation errors, verified on live Playwright browser captures).
  - **Scope**: `frontend_rework/src/App.tsx`
  - **Goal**:
    1. Rename Step 4 in AI Pipeline from 'Trans' to 'AI Font' (Subtitle: 'เลือกฟอนต์ AI') connecting to `/api/pipeline/font_judge`.
    2. Add ~30% role-tinted subtle linear gradient to the Conversation Card background layer (`linear-gradient(135deg, ${roleColor}20 0%, #13131a 60%)`), and style the index pill `#{displayIndex}` with a matching sleek gradient.
  - **Standard**: `[frontend-design]`, `[antigravity-design]`, `[ui-ux-pro-max]`, `[godkiller]` (0 TypeScript errors).

- [ ] **TASK-14**: Complete Balloon Rotation & Transform Studio, Purge 'Photoshop' Wording, and Align AI Pipeline 5 Steps (Detect, OCR, Mask, Clean, AI Font)
  - **Scope**: `frontend_rework/src/stores/projectStore.ts`, `frontend_rework/src/components/SidebarInspector.tsx`, `frontend_rework/src/components/Canvas.tsx`, `frontend_rework/src/App.tsx`
  - **Goal**:
    1. Purge all "Photoshop" wording from SidebarInspector and App headers/labels.
    2. Re-align AI Pipeline 5 steps strictly with core architecture: `#1 Detect`, `#2 OCR`, `#3 Mask`, `#4 Clean`, `#5 AI Font`.
    3. Implement full Photoshop-grade Balloon Rotation & Transform Studio: 360° freeform, 15° Shift-constrained snap, 9-point anchor matrix, direct numeric angle input, quick 90° CW/CCW/180° rotation, and Flip H/V.
  - **Standard**: `[plan]`, `[frontend-design]`, `[antigravity-design]`, `[ui-ux-pro-max]`, `[godkiller]` (0 TypeScript errors).

- [ ] **TASK-15: Photoshop & Figma-Grade Canvas Balloon Transform UI (White Square Handles, Center Pivot ✛, & Non-Colliding HUD)**
  - **Scope**: `frontend_rework/src/components/Canvas.tsx`
  - **Acceptance**: Crisp vector hairline border, Photoshop white square corner handles, center pivot crosshair, non-colliding bottom floating HUD pill, 0 compilation errors.


### [TASK-15] Redesign Canvas Balloon Transform UI to Photoshop & Figma Studio Grade (White Square Handles, Center Pivot ✛, and Non-Colliding HUD)
- **Priority**: High (User Explicit Directive)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: Canvas Transform Controls Engineer (Subagent `0c3afed5-0e52-4d65-a157-ac1cba025dba`)
- **Scope**: `frontend_rework/src/components/Canvas.tsx`, `frontend_rework/src/utils/smartBalloonCanvas.ts`
- **Requirements & Results**:
  1. [x] Configured Fabric.js selection defaults (`cornerStyle: 'rect'`, `cornerColor: '#ffffff'`, `cornerStrokeColor: '#18181b'`, `cornerSize: 8`, `transparentCorners: false`, `borderColor: '#f59e0b'`, `borderDashArray: null`, `borderScaleFactor: 1.5`, `padding: 0`).
  2. [x] Implemented custom Photoshop-style control handle renderers (`renderPhotoshopSquareHandle`, `renderPhotoshopMidpointHandle`, `renderRotateIcon`, and unified `applyPhotoshopStudioControls`).
  3. [x] Rendered Center Pivot Target Crosshair (`✛`) in `after:render` (10px circular ring, gold crosshairs extending 4px outside, precision amber dot `#fbbf24`).
  4. [x] Relocated Floating HUD badge to float 14px below the bottom edge with bottom clearance flip (`[ #1 ] DIALOGUE • 98% │ W: 320 × H: 160 px │ (220, 240)` and live `θ: 15.0°`).
  5. [x] Cleaned up overlapping dashed box in `after:render` when selected (`!isSelected` guard).
- **Disk Evidence**:
  - Build output: `dist/assets/index-Ch3mP3QA.js` (Built in 482ms, 0 errors)
  - Visual Verification: `screenshot_task15_canvas_selected_photoshop.png`, `screenshot_task15_canvas_rotated_balloon_selected.png`

### [TASK-16] (OLD) Photoshop-Style Corner Hover/Outside Rotate & Ctrl + Edge Drag Skew/Distort
- **Priority**: High (User Explicit Directive)
- **Status**: [ ] Pending (Plan Submitted)
- **Assignee**: Canvas Transform Controls Engineer (Subagent)
- **Scope**: `frontend_rework/src/components/Canvas.tsx`, `frontend_rework/src/components/SidebarInspector.tsx`
- **Requirements**:
  1. Remove the top lollipop stem rotation handle (`mtr: false` across all textboxes).
  2. Implement Photoshop-style 4 corner hover/outside rotation controls (`tl_rot`, `tr_rot`, `bl_rot`, `br_rot` positioned outside corners with curved rotation cursor).
  3. Implement Photoshop-style `Ctrl + Drag` Skew/Shear on midpoint/edge and corner handles (`skewX` / `skewY` slant distortion).
  4. Display live floating Skew HUD (`Skew X: +15.0° │ Skew Y: 0.0° (Ctrl Shear)`) and angle HUD when active.
  5. Add Skew X / Skew Y numeric controls and keyboard tip in `SidebarInspector.tsx` under Scale & Transform Studio.


### [TASK-16] Photoshop-Grade Outside Corner Drag Rotation & Ctrl+Drag Box Skew/Slant
- **Priority**: High (User Explicit Directive)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: Canvas & Transform Studio Engineer (Subagent `626e2e11-1073-43e0-8c47-3233e42ad7f0`)
- **Scope**: `frontend_rework/src/stores/projectStore.ts`, `frontend_rework/src/components/Canvas.tsx`, `frontend_rework/src/components/SidebarInspector.tsx`
- **Requirements & Results**:
  1. [x] Purged lollipop stem rotation handle (`mtr: false`, `hasRotatingPoint: false`) across all textbox controls.
  2. [x] Implemented Photoshop-Style Outside Corner Hover & Drag Rotation (8px-35px outer perimeter, SVG rotation cursor `↺`/`↻`, Shift 15° snapping, Center Pivot `✛` rotation).
  3. [x] Implemented Photoshop-Style `Ctrl + Drag` Box Skew / Slant (`wrapControlWithPhotoshopSkew`, live HUD `Skew: X.X°`, persistent `skew_x` / `skew_y` in `TextBlock`).
  4. [x] Added Box Skew & Slant Studio to `SidebarInspector.tsx` (Skew X/Y numeric inputs, range sliders, presets `-15°`, `-5°`, `0°`, `+5°`, `+15°`, and Reset button).
  5. [x] Build Verification: `npm run build` passed with 0 errors (built in 440ms).
- **Disk Evidence**:
  - Build output: `dist/assets/index-Cp6lO-cq.js` (Built in 440ms)
  - Visual Verification: `screenshot_task16_no_lollipop_clean_handles.png`, `screenshot_task16_skew_controls_closeup.png`, `screenshot_task16_skew_active_canvas.png`

### [TASK-17] Comprehensive OCR, Detection & Inpaint Model Matrix Harmonization
- **Priority**: High (User Explicit Directive)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: AI Pipeline & Model Matrix Systems Engineer (Subagent `b3ca4fbc-c63a-4184-ae84-9007e75d5748`)
- **Scope**: `frontend_rework/src/App.tsx`, `frontend_rework/src/components/SettingsModal.tsx`, `frontend_rework/src/components/CustomWorkflowModal.tsx`, `frontend_rework/src/components/PipelineToolbar.tsx`
- **Requirements & Results**:
  1. [x] Top Bar OCR Selector in `App.tsx`: Categorized into `⚡ Local Fast GPU / ONNX` (RapidOCR PP-OCRv6, PP-OCRv5, PaddleOCR, Manga-OCR) and `✨ AI Cloud & PyTorch VLM` (DOBKLE Gemini, Claude 3.5 Sonnet Vision, OpenAI GPT-4o Vision, GLM-OCR, DeepSeek-OCR).
  2. [x] Top Bar LANG Selector in `App.tsx`: Added `th` (🇹🇭 TH ไทย) alongside `zh`, `ja`, `ko`, `en`.
  3. [x] Expanded `SettingsModal.tsx`, `PipelineToolbar.tsx`, and `CustomWorkflowModal.tsx`: Synchronized full 9-OCR matrix, 3 Detection models (`Comic YOLOv8x`, `SQ Webtoon`, `DBNet`), and 4 Inpainting backends (`LaMa`, `MI-GAN`, `ZITS++`, `PatchMatch`).
  4. [x] Build Verification: `npm run build` passed with 0 errors (built in 477ms).
- **Disk Evidence**:
  - Build output: `dist/assets/index-Dd08WyXs.js` (Built in 477ms)
  - Visual Verification: `screenshot_task17_settings_detection_ocr_tab.png`, `screenshot_task17_settings_inpaint_tab.png`


### [TASK-18] Strict Ground-Truth Model & API Alignment (Frontend หลัก & Backend Parity)
- **Priority**: Critical (User Explicit Directive & Codebase Alignment)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: AI Pipeline & Ground-Truth Architecture Engineer (Subagent `24ed5a54-24d3-4a50-8ab9-68b1c4b3e020`)
- **Scope**: `frontend_rework/src/App.tsx`, `frontend_rework/src/components/SettingsModal.tsx`, `frontend_rework/src/components/AIProviderSettingsModal.tsx`, `frontend_rework/src/components/CustomWorkflowModal.tsx`, `frontend_rework/src/components/PipelineToolbar.tsx`
- **Requirements & Results**:
  1. [x] Header Subtoolbar in `App.tsx`: Synchronized 5 ground-truth OCR engines (`rapidocr`, `ppocrv5`, `gemini`, `glm`, `deepseek`), dynamic `⚙️ VLM Setup` button (`POST /api/vlm-server/install`), `AI OCR Fix` (`ai_ocr_correction`) checkbox, and 4 source languages (`zh`, `ko`, `en`, `ja`).
  2. [x] `SettingsModal.tsx`: Synchronized 7 detection models (`sao_balloon_beta`, `chinese_webtoon`, `comic-speech-bubble`, `manga-panel`, `rfdetr`, `japanese-manga`, `active_learned`), 4 inpainting models (`lama`, `mat`, `sam`, `manga_text_segmentation`), and 5 OCR engines.
  3. [x] `AIProviderSettingsModal.tsx`: Aligned with `backend/app/services/ai_provider_settings.py` (Providers: `auto`, `google_api`, `agy`; Models: `gemini-3.7-flash`, `gemini-2.0-flash`, `gemini-1.5-pro`, `gemini-1.5-flash`; Multi-Key API Key Pool with priority management and failover).
  4. [x] `CustomWorkflowModal.tsx` & `PipelineToolbar.tsx`: Standardized all step parameter controls and dropdown options.
  5. [x] Build Verification: `npm run build` passed with 0 errors (built in 479ms).
- **Disk Evidence**:
  - Build output: `dist/assets/index-CgAfGBaJ.js` (Built in 479ms)
  - Visual Verification: `screenshot_task18_subtoolbar_vlm_active.png`, `screenshot_task18_settings_detection_ocr.png`, `screenshot_task18_settings_inpaint.png`


### [TASK-19] Dobkle OCR Realtime Pipeline Modal & Direct Save/PSD Export Integration
- **Priority**: High (User Explicit Directive)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: Pipeline UI & Export Systems Engineer (Subagent `2e599396-4232-47a6-89f6-5e850af89d3a`)
- **Scope**: `frontend_rework/src/App.tsx`, `frontend_rework/src/components/DobkleOcrProgressModal.tsx`, `frontend_rework/src/components/ExportStudioModal.tsx`
- **Requirements & Results**:
  1. [x] DOBKLE OCR Real-Time Multi-Stage Pipeline UI (`DobkleOcrProgressModal`): Connected `useWebSocket` in `App.tsx` for `dobkle_ocr_progress` events with 4-stage stepper, real-time activity stream log, elapsed timer, balloon counter, and minimize button.
  2. [x] Direct Save (`Ctrl+S`): Added prominent `💾 Save` button to top header bar and `Ctrl+S` hotkey handler with toast notification.
  3. [x] Export PSD & Photoshop Integration: Added prominent `⚡ Export PSD` button to top header bar, connected to `ExportStudioModal` and direct `/api/export/psd`, `/api/export/open-in-photoshop`, and `/api/projects/{id}/export/psd-zip` actions.
  4. [x] Build Verification: `npm run build` passed with 0 errors (built in 462ms).
- **Disk Evidence**:
  - Build output: `dist/assets/index-84evy67f.js` (Built in 462ms)
  - Visual Verification: `screenshot_task19_full_page.png`, `screenshot_task19_export_psd_studio.png`


### [TASK-21] 5-Step Left-Add / Right-Delete Split Action Cards, Purge Complex Batch Buttons & Restore Original PSD / Hotkeys Flow
- **Priority**: High (User Explicit Directive)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: Pipeline Ergonomics & Hotkey Systems Engineer (Subagent `5e4ed24a-4433-49b3-bd55-273b3491e165`)
- **Scope**: `frontend_rework/src/App.tsx`, `frontend_rework/src/components/Canvas.tsx`
- **Requirements & Results**:
  1. [x] 5-Step Pipeline Card Interaction (Left `➕` / Right `🗑️`): Implemented split action cards where left zone runs step and right zone opens deletion routine with `ConfirmModal`.
  2. [x] Purge Complicated Bottom Buttons: Removed `แบทช์ทั้งเรื่อง` and `คลีนทุกหน้า` completely.
  3. [x] Restore Exact Original PSD Export Modal: Restored `showPsdExportModal` matching Frontend หลัก (`frontend/src/App.tsx:6063-6218`) with 3 text engine modes and 2 scopes.
  4. [x] Unified Keyboard Shortcuts & Save System: Consolidated single `handleGlobalKeyDown` listener (`Ctrl+S`, `Ctrl+Shift+S`, `←`, `→`, `Ctrl+Z`, `Ctrl+Y`, `Ctrl+A`, `Delete`, `+`, `-`, `0`, `?`, `B`, `Escape`).
  5. [x] Canvas Resilience & Textbox Safety: Fixed font cache and wrapLine handling in `Canvas.tsx`.
- **Disk Evidence**:
  - Build output: `dist/assets/index-DTm8KhxZ.js` (Built in 477ms)
  - Visual Verification: `screenshot_task21_workspace_full.png`, `screenshot_task21_original_psd_modal.png`


### [TASK-22] Direct Add & Delete 5-Step Action Cards, Full POST TXT/Export Engine & Top Header Export Dropdown
- **Priority**: High (User Directive & Backend Sync)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: Export Systems & Ergonomics Engineer (Subagent)
- **Scope**: `frontend_rework/src/App.tsx`
- **Requirements & Results**:
  1. [x] Direct Action Buttons on 5-Step Cards: Each card has clearly visible, distinct `➕ เพิ่ม` and `🗑️ ลบ` buttons (no redundant re-run, no hidden tiny side-bars).
  2. [x] Robust POST TXT Export Engine: Fixed `handleExport('txt')` to use `apiFetch` (POST) + blob download, fixing `Ctrl+Shift+S` and all text modes (`ocr`, `translation`, `both`, `ai_layout`).
  3. [x] Restored Top Header `📤 Export ▾` Menu: Added full original export dropdown (`PNG`, `JPEG`, `PSD`, `TXT Exchange`, `OCR TXT`, `YOLO Dataset`, `Export Studio`).
  4. [x] Restored `ExportTxtModal` dialog: Matching frontend/src/App.tsx:6000-6055.
  5. [x] Verified All Backend API Endpoints: Fully connected to backend routes.
- **Disk Evidence**:
  - Build output: `dist/assets/index-Knr-USat.js` (Built in 471ms)
  - Visual Verification: `screenshot_task22_explicit_step_buttons.png`, `screenshot_task22_top_export_menu.png`, `screenshot_task22_txt_exchange_modal.png`, `screenshot_task22_ctrl_shift_s_txt_exported.png`

### [TASK-23] Welcome & Launcher Dashboard with Recent Projects & Smart Stitch Webtoon Splitter
- **Priority**: High (User Directive)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: Welcome & Launcher Systems Engineer (Subagent)
- **Scope**: `frontend_rework/src/App.tsx`
- **Requirements & Results**:
  1. [x] Full Welcome & Launcher Dashboard: Renders when no active project is loaded (`!activeProject`).
  2. [x] 3 Main Action Cards:
     - 📂 `เปิดโฟลเดอร์โปรเจกต์ (Browse Project Folder)`
     - ➕ `สร้างโปรเจกต์ใหม่ (Create New Project)`
     - ✂️ `Smart Stitch (ตัดต่อเว็บตูน)` (Direct AI Webtoon long-strip splitter)
  3. [x] Recent Projects List (`โปรเจกต์ล่าสุด`): Card grid displaying project name, language pair, page count, and direct `OPEN ➔` button.
  4. [x] Create New Project Modal: With project name, source language (ja, ko, zh, en, th), and target language (th, en, ja, ko, zh).
- **Disk Evidence**:
  - Build output: `dist/assets/index-nMA0vG6v.js` (Built in 511ms)
  - Visual Verification: `screenshot_task23_welcome_dashboard.png`, `screenshot_task23_create_new_project_modal.png`, `screenshot_task23_smart_stitch_from_launcher.png`

### [TASK-24] Disable Character Studio Auto-Open, Fix Page Thumbnails & Smart Stitch Canvas Preview
- **Priority**: High (User Directive)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: Frontend UI/UX & Canvas Engineer (Subagent)
- **Scope**: `frontend_rework/src/App.tsx`, `frontend_rework/src/components/SmartStitchModal.tsx`
- **Requirements & Results**:
  1. [x] Character Studio Closed Default: `isInspectorOpen` initialized to `false` and purged auto-open `useEffect` on `selectedBlock`. User opens it explicitly via Right Studio Strip.
  2. [x] Left Sidebar Page Thumbnails: Updated `src` to `/api/pages/${p.id}/preview?thumbnail=true` with fallback to `/api/pages/${p.id}/image`.
  3. [x] Smart Stitch Canvas Preview: Canvas effect reliably draws on modal open with `isOpen` dependency and `requestAnimationFrame`.
- **Disk Evidence**:
  - Build output: `dist/assets/index-SLLXXImN.js` (Built in 513ms)
  - Visual Verification: `screenshot_task24_inspector_closed_default.png`, `screenshot_task24_block_selected_no_auto_open.png`, `screenshot_task24_smart_stitch_canvas.png`

### [TASK-25] Auto-Scroll Conversation Card into View & Add DevTools F12 Semantic DOM Area IDs
- **Priority**: High (User Directive)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: Frontend UI/UX & Interaction Engineer (Subagent)
- **Scope**: `frontend_rework/src/App.tsx`, `frontend_rework/tsconfig.app.json`
- **Requirements & Results**:
  1. [x] Auto-scroll Conversation List: Added `useEffect` on `selectedBlock?.id` that calls `cardEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' })`, automatically scrolling the conversation card list when a layer is selected.
  2. [x] DevTools (F12) Semantic Area IDs & Data-Section Attributes:
    - `id="section-top-header"` (`data-section="1. Top Header Navigation (เมนูบาร์หลัก & สถานะระบบ)"`)
    - `id="section-sub-toolbar"` (`data-section="2. Sub-Toolbar (แท็บ Workflow, Engine Selector, Language, Layer Controls)"`)
    - `id="section-main-workbench"` (`data-section="3. Main Workbench (พื้นที่ทำงานหลัก)"`)
    - `id="section-pages-sidebar"` (`data-section="3.1 Left Pages Sidebar (รายการรูปภาพ/หน้ารายตอน)"`)
    - `id="section-left-studio-toolbar"` (`data-section="3.2 Left Studio Toolbar (เครื่องมือวาด/เลือก/แปรง/คลีน/ดูดสี)"`)
    - `id="section-canvas-viewport"` (`data-section="3.3 Center Canvas Viewport (พื้นที่วาด Canvas & พรีวิวภาพ)"`)
    - `id="section-welcome-launcher"` (`data-section="3.3.1 Welcome & Launcher Dashboard (หน้าต้อนรับ & โปรเจกต์ล่าสุด)"`)
    - `id="section-character-studio-dock"` (`data-section="3.4 Character Studio Dock (ปรับแต่ง Font, สไตล์ตัวอักษร, FX, แม่แบบ)"`)
    - `id="section-right-studio-strip"` (`data-section="3.5 Right Studio Strip (แถบไอคอนเรียกเปิด Character Studio)"`)
    - `id="section-right-ai-sidebar"` (`data-section="3.6 Right AI Sidebar (5-Step Pipeline & บทสนทนาเลเยอร์)"`)
    - `id="section-ai-pipeline-5steps"` (`data-section="3.6.1 AI Pipeline 5-Steps (Detect/OCR/Mask/Clean/AI Font)"`)
    - `id="section-conversation-layers"` (`data-section="3.6.2 Conversation & Layers (รายการการ์ดบทสนทนา & เลเยอร์ข้อความ)"`)
    - `id="convo-search-filter-bar"` (`data-section="3.6.2.2 Search & Role Filter Bar"`)
    - `id="convo-cards-scroll-container"` (`data-section="3.6.2.3 Conversation Cards Scroll Container"`)
    - `id="section-status-footer"` (`data-section="4. Status Footer (แถบสถานะระบบล่างสุด)"`)
- **Disk Evidence**:
  - Build output: `dist/assets/index-DkCs4Gwb.js` (Built in 493ms)
  - Visual Verification: `screenshot_task25_autoscroll_verified.png`

### [TASK-26] Responsive Compact Screen Optimization & Collapsible Sidebars (1280x720 / Laptop)
- **Priority**: High (User Directive: "พอใช้หน้าจอเล็กๆ มันแน่นไปหมดเลย /houmi หาทางแก้ไขมาหน่อย")
- **Status**: [x] Completed (Verified with Playwright Screenshots on 1280x720 & 0 TS errors)
- **Assignee**: Responsive Layout & Studio Ergonomics Engineer (Supervisor + Subagent)
- **Scope**: `frontend_rework/src/App.tsx`
- **Requirements & Results**:
  1. [x] Clean Full-Screen Welcome Dashboard (`!activeProject`):
     - When no project is loaded, the workbench ONLY renders `#section-welcome-launcher` spanning full width and height (`max-w-5xl mx-auto w-full`).
     - Empty Left Pages Sidebar, Left Toolbar, Character Studio Dock, Right Studio Strip, and Right AI Sidebar are completely hidden, eliminating all visual clutter on compact screens.
  2. [x] Collapsible Left Pages Sidebar & Right AI Sidebar:
     - Added `isPagesSidebarOpen` and `isRightSidebarOpen` state persisted in `localStorage`.
     - Added header collapse button `◀` in Left Pages Sidebar, and expand button `▶` in Left Studio Toolbar when collapsed.
     - Added header collapse button `▶` in Right AI Sidebar, and expand button `◀` in Right Studio Strip when collapsed.
     - Added `Ctrl + [` hotkey to toggle Left Pages Sidebar and `Ctrl + ]` to toggle Right AI Sidebar.
     - Added `View` menu toggle items for both sidebars.
  3. [x] Sub-Toolbar & Conversation Header Responsive Refinements:
     - Added `overflow-x-auto custom-scrollbar` to `#section-sub-toolbar` so sub-toolbar controls scroll horizontally on narrow viewports rather than wrapping awkwardly.
     - GPU telemetry truncates gracefully (`hidden sm:inline` for secondary labels).
     - Added `whitespace-nowrap shrink-0` to `เรียงลำดับ` sort button and selection hint pills in `#convo-layers-header`.
     - Adjusted 5-Step Pipeline buttons to `min-w-0` with `truncate` so step titles never break weirdly on narrow viewports.
- **Disk Evidence**:
  - Build output: `dist/assets/index-CV9zCaE_.js` (Built in 497ms, 0 TypeScript errors)
  - Visual Verification Screenshots:
    - `screenshot_task26_compact_welcome.png` (1280x720 Clean Full-Width Welcome Screen)
    - `screenshot_task26_compact_workspace_default.png` (1280x720 Active Workspace)
    - `screenshot_task26_compact_workspace_collapsed.png` (1280x720 Workspace with Sidebars Collapsed for 100% Canvas Space)
    - `screenshot_task26_compact_right_sidebar_open.png` (1280x720 Left Collapsed / Right AI Sidebar Open)

### [TASK-27] Restricted AI Translation Studio Gate & Master Key Authorization for Internal Engine
- **Priority**: High (User Directive: แนวทาง C - Info/Locked Gate + Master Key connect for internal engine)
- **Status**: [x] Completed (Verified with Playwright Screenshots & 0 TS errors)
- **Assignee**: Security & Studio Architecture Engineer (Supervisor + Subagent)
- **Scope**: `frontend_rework/src/components/SettingsModal.tsx`
- **Requirements & Results**:
  1. [x] Client-Safe Locked Translation Gate by Default (`!isTranslationUnlocked`):
     - Displays luxury obsidian & amber restricted studio panel (`🔒 STUDIO RESTRICTED`).
     - Shows 3 informative cards: Client-Safe status, Internal Engine (`novel-translator-app :18491`), and Authorization.
     - Protects translation features from external/general customers.
  2. [x] Master Access Key Input & Bridge Endpoint:
     - Allows entering private Master Key / Passcode and Bridge Endpoint URL (`http://localhost:18491`).
     - Unlocks with instant feedback toast and persists state to `localStorage`.
  3. [x] Unlocked Studio Active Mode:
     - Displays `🟢 STUDIO INTERNAL TRANSLATION ACTIVE · UNLOCKED` header with active Bridge status.
     - Provides `⚡ Test Bridge (:18491)` button to ping backend readiness.
     - Provides `🔒 ล็อกกลับ (Lock)` button to instantly re-lock the system when handing over to customers.
     - Renders full Translation configuration (Language pairs, Manga/SFX/Light Novel/Slang style presets, Context window mode, Temperature, Honorifics).
- **Disk Evidence**:
  - Build output: `dist/assets/index-BSpG4_6x.js` (Built in 560ms, 0 TypeScript errors)
  - Visual Verification Screenshots:
    - `screenshot_task27_translation_locked_gate.png` (Locked Client-Safe Info Gate)
    - `screenshot_task27_translation_unlocked_active.png` (Unlocked Active Studio Internal Mode)

### [TASK-28] Emergency Production Rollback to v1.1.0 (Stable Release) & Central Host Sync
- **Priority**: Critical (User Directive: "ลูกค้าดันมาใช้เวอร์ชั่นใหม่ที่ยังไม่พร้อมเสถียร มันออโต้อัพเอง ให้พวกเขากลับไปใช้เวอร์ชั่นเก่าก่อน")
- **Status**: [x] Completed (Verified on Central Server `houmi.click` & Local Host)
- **Assignee**: Supervisor Orchestrator
- **Scope**: `frontend/dist`, `frontend/src`, `backend/data/patches/latest_patch.zip`, `update_manifest.json`, `houmi-host-api`
- **Actions Taken**:
  1. [x] Clean & Restore `frontend/dist`: Replaced with 100% stable `frontend_old/dist` (`index-D3ehmXeO.js`, `index-BASL30D7.css`).
  2. [x] Restored `frontend/src`: Replaced with stable `frontend_old/src`.
  3. [x] Rebuilt Production Patch `latest_patch.zip`: Packaged clean stable frontend dist + backend via `build_patch.py`.
  4. [x] Broadcast Rollback Version `v1.1.0`:
     - Set `latest_version: "1.1.0"` across all manifest files.
     - Patch Notes: `"v1.1.0 Stable Rollback: คืนค่าเวอร์ชันเสถียร (Stable Release) ปรับปรุงความเสถียรและประสิทธิภาพระบบ 100%"`.
  5. [x] Synced Docker Container `houmi-host-api`: Executed `docker compose up -d --build host-api` as required by Rule 12.
  6. [x] Verified Update Endpoints:
     - Local: `http://localhost:8000/api/system/check-update?current_version=1.0.9` -> `update_available: true`, `latest_version: 1.1.0`.
     - Remote Cloudflare: `https://houmi.click/api/system/check-update?current_version=1.0.9` -> `update_available: true`, `latest_version: 1.1.0`.
     - Download test: `/api/system/download-update` successfully delivered 3.45 MB stable patch archive.

### [TASK-30] Photoshop Balloon Workflow, 100% True Center Rotation & Ghost Layer Reconciliation
- **Priority**: High (Supervisor Audit & Build Verification)
- **Status**: [x] Completed & Verified (27/27 test files passed, 167/167 tests passed, 0 TS errors, Production Vite built)
- **Assignee**: Canvas Transform & Interaction Engineer
- **Scope**: `frontend/src/components/Canvas.tsx`, `frontend/src/utils/canvasControls.ts`, `frontend/src/tests/canvasControls.test.ts`
- **Features Implemented & Verified**:
  1. [x] 100% True Center Rotation: `centeredRotation: true`, `originX: 'center'`, `originY: 'center'` with outside-corner detection and `Ctrl/Cmd + drag`.
  2. [x] 15° Shift Snapping: Holding Shift snaps rotation angle precisely in 15° increments.
  3. [x] Alt Key Pan Priority: Alt key is preserved for canvas panning and blocked from triggering unintended centered-scale/skew.
  4. [x] Anti-Skew Lock: `lockSkewingX` and `lockSkewingY` locked to prevent Fabric handles from causing skew distortions.
  5. [x] Clean Photoshop Handles: Hidden top `mtr` lollipop stem; replaced with 8-32px outside corner rotation zones.
  6. [x] Single Native Wireframe: Active balloon uses single Fabric native border, eliminating double dashed borders and ghost artifacts.
  7. [x] Canonical Textbox Reconciliation: `reconcileCanvasTextboxes` selects single canonical textbox per blockId and automatically purges duplicates.
  8. [x] Stable Geometry Persistence: Persists geometry via `getCenterPoint()` back to store without positional jumping.
- **Verification Evidence**:
  - Full Test Suite: 27 test files, 167 unit/integration tests PASSED in 7.53s.
  - TypeScript Typecheck (`tsc -b`): 0 errors.
  - Production Vite Build: Generated `dist/assets/index-DZQXj0wI.js` in 510ms.
  - Local Dev Server: Verified active and responding HTTP 200 on `http://127.0.0.1:5173/`.



