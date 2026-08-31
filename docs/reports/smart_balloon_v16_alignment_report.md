# Smart Balloon V16 Alignment & Benchmark Report

สถานะ: เสร็จสิ้นรอบสอง (2026-08-26) — ปิด gap, วัดผลด้วย GT จริง (SAM-generated), ตัดสิน default จากข้อมูล

## ปัญหาที่แก้ (จากการวิเคราะห์ก่อนหน้า)

1. **V16 เป็น dead code** — `get_smart_balloon_adaptive_enabled()` ไม่เคยถูกเรียก, `compute_smart_balloon_bounds()` ไม่ส่ง `use_adaptive` → setting "smart_balloon_adaptive" ไร้ผล
2. **Schema ไม่ตรง V15** — V16 ขาด `smart_*`, `crop_mask`, `crop_offset`, `raw_contour_points`, `row_width_constraints`, `metadata` ซึ่ง pipeline.py (4 จุด), inpainter.py:655 และ contour_fitting.py ใช้จริง → ถ้าเปิดจริง mask asset จะไม่ถูกบันทึก และ text removal เสีย contour raw
3. **archetype = "adaptive" placeholder** — บายพาส logic SPIKY_FUZZY (spike preservation)

## สิ่งที่แก้แล้ว

### smart_balloon_adaptive.py (เขียนใหม่)

- คืน schema ครบเท่า V15 ทุก field + เก็บ `version`, `bg_stats` ไว้ตาม contract เดิม
- ใช้ classifier จริง (`classify_balloon_archetype`) + body isolation แบบ V15 (skip morphology เมื่อ SPIKY_FUZZY)
- **Conjoined guard**: rival ที่ share white blob / overlap ≥ 0.10 → return `fallback="conjoined_deferred_to_v15"` ให้ dispatcher ไปทำ waist-slicing ที่ V15 (ไม่ duplicate logic)
- `multi_seed_adaptive_flood_fill` คืน signature เดิม (mask เดียว) เพื่อไม่พัง test เดิม

### detector.py + pipeline.py (wiring)

- `compute_smart_balloon_bounds(..., settings=None)` — resolve ผ่าน `get_smart_balloon_adaptive_enabled(settings)`; default **True** ตาม docstring เดิมของ config (auto-fallback V15 เมื่อ fail)
- Call sites ทั้ง 4 ใน pipeline.py ส่ง project settings แล้ว → toggle รายโปรเจกต์ใช้ได้จริง (`"smart_balloon_adaptive": false` เพื่อปิด)

### Tests

- `test_smart_balloon_adaptive.py`: +5 tests (schema parity, smart_*=safe_bbox, conjoined defer, near-duplicate ไม่ defer, dispatcher คืน v16 schema) — **31 passed**
- Suite เดิมไม่พัง (inpainter failures = pre-existing ก่อนแก้)

## ผล Benchmark (150 records, dev+test split, real manga)

| engine | n | success | fallback | p50 | p95 |
|---|---|---|---|---|---|
| v15 | 150 | 0.900 | 15 × contour_too_small | 93ms | 188ms |
| v16 | 150 | 0.900 | 15 × contour_too_small (record เดียวกันทุกตัว) | 154ms | 296ms |

ข้อสังเกต:

- **Coverage เท่ากันเป๊ะ** — record ที่ fail 15 ตัวเป็นชุดเดียวกันทั้งคู่ (รวมกันในโปรเจกต์ 04d41f9e เป็นหลัก = หน้ายาก/พื้นเข้ม)
- **V16 ช้ากว่า ~55ms/บอลลูน (median)** จาก multi-seed flood fill 9 seeds + Sobel

## ผล Benchmark รอบสอง — GT-scored (263 GT masks จาก SAM 2.1)

สร้าง GT ด้วย `bootstrap_gt_masks.py` (SAM box-prompt + QC gates: bbox cover ≥0.85, area ratio 1.15-30×, erode 3px ตัด stroke) — **independent จาก V15/V16 ทั้งหมด**, ตรวจสายตาผ่าน QC sheets ใน `datasets/smart_balloon_bench/qc/`

