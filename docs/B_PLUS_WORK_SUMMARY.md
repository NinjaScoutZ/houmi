# Houmi B+ Typesetting — Definitive Work Summary

**Audience:** Product / engineering / expert reviewers (no chat history required)  
**Date:** 2026-07-19  
**Status:** Phase 0–2 engineering close-out **complete**  
**Live versions:** `schema_version = 2.0.0` · `layout_engine_version = 2.0.1`  
**Production merge:** **NOT APPROVED** until Gate 0 corpus + Gate 1–3 evidence (see §4)

| Related docs | Path |
|---|---|
| Technical RFC (implementation contract) | [`docs/TYPESETTING_RFC_B_PLUS.md`](./TYPESETTING_RFC_B_PLUS.md) |
| Expert review pack | [`docs/EXPERT_REVIEW_B_PLUS_TYPESETTING.md`](./EXPERT_REVIEW_B_PLUS_TYPESETTING.md) |
| Direction deck (Marp) | `Houmi_Auto_Font_LineBreak_Judge_Proposal.md` |

---

## 1. Decision locked

| Item | Value |
|---|---|
| Path | **Option B+ — Deterministic-first Hybrid** (not A / B / C as first proposed) |
| Product goal | Maximize ready-to-ship lettering; Preview / PNG / PSD **semantic** parity; users only fix low-confidence / risk cases |
| Architecture | **Engine owns rules · Decision Ranker ranks feasible candidates · Template owns brand · TypesettingSpec is the export contract** |
| Approved build | Phase **0–2** + minimum feedback event logging |
| **Not approved** | Phase **4 Tiny ML** · Phase **5 Local LLM** until a Gate fails and rules cannot fix it with event evidence |

---

## 2. What shipped (code)

### 2.1 Line engine
- Beam + greedy line candidates + rules **Decision Ranker** — `backend/app/services/typesetting/fitting.py`
- Exact font metrics (Pillow) + ellipse/rect safe width hard constraints
- Thai segmentation + **project dictionary** (`settings.project_dictionary` / `thai_dictionary`) — `segmentation.py`
- Entry: `compute_block_typesetting` — `service.py`

### 2.2 TypesettingSpec v2
- `TYPESETTING_SCHEMA_VERSION = "2.0.0"` — `schemas.py`
- `LAYOUT_ENGINE_VERSION = "2.0.0"` — `service.py`
- Fields include: `spec_id`, `revision`, `render_fingerprint`, bold/italic, color/stroke, align, `decision_status`, confidences, `reason_codes`, `template_id`
- Frontend mirrors: `CURRENT_SCHEMA_VERSION` / `CURRENT_LAYOUT_ENGINE_VERSION` = `'2.0.0'` — `frontend/src/utils/typesetting.ts`

### 2.3 Decision status (product lock)
| Status | Meaning |
|---|---|
| `AUTO_APPLIED` | Hard constraints OK; layout confidence high enough to apply |
| `DEFAULTED` | Safe default path (reserved) |
| `NEEDS_REVIEW` | Overflow / font fallback / hard gates / low layout confidence — must surface |

Low **style** confidence defers template auto-apply; it does **not** silently hide layout risk.

### 2.4 Style Judge v1 (rules only)
- Multi-signal Style Descriptor — `style_judge.py`
- Auto-apply template only if **confidence ≥ 0.90**
- API: `POST /api/typesetting/style-judge`

### 2.5 Feedback instrumentation
- JSONL: `data/feedback/typesetting_events.jsonl` (override `HOUMI_TYPESETTING_FEEDBACK_PATH`)
- Auto-log on compute; user API `POST /api/typesetting/feedback`
- UI: ACCEPT / SYSTEM WRONG / PREFERENCE
- Manual template change → `user_preference` event

### 2.6 Parity & export
- Helpers: `parity.py` (semantic / geometry)
- PNG: Spec lines + color + **stroke** — `renderer.py` + `stroke.py`
- PSD: Spec-driven manifest; missing font **blocks** export (no silent fallback) — `psd_export.py`
- Fabric: stroke from Spec + **dirty-check** via `fabricStrokeNeedsUpdate` in Canvas `hasChanged`

### 2.7 UI (Typesetting workspace)
| Control | Behavior |
|---|---|
| **AUTO STYLE PAGE** | Style Judge whole page; snapshot for undo |
| **UNDO AUTO STYLE** | Restore pre-run block snapshot |
| **SUGGEST ONLY** | Judge without template swap |
| **RECOMPUTE LAYOUT** | Page beam recompute |
| **REVIEW QUEUE** | Filter layers to `NEEDS_REVIEW` |
| Layer badges | OK / DEF / REV / ST |
| Canvas outline | Color by decision when Spec-backed |
| Inspector | confidences, reason codes, feedback buttons |

### 2.8 Harness & contracts
- Benchmark: `backend/scripts/benchmark_typesetting.py` → `data/benchmarks/*.json`
- RFC + expert review + **this summary** under `docs/`

---

## 3. How to verify

### 3.1 Backend
```bat
cd E:\houmi\backend
.venv\Scripts\python.exe -m pytest tests/test_typesetting.py tests/test_style_judge.py tests/test_stroke_and_dictionary.py tests/test_layout_region.py tests/test_psd_roundtrip.py tests/test_autofit_constraints.py -q
```
**Last gate run:** 78 passed · exit 0  
**Full backend application suite:** `pytest tests -q` → 125 passed  

