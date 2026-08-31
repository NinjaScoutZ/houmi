# Smart Balloon Typesetting Research & Development

คลังเอกสารและงานวิจัยระบบตรวจจับรูปทรงบอลลูนและการจัดวางข้อความแบบปรับตัวอัตโนมัติ (**Smart Balloon Engine**) สำหรับมังงะและเว็บตูน

---

## 🌟 งานวิจัยล่าสุด (Latest Research)

### 📌 [Smart Balloon V15: Spiky & Fuzzy Edge Classification (`v15_fuzzy_edge_research/`)](v15_fuzzy_edge_research/README.md)
* **โฟลเดอร์งานวิจัย:** [`research/v15_fuzzy_edge_research/`](v15_fuzzy_edge_research/README.md)
* **หัวข้องานวิจัย:** การจำแนกบอลลูนประเภท **ขอบขนฟู (Feathered/Fuzzy)**, **บอลลูนความคิดแบบฟุ้งกระจาย (Thought Cloud Auras)**, และ **หนามแหลม (Scream/Shock Bursts)** ด้วย Raw Image Canny Edge Density & Normal Gradient Analysis
* **ผลลัพธ์:** จำแนก `SPIKY_FUZZY` แม่นยำ 100% (Edge Density 26.2%) ตัดแยกเอวบอลลูนคู่ และคงสภาพเส้นขนโดยไม่ถูก Morphology ทำลาย (เวลาประมวลผล ~13-21 ms)

---

## 📑 สารบัญงานวิจัยตามรุ่น (Research Versions)

1. **[V15] Spiky & Fuzzy Edge Research (ล่าสุด):** [`v15_fuzzy_edge_research/README.md`](v15_fuzzy_edge_research/README.md)
2. **[V2] Geodesic Voronoi & Adaptive Crop Research:** [`REPORT_TH.md`](REPORT_TH.md), [`smart_balloon_v2.py`](smart_balloon_v2.py), [`SMART_BALLOON_V2_FINDINGS.md`](SMART_BALLOON_V2_FINDINGS.md)
3. **[V1] Typesetting Engine Initial Research:** [`research_typesetting_report.md`](research_typesetting_report.md)

---

## 📂 โครงสร้างโฟลเดอร์งานวิจัย (Folder Structure)

```
research/
├── v15_fuzzy_edge_research/       # 🌟 [NEW] งานวิจัยล่าสุด: V15 Spiky/Fuzzy Edge Classification
│   ├── README.md                  # เอกสารสรุปงานวิจัย V15 พร้อมโค้ด รูปภาพ และ Benchmark
│   ├── fuzzy_conjoined_comparison.png # ภาพผลการทดสอบ Canny Edges, Contours & Typesetting
│   ├── test_fuzzy_conjoined.py    # สคริปต์ทดสอบภาพ Conjoined Fuzzy Balloon
│   └── generate_fuzzy_comparison.py # สคริปต์สร้างภาพ Visual Benchmark 3 แผง
├── smart_balloon_v2.py            # สคริปต์วิจัย V2 (Geodesic Voronoi)
├── REPORT_TH.md                   # รายงานวิจัยฉบับ V2 (ภาษาไทย)
├── SMART_BALLOON_V2_FINDINGS.md   # รายงานผล V2 (ภาษาอังกฤษ)
├── SMART_BALLOON_V2_SUMMARY.txt   # สรุปผลการรัน 9 ตัวอย่าง
└── images/                        # ชุดภาพตัวอย่างสำหรับทดสอบ
```