| engine | scored | iou_mean | iou_median | precision | utilization | containment | p50 |
|---|---|---|---|---|---|---|---|
| v15 | 241 | **0.680** | **0.731** | 0.888 | **0.740** | 0.874 | **92ms** |
| v16 | 241 | 0.661 | 0.719 | **0.901** | 0.702 | **0.888** | 144ms |
| bbox | 263 | 0.612 | 0.632 | 0.977 | 0.623 | 0.966 | 0ms |

**Paired (n=241):** v15 ชนะ 42 / v16 ชนะ 8 / เสมอ 191 (79%) — ΔIoU mean +0.020 ฝั่ง v15

การตีความ:

- **V15 ครอง IoU + utilization** (ใช้พื้นที่ใส่ตัวอักษรได้มากกว่า bbox baseline ถึง +19%)
- V16 ได้ precision/containment ดีกว่าเล็กน้อย = ปลอดภัยกว่าแต่เสียพื้นที่ ~4%
- bbox baseline ยืนยันปัญหาเดิม: ปลอดภัยสุดแต่ทิ้งพื้นที่ 38% — นี่คือเหตุผลที่ Smart Balloon มีค่า
- 22 dual-fallbacks คือหน้า textured/gradient box (เช่น system-message panel) ที่ flood-fill ทำงานไม่ได้เลย — SAM จับได้หมด → เป็นหลักฐานว่าทางออกระยะยาวคือ SAM/learned segmentation ไม่ใช่ tune flood-fill ต่อ

## การตัดสินใจ (data-driven)

**เปลี่ยน `smart_balloon_adaptive` default True → False (opt-in)** เพราะ:

1. คุณภาพไม่ดีกว่า (แพ้ paired 42:8) ทั้งที่แพงกว่า +52ms (+57%)
2. จุดขายตามทฤษฎี (gray/gradient) ไม่ปรากฏในข้อมูลจริง — fallback set เท่าเดิม
3. Wiring ครบแล้ว โปรเจกต์ที่มีหน้าเทาเยอะเปิดเองได้ทันทีผ่าน `{"smart_balloon_adaptive": true}`

## รอบสาม — SAM Box Fallback เข้า production path

### ปัญหาที่พบจากการวัด production path

เพิ่ม engine `prod` (ผ่าน `compute_smart_balloon_bounds` จริง) ใน harness → พบว่า fallback เดิมถูก gate ด้วย "ต้องขาว" 2 ชั้น (white-component check + white-seed check) ทำให้ textured/gradient box **ไม่มีทางถึง SAM เลย** และ legacy `clean_seed_balloon` ที่หลุดมาได้ให้ IoU ~0.12 (mask ผิดตำแหน่ง)

### สิ่งที่แก้

`detector._sam_box_fallback_result()` — SAM 2.1 box-prompt ทำงาน**บนภาพเต็มหน้า** (บทเรียนจากการ debug: prompt บน crop ให้ cover แค่ 0.14-0.87 จาก record เดียวกัน ส่วน full-page ผ่าน gate หมด — encoder cache ต่อหน้าทำให้จ่าย encode ครั้งเดียวต่อหน้า) พร้อม:

- QC gates เดียวกับ GT bootstrap: bbox cover ≥ 0.85, area ratio 1.15-30×
- คืน schema เต็ม V15 (smart_*, crop_mask+crop_offset แบบ window, contour, row_width_constraints, archetype จาก classifier จริง)
- Chain ใหม่: `V15 → SAM box fallback → legacy white path → bbox` — เครื่องไม่มี SAM = คืน None แล้วไป legacy ตามเดิม (graceful)

### ผล (GT-scored 263 records)

| path | success | iou_mean | util | contain | p50 |
|---|---|---|---|---|---|
| v15 เดิม | 0.916 (22 fail) | 0.680 | 0.740 | 0.874 | 92ms |
| **prod ใหม่** | **1.000 (0 fail)** | **0.691** | **0.746** | 0.884 | 106ms |

