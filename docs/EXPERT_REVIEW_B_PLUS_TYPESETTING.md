# Houmi B+ Typesetting — Expert Review Summary

**Document type:** Engineering / product expert review pack  
**Date:** 2026-07-19  
**Decision:** Deterministic-first Hybrid (**Option B+**), conditional approval of Phase 0–2  
**Live contract versions:** `TypesettingSpec.schema_version = 2.0.0` · `layout_engine_version = 2.0.1`  
**Production merge:** **NOT APPROVED** until Gate 0 corpus + held-out baseline exist  
**Companion RFC:** [`docs/TYPESETTING_RFC_B_PLUS.md`](./TYPESETTING_RFC_B_PLUS.md)  
**Product deck (direction lock):** `Houmi_Auto_Font_LineBreak_Judge_Proposal.md`

---

## 1. Executive decision (what leadership locked)

| Item | Value |
|---|---|
| Path | **Option B+** — not A / B / C as originally proposed |
| Product goal | Maximize ready-to-ship lettering; Preview / PNG / PSD semantic parity; user edits only low-confidence / risk cases |
| Architecture one-liner | **Engine owns rules · Decision Ranker ranks feasible candidates · Template owns brand · Spec is the export contract** |
| Approved build scope | Phase 0–2 + minimum feedback instrumentation |
| **Not approved** | Phase 4 Tiny ML · Phase 5 Local LLM (until a Gate fails and rules cannot fix it) |
| Pre-merge code gate (historical) | Gate 0 deliverables (Spec v2, parity defs, RFC, feedback sink, baseline harness) |

---

## 2. What shipped (code, not slides)

### 2.1 Production line engine
| Capability | Location |
|---|---|
| Beam + greedy line candidates + rules ranker | `backend/app/services/typesetting/fitting.py` |
| Exact font metrics (Pillow) | same + `font_registry` |
| Hard constraints (overflow, ellipse/rect safe width) | `fitting.py` `_evaluate_lines` |
| Thai segmentation + **project dictionary** (proper names) | `segmentation.py` (`project_dictionary` / `thai_dictionary` in project settings) |
| Canonical compute entry | `service.py` → `compute_block_typesetting` |

### 2.2 TypesettingSpec v2 (immutable artifact)
| Capability | Location |
|---|---|
| Schema + decision fields | `schemas.py` (`TYPESETTING_SCHEMA_VERSION = "2.0.0"`) |
| `decision_status`: `AUTO_APPLIED` \| `DEFAULTED` \| `NEEDS_REVIEW` | `service.py` |
| `render_fingerprint`, `spec_id`, `revision`, color/stroke/align | `schemas.py` / `service.py` |
| Engine constant | `LAYOUT_ENGINE_VERSION = "2.0.0"` |

### 2.3 Style Judge v1 (rules only)
| Capability | Location |
|---|---|
| Multi-signal Style Descriptor | `style_judge.py` |
| Template map + auto-apply only if conf ≥ 0.90 | `apply_style_descriptor_to_block` |
| Batch API | `POST /api/typesetting/style-judge` |
| Built-in template packs | `text_templates.py` |

### 2.4 Feedback instrumentation (from first suggestion)
| Capability | Location |
|---|---|
| JSONL events | `feedback.py` → default `data/feedback/typesetting_events.jsonl` |
| Env override | `HOUMI_TYPESETTING_FEEDBACK_PATH` |
| User API | `POST /api/typesetting/feedback` |
| Auto-log on compute | `log_decision_from_spec` in `compute_block_typesetting` |
| UI manual labels | ACCEPT / SYSTEM WRONG / PREFERENCE |
| Auto on manual template change | `applyTextTemplate` → `user_preference` event |

