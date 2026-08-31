# Smart Balloon Benchmark Harness

เอกสารนี้อธิบายเครื่องมือวัดผล Smart Balloon ที่สร้างตามแผนใน `smart_balloon_research_v0.4.md` (หัวข้อ "แผนวิจัยที่ทำซ้ำได้") — จุดประสงค์คือทำให้ทุกการพัฒนาต่อจากนี้วัดผลได้จริง ไม่ใช่ "100% success" จากภาพเดียว

## ไฟล์ที่เกี่ยวข้อง

| ไฟล์ | หน้าที่ |
|---|---|
| `backend/scripts/benchmark_smart_balloon.py` | CLI entry (`bootstrap`, `run`) |
| `backend/scripts/bootstrap_gt_masks.py` | สร้าง GT ด้วย SAM box-prompt (`--per-project` กระจายข้ามเรื่อง) |
| `backend/scripts/audit_gt_confidence.py` | tier ความน่าเชื่อถือ GT (box vs point prompt) + review queue |
| `backend/scripts/sweep_inset.py` | sweep inset_ratio กับ GT |
| `backend/scripts/benchmark_typesetting.py` | **glyph-level benchmark** — render ข้อความจริง วัด containment ระดับพิกเซล (A/B inset ฯลฯ) |
| `backend/tests/test_smart_balloon_smoke_benchmark.py` | smoke benchmark 6 records ใน pytest — กัน regression ของ production path |
| `backend/scripts/smart_balloon_bench/manifest.py` | schema manifest + bootstrap + แบ่ง split ตามเรื่อง |
| `backend/scripts/smart_balloon_bench/metrics.py` | IoU / precision / utilization / containment + aggregation |
| `backend/scripts/smart_balloon_bench/engines.py` | adapter: `bbox` (baseline), `v15` (production), `v16` (adaptive) |
| `backend/scripts/smart_balloon_bench/reporting.py` | JSON results, Markdown report, preview overlays |
| `backend/tests/test_smart_balloon_benchmark.py` | unit tests (14 cases, synthetic images) |

## เริ่มใช้งาน

### 1. Bootstrap manifest

```bash
python backend/scripts/benchmark_smart_balloon.py bootstrap
```

- อ่าน `data/projects/*/training/balloons.json` ทุกโปรเจกต์
- บอลลูนอื่นในหน้าเดียวกันถูกใส่เป็น `rival_boxes` ให้ครบ เพื่อให้ conjoined splitting ถูก exercise แบบ production
- แบ่ง split **ตามโปรเจกต์ (เรื่อง) ด้วย md5 hash** — ไม่สุ่มรายหน้า ป้องกัน style leakage ตามที่ v0.4 กำหนด
- ผลล่าสุด: **8,496 records จาก 151 projects** (train 5,367 / dev 1,300 / test 1,829) → เกินเป้า 200 blocks ของ v0.4 แล้ว

Output: `datasets/smart_balloon_bench/manifest.jsonl` (JSONL)

### 2. Run benchmark

```bash
python backend/scripts/benchmark_smart_balloon.py run \
    --manifest datasets/smart_balloon_bench/manifest.jsonl \
    --engines bbox,v15,v16 \
    --splits dev,test \
    --previews 12
```

Options สำคัญ:

- `--engines` — `bbox` = text bbox passthrough (baseline เดิม), `v15` = engine หลัก, `v16` = V15 + adaptive path
- `--limit N` — รันเฉพาะ record แรก N ตัว (smoke test)
- `--margin-px 8` — ระยะ margin สำหรับ metric containment
- `--previews N` — จำนวนภาพ overlay สำหรับตรวจตา

Output ต่อรัน (default `data/benchmarks/smart_balloon/<timestamp>/`):

- `results_*.json` — ผลราย record + aggregates + git commit + config (reproducibility)
- `report_*.md` — ตารางเทียบ engine, breakdown ตาม balloon_type / archetype / split, worst-10 records
- `previews/` — overlay: ส้ม = text bbox, แดง = GT contour, เขียว = safe polygon

## Ground Truth Masks

GT ปัจจุบันสร้างอัตโนมัติด้วย SAM 2.1 (independent จาก V15/V16) ผ่าน `backend/scripts/bootstrap_gt_masks.py`:

```bash
python backend/scripts/bootstrap_gt_masks.py --limit 300 --skip-existing
```

- ใช้ text bbox เป็น box prompt บนภาพเต็มหน้า (encoder cache ต่อหน้า — หน้าเดียวหลายบอลลูนจ่าย encode ครั้งเดียว)
- QC gates: bbox coverage ≥ 0.85, area ratio 1.15–30×, component เดียว + อุดรู, erode 3px ตัด stroke
- ผ่าน gate → บันทึก `datasets/smart_balloon_bench/gt/<record_id>.png` + QC overlay ใน `qc/` + อัปเดต manifest อัตโนมัติ
- สถานะล่าสุด: **263 masks** (dev 111 / test 152) — เกินโควตา 200 ของ v0.4
- หมายเหตุ: เป็น pseudo-GT — ก่อนตัดสิน release ใหญ่ควรมี human-verified subset เทียบ bias

รัน benchmark เฉพาะ record ที่มี GT:

```bash
python backend/scripts/benchmark_smart_balloon.py run --gt-only --engines v15,v16,bbox ...
```

เมื่อมี GT แล้ว harness จะคำนวณอัตโนมัติ:

| Metric | ความหมาย | อ่านว่าอย่างไร |
|---|---|---|
| `mask_iou` | IoU ระหว่าง safe polygon กับ GT | สูง = รูปทรงตรง |
| `precision` | สัดส่วน safe ที่อยู่ใน GT | ต่ำ = ล้ำออกนอกบอลลูน (clipping) |
| `utilization` | สัดส่วน GT ที่ safe ครอบ | ต่ำ = เสียพื้นที่ใส่ตัวอักษร |
| `containment` | สัดส่วน safe ที่อยู่ใน GT erode 8px | layout safety proxy ของ v0.4 |

แนะนำเริ่มจาก dev/test split ก่อน 200–300 blocks ครอบคลุมทุก archetype (oval / cloud / burst / caption / stitched) ตามโควตา v0.4

## เกณฑ์การตัดสิน (ตาม v0.4)

- เทียบ candidate ใหม่กับ baseline ด้วย manifest + commit เดียวกัน
- release gate: containment/precision ดีขึ้นโดย utilization และ font-too-small ไม่แย่ลง และ fallback rate ตรวจสอบได้
- ตัวเลข p50/p95 runtime ใช้ตัดสิน regression ด้าน speed

## ข้อจำกัดที่รู้ตัว

- ~~`v16` ผ่าน `use_adaptive=True` ให้ V15 dispatcher — ผลที่ได้ยังขาด field บางตัว~~ **แก้แล้ว** (ดู `smart_balloon_v16_alignment_report.md`) — V16 คืน schema เท่า V15 พร้อม conjoined guard
- GT เป็น pseudo-GT จาก SAM (263 masks แล้ว) — อ้างเลข IoU ได้แต่ควรมี human-verified subset ก่อน release gate ใหญ่
- bootstrap ครอบเฉพาะโปรเจกต์ที่มี `training/balloons.json`
