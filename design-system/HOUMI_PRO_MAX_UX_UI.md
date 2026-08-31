# 🎨 HOUMI STUDIO PRO — UX/UI PRO MAX DESIGN SYSTEM SPECIFICATION
*Generated with NextLevelBuilder UI/UX Pro Max Design Intelligence (Zero Core Code Modifications)*

---

## 1. Overview & Vision

HOUMI Studio is an AI-powered manga and webtoon translation & lettering workspace. This specification integrates design principles from `ui-ux-pro-max-skill` to achieve a **Pro Studio Workbench** standard (analogous to Adobe Spectrum, Figma, and DaVinci Resolve) while preserving 100% of Houmi's existing layout, muscle memory, and fast translation workflow.

---

## 2. Design Dials & Parameters

| Parameter | Value | Rationale |
|---|---|---|
| **Variance** | `4/10` | Balanced, modern, high-precision layout |
| **Motion Intensity** | `3/10` | Subtle, professional, GPU-accelerated micro-interactions |
| **Visual Density** | `8/10` | Information-dense workbench suitable for multi-page manga editing |
| **Color Scheme** | `OLED Dark` | Deep blacks (`#09090B`) + Studio Amber (`#F59E0B`) + Precision Cyan (`#06B6D4`) |

---

## 3. Design Tokens & Color Palette

```css
:root {
  /* Surfaces & Backgrounds */
  --color-bg-base: #09090b;       /* Deep OLED Black */
  --color-bg-surface: #121215;    /* Workbench Panels */
  --color-bg-card: #18181b;       /* Cards & Floating Toolbars */
  --color-bg-glass: rgba(18, 18, 21, 0.85);

  /* Borders & Dividers */
  --color-border-subtle: rgba(255, 255, 255, 0.08);
  --color-border-active: rgba(245, 158, 11, 0.40);
  --color-border-cyan: rgba(6, 182, 212, 0.40);

  /* Primary Brand & Accents */
  --color-accent-amber: #f59e0b;  /* Studio Gold/Amber (Primary Brand) */
  --color-accent-amber-glow: rgba(245, 158, 11, 0.15);
  --color-accent-cyan: #06b6d4;   /* Precision / Inscribed Fit */
  --color-status-success: #10b981;/* Auto-Applied / Clean Ready */
  --color-status-review: #f59e0b; /* Needs Review */
  --color-status-error: #ef4444;  /* Failed / Attention */

  /* Elevation Shadows */
  --shadow-level-1: 0 1px 3px rgba(0, 0, 0, 0.4);
  --shadow-level-2: 0 4px 6px rgba(0, 0, 0, 0.5);
  --shadow-level-3: 0 10px 20px rgba(0, 0, 0, 0.6);
  --shadow-level-4: 0 20px 40px rgba(0, 0, 0, 0.75);

  /* Typography */
  --font-sans: 'Inter', -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  --font-pixel: 'Space Grotesk', sans-serif;
}
```

---

## 4. Key Component Ergonomics

### A. Floating Lettering Bar
- **Anatomy**: Font stepper (`- 22 +`), color swatches, stroke stepper, text alignment (`Left / Center / Right`), direction toggle (`LTR / CJK`), AI tools (`✨ Extract`, `🎯 Center in Balloon`, `🪄 Auto-fit`), duplication/deletion, and close button (`✕`).
- **Safe Distance**: Fixed minimum offset of `24px - 28px` above the top handle of the active text block.
- **Boundary Clamping**:
  - If `blockY * canvasScale < 75px` (near canvas top), the toolbar automatically flips to the bottom (`(blockY + blockHeight) * canvasScale + 24px`).
  - Left position clamped to `max(195px, centerPos)` to avoid left-screen clipping.
- **Persistence**: Remembers hide state in `localStorage` (`houmi_show_floating_lettering_bar`) with 1-click restore via top `View` menu or sub-toolbar pill button.

### B. Free-Floating & Foldable Text & Formatting Panel
- **Draggable Header**: Pointer capture dragging with smooth coordinates and viewport bound clamping.
- **Quick Dock Buttons**: `⇱ Dock Left` (left: 20px), `⇲ Dock Right` (right: 340px).
- **Independent Accordions**: Separate fold/expand toggles for Style Presets and Custom Typography.

### C. 1-Click Pipeline Matrix & Review Queue
- **Status Matrix**: Detect -> OCR -> Translate -> Inpaint -> Typeset with live timer badges and cancel buttons.
- **Review Queue Filter**: 1-click filter toggle (`All` vs `NEEDS_REVIEW`) to streamline quality assurance before export.

---

## 5. WCAG 2.2 AAA Accessibility Compliance

1. **Contrast Ratios**:
   - Primary Text (`#FAFAFA`) on Base (`#09090B`): **18.2:1** (Exceeds AAA 7.0:1 threshold).
   - Amber Accent (`#F59E0B`) on Dark (`#121215`): **8.5:1** (Exceeds AAA threshold).
2. **Keyboard Accessibility**:
   - `focus-visible:ring-2 focus-visible:ring-amber-500/50` on all operable inputs.
   - Complete single-key and modifier shortcuts for all frequent actions.

---

## 6. How to Open the Interactive Preview

To review the interactive prototype in your browser:
Open `file:///e:/houmi/ux-ui-pro-max-preview.html` in Chrome or Edge.
