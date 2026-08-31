# Smart Balloon — งานวิจัยร่วมและแผนพัฒนา v0.4

เอกสารนี้เป็นฉบับที่ผูกกับ implementation ปัจจุบันของ Houmi โดยแยกให้ชัดเจนระหว่างหลักการ, code ที่มีอยู่จริง, และผลทดลองที่ยังต้องพิสูจน์

## สถานะข้อสรุป

เป้าหมายที่ถูกต้องไม่ใช่การทำให้ “พื้นที่หมึกกิน 70% ของบอลลูน” แต่คือเลือกขนาดฟอนต์และการตัดบรรทัดที่ใหญ่ที่สุดเท่าที่ glyph ที่ render จริงจะอยู่ภายในพื้นที่ปลอดภัยของบอลลูนได้ พร้อมรักษาสมดุลของบรรทัดและ manual line break

ข้อกำหนดนี้สอดคล้องกับ pipeline ของ Houmi มากกว่า density คงที่ เพราะข้อความภาษาไทย/ญี่ปุ่น/ละตินมีสัดส่วนหมึก, bearing, diacritic และ line-height ต่างกัน

## สิ่งที่พัฒนาแล้วใน v0.4

### 1. Contour width profile

เพิ่ม `backend/app/services/typesetting/contour_fitting.py` ซึ่ง:

- รับ binary mask และ erode ตาม padding ที่กำหนด
- หา contiguous run ของแต่ละแถว ไม่ใช้ `min/max` ที่อาจพาดข้ามช่องว่าง
- เลือก run ที่มีศูนย์กลางใกล้แกนข้อความก่อน แล้วจึง fallback เป็น run ที่ยาวที่สุด
- วัดความกว้างเป็น band รอบ line box ไม่ใช่ sample เพียง 1 พิกเซล
- คืน `None` เมื่อ mask เล็ก/ว่าง/ไม่น่าเชื่อถือ เพื่อให้ engine เดิมทำงานต่อ

### 2. เชื่อมกับ production line engine

`compute_best_layout()` รับ `line_width_provider` แบบ optional เมื่อเปิด `contour_layout` ระบบจะใช้ความกว้างจาก mask ในการประเมินทุก candidate; เมื่อปิดหรือโหลด mask ไม่ได้ จะกลับไปใช้ ellipse/rectangle safety factor เดิม

ผลลัพธ์ถูกบันทึกใน `TypesettingSpec.metrics.contour_layout` และ `LayoutRegionSpec` รองรับ `mask_path`, `mask_area`, `contour_version` เพื่อทำ audit/reproducibility

### 3. Mask provenance

- auto pipeline เก็บ page-space mask และ path ไว้กับ layout region เมื่อมี smart mask
- manual SAM selection เก็บ mask ที่เลือกและเปิด `contour_layout` ให้บล็อกนั้นโดยอัตโนมัติ
- การเปลี่ยน mask/path ทำให้ typesetting signature เปลี่ยนและคำนวณ spec ใหม่

## ขอบเขตที่ยังไม่ควรอ้างว่าเสร็จ

- ยังไม่ได้ตรวจ alpha ของ glyph rasterized จริงทุกพิกเซลกับ mask; width profile เป็น safe approximation ระยะที่หนึ่ง
- ยังไม่มี ground-truth test set สำหรับตอน “ดาว” 110 จึงห้ามรายงาน 100% หรือ clipping 0%
- ยังไม่รองรับ vertical CJK แบบเต็มรูปแบบ เพราะ renderer มาตรฐานของระบบยังเป็น horizontal layout
- contour fitter ยังเป็น opt-in สำหรับ auto detection จนกว่าจะผ่าน benchmark; manual mask ที่ผู้ใช้ยืนยันจะเปิดใช้ทันที

## แผนวิจัยที่ทำซ้ำได้

### ชุดข้อมูล

แบ่ง train/dev/test ตามเรื่องหรือ chapter ไม่ใช่สุ่มรายหน้า เพื่อป้องกันหน้าที่มี style เดียวกันรั่วข้ามชุด ควรมีอย่างน้อย 200 blocks แยกตามวงรี, วงกลม, cloud, burst/SFX, caption, stitched และบอลลูนที่มี texture

สำหรับแต่ละ block ต้องเก็บ:

- source image hash และ page/block id
- ground-truth interior mask หรือ polygon
- ข้อความและ font ที่ใช้ render
- manual line breaks ถ้ามี
- model/config/engine version และผล candidate ที่เลือก

### Metrics

- mask: IoU/Dice ต่อ block และแยกตามชนิดบอลลูน
- layout safety: สัดส่วน glyph/outline pixels ที่อยู่นอก `safe_mask`
- fit: overflow rate, minimum font size, line-balance coefficient, fallback rate
- reproducibility: runtime p50/p95 และผลเมื่อ rerun ด้วย input เดิม
- human review: blind pairwise preference ระหว่าง bbox, ellipse และ contour

เกณฑ์ release ควรตั้งหลังเก็บ baseline ไม่ใช่กำหนด 65–75% ล่วงหน้า เช่น ต้องลด outside-mask pixels โดยไม่เพิ่ม overflow หรือ font-too-small อย่างมีนัยสำคัญ และต้องมี fallback ที่ตรวจสอบได้

## การใช้งานทดลอง

ตั้งค่า project:

```json
{
  "enable_contour_layout": true
}
```

หรือใส่ `contour_layout: true` ใน metadata ของ block ที่มี `mask_path` โดยตรง การเปิดใช้ auto contour ควรทำบน dev set ก่อน แล้วจึงเปิดเป็นค่าเริ่มต้นหลังมีผล test set ที่แยกเรื่องแล้ว

## คำถามวิจัยรอบถัดไป

1. glyph-alpha containment ให้ผลดีกว่า width profile มากน้อยเพียงใดเมื่อมีหาง/รูปร่างเว้า
2. การเลือก contiguous run ที่ใกล้ศูนย์กลางเหมาะกับ cloud balloon หรือควรใช้ skeleton/medial axis แทน
3. ควรให้ระบบเสนอ 3 candidate พร้อม uncertainty ให้ผู้แปลเลือกหรือไม่
4. mask จาก SAM, threshold และ detector ต่างกันอย่างไรเมื่อวัดด้วย ground truth เดียวกัน

## แหล่งอ้างอิงหลัก

- OpenCV `distanceTransform`: https://docs.opencv.org/4.5.3/d7/d1b/group__imgproc__misc.html
- U-Net: https://arxiv.org/abs/1505.04597
- SAM 2: https://arxiv.org/abs/2408.00714
- Manga109: https://manga109.github.io/manga109-project-website/en/