### 2.5 Parity (semantic / geometry / font — not pixel-perfect)
| Capability | Location |
|---|---|
| Helpers | `parity.py` |
| PNG Pillow reads Spec lines/color/**stroke** | `renderer.py` + `stroke.py` |
| PSD manifest from Spec (no live-field re-layout) | `psd_export.py` |
| Font missing → export blocked (no silent fallback) | `psd_export.py` preflight |
| Fabric preview stroke from Spec | `frontend/src/utils/fabricStroke.ts` + `Canvas.tsx` |
| Fabric dirty-check includes stroke | `fabricStrokeNeedsUpdate` in Canvas `hasChanged` (stroke-only Spec updates apply) |

### 2.6 UI (Typesetting workspace)
| Control | Behavior |
|---|---|
| **AUTO STYLE PAGE** | Style Judge whole page; snapshot for undo; conf≥0.90 apply |
| **UNDO AUTO STYLE** | Restore pre-run block fields + metadata snapshot |
| **SUGGEST ONLY** | Judge without template swap |
| **RECOMPUTE LAYOUT** | Page beam recompute |
| **REVIEW QUEUE** | Filter layer list to `NEEDS_REVIEW` |
| Layer badges | OK / DEF / REV / ST |
| Canvas outline colors | By decision status when Spec-backed |
| Inspector | confidences, reason codes, feedback buttons |

### 2.7 Contracts & harness
| Artifact | Path |
|---|---|
| Technical RFC | `docs/TYPESETTING_RFC_B_PLUS.md` |
| This expert summary | `docs/EXPERT_REVIEW_B_PLUS_TYPESETTING.md` |
| Benchmark CLI | `backend/scripts/benchmark_typesetting.py` |
| Benchmark outputs | `data/benchmarks/*.json` |

---

## 3. How to verify (commands & APIs)

### 3.1 Backend unit tests
```bat
cd E:\houmi\backend
.venv\Scripts\python.exe -m pytest tests/test_typesetting.py tests/test_style_judge.py tests/test_stroke_and_dictionary.py tests/test_layout_region.py tests/test_psd_roundtrip.py -q
```
**Expected:** exit 0 (76 tests collected/passed in the current set; full `pytest tests -q`: 125 passed).

### 3.2 Frontend unit tests
```bat
cd E:\houmi\frontend
npm test -- --run src/tests/decisionStatus.test.ts src/tests/typesetting.test.ts src/tests/autoStyleAndStroke.test.ts
```
**Expected:** exit 0 (20 tests in this gate set; full frontend suite: 53 passed).

### 3.3 Synthetic benchmark
```bat
cd E:\houmi\backend
.venv\Scripts\python.exe scripts\benchmark_typesetting.py --synthetic 20 --repeats 3
```
**Expected:** JSON under `data/benchmarks/`; reports `engine_version`/`schema_version` `2.0.0`; `gate_hints.p95_page_le_2000ms: true` on reference hardware used in development (~p95 &lt; 1s for 20 blocks).

### 3.4 HTTP APIs
| Method | Path | Notes |
|---|---|---|
| POST | `/api/typesetting/recompute/page/{page_id}` | Persist Specs |
| POST | `/api/typesetting/style-judge` | Body: `{ "page_id", "apply_template", "confidence_auto_threshold": 0.90, "recompute_layout": true }` |
| POST | `/api/typesetting/feedback` | `change_reason`: `accepted` \| `system_wrong` \| `user_preference` |
| POST | `/api/typesetting/preflight` | No DB / no feedback pollution |

### 3.5 Project dictionary (optional)
In project `settings`:
```json
{ "project_dictionary": ["เทพแห่งสุริยา", "ชื่อเฉพาะ"] }
```
Engine will not split those spans across line breaks.

---

## 4. Decision Gates & KPI posture

| Gate | Intent | Status for expert reviewers |
|---|---|---|
| **0 Baseline Accepted** | Dataset 300–500 + GT splits/baseline, Spec v2, parity defs, RFC, feedback sink | **NOT PASSED / evidence incomplete**. Engineering artifacts and synthetic harness exist, but the required real corpus + held-out baseline are still missing and block Production merge. |
| **1 Line Engine** | overflow 0%, Thai grapheme/token rules, line accept ≥85% on held-out | **Engineering path ready**; accept-rate KPI needs human GT (open). Synthetic overflow_count 0 on harness samples. |
| **2 Style Judge** | high-conf ≥0.90 precision ≥90% held-out + coverage | **Rules v1 shipped**; precision not certified without held-out labels. |
| **3 Export** | PNG/JPEG/PSD same Spec; no silent font fallback | **Code path enforced**; full page round-trip on production manga still QA. |

### KPI notes (honest)
- Thai: engine guarantees **no mid-grapheme / mid-token split** for tokens it emits; dictionary covers proper names; **does not** claim 100% linguistic word correctness of PyThaiNLP.
- High-confidence template accept: defined as **calibrated conf ≥ 0.90** on held-out — measurement pending GT.
- Performance: standard page ≤20 blocks; p95 ≤2s target; synthetic harness on dev CPU meets p95 ≤2s.
- Parity: **semantic 100%** required; geometry center ≤ max(2px, 1% box); **not** pixel-perfect PSD vs browser.

---

## 5. Remaining gaps & intentional deferrals

| Item | Status |
|---|---|
| Quality Contract 300–500 real boxes + train/tune/held-out | **Deferred** — needs human labeling (explicit non-goal of this close-out) |
| Tiny ML / Local LLM | **Not approved** until Gate fail + rules cannot fix + event evidence |
| Full Feedback Platform (dashboard, dataset export UI) | Phase 3 — logging exists; product platform not built |
| Review Queue depth (assign, SLA, multi-page queue) | **Minimal filter shipped**; full queue product deferred |
| Stroke on PSD text engine | Spec/manifest carry stroke fields; Photoshop engine rendering of stroke depends on CLI capabilities — validate in QA |
| Calibrated confidence model | Rule scores only; calibration deferred |
| PPTX deck sync to B+ | Deferred; Marp MD is source of direction |

### Closed in this close-out (were open handoff items)
- Auto Style **undo** (page snapshot)
- Review **filter** (NEEDS_REVIEW queue toggle)
- Stroke draw-through **Pillow + Fabric** from Spec
- Auto-feedback on **manual template** change
- Project **dictionary** hook

---

## 6. Architecture diagram (shipped)

```
Translation + Balloon geometry
        │
        ├─► Style Judge (rules) ──► suggested_template + style_confidence
        │         │
        │         └─► optional template apply if conf ≥ 0.90
        │
        ▼
segment_text (+ project_dictionary)
        │
        ▼
beam/greedy candidates × font-size search
        │
        ▼
hard constraints → Decision Ranker (score_layout)
        │
        ▼
TypesettingSpec v2 + decision_status + reason_codes
        │
        ├─► Canvas (Fabric, stroke from Spec)
        ├─► PNG (Pillow, stroke from Spec)
        └─► PSD CLI manifest (Spec fields only)
        │
        ▼
feedback JSONL (suggested / auto / user reasons)
```

---

## 7. Code map (quick)

```
backend/app/services/typesetting/
  schemas.py          Spec v2
  service.py          compute + decision_status
  fitting.py          beam + ranker
  style_judge.py      Style Judge v1
  feedback.py         JSONL events
  parity.py           semantic/geometry helpers
  stroke.py           Pillow stroke kwargs
  segmentation.py     Thai + dictionary
backend/app/routes/typesetting.py
backend/scripts/benchmark_typesetting.py
frontend/src/utils/{typesetting,decisionStatus,fabricStroke,autoStyleSnapshot}.ts
frontend/src/App.tsx, components/Canvas.tsx
docs/TYPESETTING_RFC_B_PLUS.md
docs/EXPERT_REVIEW_B_PLUS_TYPESETTING.md   ← this file
```

---

## 8. Recommended expert checklist

1. Confirm versions in `schemas.py` / `service.py` / frontend `CURRENT_*` are all **2.0.0**.
2. Run §3.1–3.3; archive logs with PR/review packet.
3. Spot-check one real page: Auto Style → Review Queue → Undo → Export PNG/PSD with missing-font blocked.
4. Confirm no ML weights or LLM runtime were introduced under `typesetting/`.
5. Treat Gate 1–2 **accept-rate KPIs** as open until GT exists; do not sign Production-ready on synthetic alone.

---

## 9. Sign-off block (for reviewers)

| Role | Name | Date | Result |
|---|---|---|---|
| Engineering | | | ☐ Approve code path · ☐ Request changes |
| Product / PO | | | ☐ Direction still B+ · ☐ KPI waiver notes |
| QA | | | ☐ Export smoke · ☐ UI smoke |

**Bottom line for experts:** B+ Phase 0–2 **engineering spine is implemented and test-backed**. Production KPI certification on real manga remains **data-gated**, not code-gated. ML/LLM remain **explicitly out of scope** until gates fail with evidence.