- **Rescue ครบ 22/22 hard cases** ด้วย IoU mean **0.805** (min 0.787) — สูงกว่าค่าเฉลี่ยรวม (system-panel รูปทรงเรขาคณิตชัด SAM ตัดได้เด็ด)
- **Regression = 0**: record ที่ V15 สำเร็จ prod คืนผล identical ทุกตัว (paired delta = 0.0000, ชนะ/แพ้ 0-0) — fallback ทำงานเฉพาะเมื่อ V15 ล้ม
- ต้นทุนเฉลี่ย +14ms/บอลลูน (จ่ายเต็มเฉพาะ record ที่ V15 ล้ม)

### บทเรียน

1. วัด production path ด้วย harness ก่อนแก้เสมอ — จุดพังจริง (whiteness gates) ต่างจากที่คาด
2. Prompt context มีผลมากกับ SAM: full-page >> crop สำหรับ box prompt
3. GT จาก full-page SAM ทำให้เทียบ fallback ได้ตรง domain

## รอบสี่ — GT Audit, กระจาย GT, และ Inset Sweep

### GT Confidence Audit (`audit_gt_confidence.py`)

Cross-validate pseudo-GT ด้วย prompt strategy ที่สอง (point prompts: center + 4 มุม) — tier จาก IoU ระหว่างสอง strategy:

- **HIGH ≥0.85: 155 masks** = verified-by-agreement (อ้างอิงหลักได้)
- MEDIUM 0.70-0.85: 88
- **LOW <0.70: 113** → review queue `datasets/smart_balloon_bench/review/` (ตรวจสายตาแล้วเจอทั้ง GT รั่วจริง เช่น หลุดลงภาพพื้นหลัง/บอลลูนติดกัน และเคส spiky ที่ทั้งสอง strategy มี artifact)

### GT ขยายข้ามโปรเจกต์

`bootstrap_gt_masks.py --per-project` → **356 masks จาก 37 projects** (เดิม 263 จาก ~4) — dev 154 / test 202

### ผล Production Path บน GT เต็ม (356)

| tier | n | iou | precision | utilization | containment |
|---|---|---|---|---|---|
| **HIGH (verified)** | 155 | **0.711** | **0.939** | 0.733 | **0.931** |
| MEDIUM | 88 | 0.722 | 0.922 | 0.777 | 0.904 |
| LOW (GT ต้องรีวิว) | 113 | 0.584 | 0.826 | 0.692 | 0.802 |
| รวม | 356 | 0.673 | 0.899 | 0.731 | 0.883 |

success ยังเป็น **1.000**, p50 62ms — ตัวเลขอ้างอิงที่เชื่อถือได้คือแถว HIGH

### Inset Sweep (`sweep_inset.py`, HIGH tier)

| inset | iou | precision | utilization | containment |
|---|---|---|---|---|
| 0.050 | 0.776 | 0.915 | **0.812** | 0.899 |
| **0.075** | 0.746 | 0.920 | **0.775** | 0.910 |
| 0.100 (default) | 0.712 | 0.924 | 0.737 | 0.917 |
| 0.125 | 0.677 | 0.927 | 0.700 | 0.922 |
| 0.150 | 0.642 | 0.929 | 0.662 | 0.925 |

**ข้อเสนอ:** `0.075` ให้พื้นที่ใส่ตัวอักษร +3.8pp ที่ต้นทุน precision -0.4pp / containment -0.7pp — เป็น candidate ที่ควร A/B บนหน้าเรนเดอร์จริง (เฉพาะไทยที่มีวรรณยุกต์บน-ล่าง) ก่อนเปลี่ยน default; ยังไม่ flip ตอนนี้

## รอบห้า — Typesetting-level Benchmark และ Inset Default ใหม่

### `benchmark_typesetting.py` — วัดระดับพิกเซลตัวอักษรจริง

ปิดช่องว่าง metric สุดท้ายของ v0.4 ("glyph-alpha containment"): รัน production engine → fit ข้อความจริงด้วย `fit_text_to_smart_balloon_shape` → render ด้วย PIL (ฟอนต์ไทย/ญี่ปุ่น/จีน/อังกฤษ) → นับพิกเซล glyph ที่หลุดนอก GT interior

### ผล A/B inset 0.075 vs 0.10 (120 records, 952 paired configs)

