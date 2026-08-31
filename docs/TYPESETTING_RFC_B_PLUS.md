# Technical RFC — Deterministic-first Hybrid Typesetting (Option B+)

**Status:** Implementation Contract (Gate 0 deliverable)  
**Engine:** `layout_engine_version = 2.0.1`  
**Schema:** `TypesettingSpec.schema_version = 2.0.0`  
**Production merge:** blocked until Gate 0 corpus + held-out baseline exist (see Decision Gates).
**Date:** 2026-07-19

This document is the **implementation contract**. The Marp proposal locks product direction; this RFC locks engineering behavior.

---

## 1. Goals

1. Maximize ready-to-ship typesetting with minimal silent errors.
2. Preview, PNG/JPEG, and PSD consume the **same** immutable `TypesettingSpec`.
3. Engine owns hard constraints; Decision Ranker ranks feasible candidates only.
4. Style Judge is multi-signal and rule-based in Phase 2; ML/LLM require failed gates + evidence.
5. Feedback events are logged from the first suggestion (not deferred to a later “ML phase”).

## 2. Non-goals (current phases)

- Tiny CNN / LightGBM / Local LLM as default path.
- Pixel-perfect Preview ↔ PSD (different text engines).
- AI choosing raw font filenames outside project templates.

## 3. Pipeline

```
Image + Balloon + Translation
  → Style Evidence (style_judge.py)
  → Template Resolver (text_templates.py) [optional auto-apply if conf ≥ 0.90]
  → Line Candidate Generator (beam + greedy baseline)
  → Exact Font Metrics (Pillow / font_registry)
  → Hard Constraints filter
  → Decision Ranker (rules scoring)
  → decision_status ∈ {AUTO_APPLIED, DEFAULTED, NEEDS_REVIEW}
  → Canonical TypesettingSpec v2 (immutable artifact)
  → Canvas / PNG / PSD readers
  → Feedback event JSONL
```

## 4. TypesettingSpec v2 (required fields)

| Field | Notes |
|---|---|
| `schema_version` | `"2.0.0"` |
| `layout_engine_version` | `"2.0.0"` (mirrored as `layout_version`) |
| `spec_id`, `revision` | New revision on any input change — never mutate in-place during render |
| `source_signature` | Hash of layout-affecting inputs |
| `render_fingerprint` | Hash of pixel/export-affecting fields |
| `font_postscript_name`, `font_fingerprint` | Export identity |
| `bold`, `italic`, `color_hex`, `stroke_width`, `stroke_color` | Semantic parity |
| `explicit_lines`, `line_height`, `tracking` | Line truth |
| `text_align` / `horizontal_align`, `vertical_align` | Alignment |
| `writing_direction`, `rotation_deg`, `padding`, `layout_region` | Geometry |
| `decision_status`, `style_confidence`, `layout_confidence`, `reason_codes` | Product states |
| `template_id` | Brand control via project templates |

**Renderer rule:** read Spec only. No second autofit. No silent font fallback on PSD export.

## 5. Decision status

| Status | When | UX |
|---|---|---|
| `AUTO_APPLIED` | Hard constraints OK; layout confidence ≥ 0.90 | Green badge |
| `DEFAULTED` | Layout is safe but style confidence is below the calibrated threshold; keep the actually applied safe/default style and expose the suggestion separately | Blue badge |
| `NEEDS_REVIEW` | Overflow, font fallback, hard gate issues, low layout confidence | Amber badge + Review |

Low **style** confidence defers template auto-apply; it does not hide layout problems.

## 6. Parity definition

### Semantic (must be 100%)

Text, line count, break points, PostScript name, size, bold/italic, color, stroke width.

### Geometry

Layout region center delta ≤ max(2px, 1% of box). BBox tolerances live in tests/`parity.py`.

### Visual

Optional image-diff within tolerance (not Gate 1 blocker).

### Font availability

Missing font → preflight error before Export. **No silent fallback** into PSD.

## 7. Feedback events

Path: `data/feedback/typesetting_events.jsonl`  
Override: `HOUMI_TYPESETTING_FEEDBACK_PATH`

```json
{
  "event": "typesetting_decision",
  "block_id": "...",
  "suggested_template": "emphasis",
  "selected_template": "bubble",
  "suggested_lines": ["..."],
  "final_lines": ["..."],
  "change_reason": "system_wrong",
  "decision_status": "NEEDS_REVIEW",
  "engine_version": "2.0.0",
  "font_fingerprint": "...",
  "spec_revision": 1,
  "timestamp": "..."
}
```

`change_reason`: `accepted` | `system_wrong` | `user_preference` | `suggested` | `auto_applied` | `defaulted` | `needs_review`

## 8. APIs

| Method | Path | Purpose |
|---|---|---|
| POST | `/typesetting/recompute/page/{id}` | Beam layout all blocks |
| POST | `/typesetting/style-judge` | Style Judge + optional template apply |
| POST | `/typesetting/feedback` | User accept/reject instrumentation |
| POST | `/typesetting/preflight` | Spec without DB/feedback side effects |

## 9. Decision Gates

| Gate | Exit criteria |
|---|---|
| **0 Baseline** | Dataset plan, Spec v2, parity defs, this RFC, feedback sink |
| **1 Line Engine** | overflow 0%, grapheme split 0%, token boundary 100%, line accept ≥85%, Preview/PNG semantic parity |
| **2 Style Judge** | high-conf (calibrated ≥0.90) precision ≥90% on held-out; coverage reported; low-conf → review; events logged |
| **3 Export** | PNG/JPEG/PSD same Spec; no renderer autofit; no silent font fallback; editable PSD |

Tiny ML may be proposed only with: failed gate id + why rules cannot fix + event log evidence.

## 10. Performance contract

- Standard page ≤ 20 blocks
- Report p50 and p95
- Deterministic typesetting p95 ≤ 2s on reference hardware (document CPU in benchmark report)
- UI main-thread block ≤ 100ms; heavy work on workers/background
- Webtoon: also report time per 20 blocks

## 11. Benchmark harness

```bash
cd backend
.venv\Scripts\python.exe scripts/benchmark_typesetting.py --synthetic 20
.venv\Scripts\python.exe scripts/benchmark_typesetting.py --page-id <uuid>
```

Outputs JSON under `data/benchmarks/`.

## 12. Code map

| Area | Path |
|---|---|
| Spec schema | `app/services/typesetting/schemas.py` |
| Engine service | `app/services/typesetting/service.py` |
| Beam + ranker | `app/services/typesetting/fitting.py` |
| Style Judge | `app/services/typesetting/style_judge.py` |
| Feedback | `app/services/typesetting/feedback.py` |
| Parity | `app/services/typesetting/parity.py` |
| Routes | `app/routes/typesetting.py` |
| PNG render | `app/services/renderer.py` |
| PSD export | `app/services/psd_export.py` |
| UI badges / Auto Style | `frontend/src/App.tsx`, `decisionStatus.ts`, `Canvas.tsx` |

## 13. Change control

- Bump `LAYOUT_ENGINE_VERSION` when ranking/constraints change.
- Bump `TYPESETTING_SCHEMA_VERSION` when Spec fields break readers.
- Frontend `CURRENT_LAYOUT_ENGINE_VERSION` / `CURRENT_SCHEMA_VERSION` must match.