### 3.2 Frontend (vitest via npm)
```bat
cd E:\houmi\frontend
npm test -- --run src/tests/decisionStatus.test.ts src/tests/typesetting.test.ts src/tests/autoStyleAndStroke.test.ts
```
**Last gate run:** 20 passed · exit 0 (vitest)  
**Full frontend suite:** 53 passed · production build exit 0  

### 3.2.1 PSD CLI
```bat
cd E:\houmi\manga-psd-cli
cargo test
```
**Last gate run:** 18 passed · exit 0 (includes stroke/leading/tracking Engine Data assertions)  

### 3.3 Benchmark
```bat
cd E:\houmi\backend
.venv\Scripts\python.exe scripts\benchmark_typesetting.py --synthetic 20 --repeats 3
```
**Last gate run (example file):** `data/benchmarks/typeset_20260719_041805.json`  
- live `engine_version`: **2.0.1** · `schema_version`: **2.0.0** (historical benchmark filenames may contain 2.0.0)  
- page **p95** reported; `gate_hints.p95_page_le_2000ms`: **true**  
- Note: synthetic pages lack real balloon images → many `NEEDS_REVIEW` is **expected**; not Gate 2 certification  

### 3.4 HTTP APIs
| Method | Path |
|---|---|
| POST | `/api/typesetting/recompute/page/{page_id}` |
| POST | `/api/typesetting/style-judge` |
| POST | `/api/typesetting/feedback` |
| POST | `/api/typesetting/preflight` (no DB/feedback side effects) |

### 3.5 Optional project dictionary
```json
{ "project_dictionary": ["เทพแห่งสุริยา", "ชื่อเฉพาะ"] }
```

---

## 4. Decision Gates & KPI posture

| Gate | Intent | Status |
|---|---|---|
| **0 Baseline** | Dataset 300–500 + GT + splits + baseline + Spec/parity/RFC/feedback | **NOT PASSED / evidence incomplete** — engineering artifacts exist; **corpus + held-out GT still missing** (blocking Production merge) |
| **1 Line Engine** | overflow 0%, Thai boundary rules, line accept ≥85% held-out | **Code path ready**; accept-rate needs human GT |
| **2 Style Judge** | high-conf (≥0.90) precision ≥90% held-out | **Rules v1 suggest-only** (auto-apply disabled until calibrated); not certified |
| **3 Export** | PNG/JPEG/PSD same Spec; no silent font fallback | **Improved** (stroke/line_height/tracking wired into PSD CLI engine data); full manga QA still required — do **not** treat as Production-certified |

**Honest KPI notes**
- Engine guarantees no mid-grapheme / mid-token split for emitted tokens; dictionary covers proper names; does **not** claim 100% linguistic word sense of PyThaiNLP alone.
- Performance target: ≤20 blocks/page, p95 ≤2s — synthetic harness on dev CPU meets this.
- Parity: semantic 100% required; geometry center ≤ max(2px, 1% box); **not** pixel-perfect PSD vs browser.

---

## 5. Explicit deferrals (not silent half-done)

| Item | Why deferred |
|---|---|
| Quality Contract 300–500 real boxes + held-out labels | Needs human labeling (non-goal of this close-out) |
| Tiny ML / Local LLM | Not approved until Gate fail + rules cannot fix + event evidence |
| Full Feedback Platform (dashboard, dataset export product UI) | Phase 3 — JSONL + APIs exist |
| Deep multi-page Review Queue (assign/SLA) | Minimal page filter shipped |
| PSD Photoshop-native stroke fidelity | Spec/manifest carry stroke; CLI/PS engine QA separate |
| Calibrated probability model for confidence | Rule scores only |
| PPTX deck sync to B+ | Marp MD is direction source |

### Closed in Phase 0–2 (were open handoff items)
- Auto Style undo · Review filter · Pillow+Fabric stroke · stroke dirty-check · auto-feedback on template change · project dictionary · Spec v2 · Style Judge v1 · feedback JSONL · parity helpers · RFC · expert doc · this summary  

---

## 6. Code map

```
backend/app/services/typesetting/
  schemas.py service.py fitting.py scoring.py
  style_judge.py feedback.py parity.py stroke.py segmentation.py
backend/app/routes/typesetting.py
backend/app/services/renderer.py
backend/app/services/psd_export.py
backend/app/services/text_templates.py
backend/scripts/benchmark_typesetting.py
frontend/src/utils/{typesetting,decisionStatus,fabricStroke,autoStyleSnapshot}.ts
frontend/src/App.tsx
frontend/src/components/Canvas.tsx
docs/TYPESETTING_RFC_B_PLUS.md
docs/EXPERT_REVIEW_B_PLUS_TYPESETTING.md
docs/B_PLUS_WORK_SUMMARY.md          ← this file
```

---

## 7. Bottom line

| Question | Answer |
|---|---|
| Is B+ Phase 0–2 engineering spine in-repo? | **Yes** — with Production Gate Repair (build, suggest-only style, signature, PSD fields) |
| Ready for expert review of architecture & code? | **Yes** — use this file + RFC |
| **Approve Production merge?** | **No** — Gate 0 corpus incomplete; Gate 1–3 not certified on held-out real work |
| Start Tiny ML / LLM? | **No** — not approved |

**One sentence:** Engine is the authority, Spec is the contract, AI/ranker only choose among legal candidates, and ML stays off until gates and feedback prove rules are insufficient.