| metric | ผล |
|---|---|
| font size | **+1.4px เฉลี่ย (481 ใหญ่ขึ้น / 0 เล็กลง)** |
| containment (HIGH tier, n=288) | **+0.0004 = ไม่เสียเลย** |
| overflow แย่ลง | 8/952 configs (0.8%) — กระจุกใน GT ที่ยังไม่ verify (04d41f9e) |
| Thai containment | short 0.946 (เท่าเดิม) / long 0.889 (-0.6pp) — วัดจากพิกเซลรวมวรรณยุกต์แล้ว |

**การตัดสิน: เปลี่ยน `smart_balloon_inset_ratio` default 0.10 → 0.075** — ตัวอักษรใหญ่ขึ้นทุกกรณีที่ layout อนุญาต โดยความปลอดภัยระดับพิกเซลบน verified GT ไม่ต่าง (โน้ต: fitter ยังมี EDT safe margin 8% ซ้อนอยู่อีกชั้น)

### ข้อค้นพบเพิ่ม: V15 false-positive success

benchmark ระดับนี้จับเคสที่ mask-IoU เฉลี่ยมองข้าม: V15 บาง record "สำเร็จ" แต่ flood fill ลามไปก้อนขาวข้างเคียง (glyph อยู่ผิดบอลลูนทั้งหมด, containment 0.0) → ต่อไปควรเพิ่ม seed-region sanity check (เช่น mask ต้องครอบ text bbox ≥ 85% แบบเดียวกับ SAM gate)

## รอบหก — V15 Sanity Gate และ CI Smoke Benchmark

### Text-bbox Coverage Gate

V15 + V16 เพิ่ม gate หลังเลือก component หลัก: **polygon ต้องครอบ text bbox ≥ 85%** (เกณฑ์เดียวกับ SAM gate) — ไม่ผ่าน = fallback แล้วไป SAM box fallback ทันที แก้โหมด false-positive success ที่พบจากรอบห้า

### ผล (GT เต็ม 356, prod path)

| metric | ก่อน gate | หลัง gate | Δ |
|---|---|---|---|
| IoU mean | 0.673 | **0.714** | +4.1pp |
| IoU median | 0.723 | **0.746** | +2.3pp |
| precision | 0.899 | **0.923** | +2.4pp |
| utilization | 0.731 | **0.770** | +3.9pp |
| containment | 0.883 | **0.908** | +2.5pp |
| success | 1.000 | 1.000 | = |

- **ทุก metric ดีขึ้น ไม่มีด้านลบ** — gate แปลง false-positive เป็น SAM rescue (ตัวอย่าง: record ที่เคย containment 0.0 → IoU 0.855 / containment 0.9999)
- HIGH tier IoU: 0.711 → **0.748**

### CI Smoke Benchmark

`test_smart_balloon_smoke_benchmark.py` — รัน harness บน 6 GT records แรกในทุก pytest run (v15 + prod path), skip อัตโนมัติเมื่อไม่มี GT/SAM — กัน regression ของ production path ตั้งแต่ตอนนี้เป็นต้นไป

## คำแนะนำถัดไป

1. Human-review LOW queue 113 masks
2. Tune classifier thresholds — **ต้องมี human archetype labels ก่อน** (tune กับ label ของ engine เอง = วนวน) — เพิ่มช่อง archetype ใน review flow จึงจะคุ้ม
3. Learned segmentation (fine-tune บน GT ที่สะอาดแล้ว) — ก้าวถัดไปเมื่อ GT ผ่านการรีวิว
4. Vertical CJK / 3-candidate UI / confidence calibration (ตาม roadmap v0.4)

## Reproduce

```bash
python backend/scripts/bootstrap_gt_masks.py --per-project 3 --limit 150 --skip-existing
python backend/scripts/audit_gt_confidence.py
python backend/scripts/benchmark_smart_balloon.py run \
    --manifest datasets/smart_balloon_bench/manifest.jsonl \
    --engines prod --gt-only \
    --out-dir data/benchmarks/smart_balloon/prod_final
python backend/scripts/sweep_inset.py
python backend/scripts/benchmark_typesetting.py --limit 120 --insets 0.10,0.075
```

