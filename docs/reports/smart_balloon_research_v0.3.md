# Smart Balloon Auto-Resize — แผนวิจัยและพัฒนา v0.3

เอกสารนี้ต่อยอดจากผล v0.2 โดยเปลี่ยนจากการดูภาพตัวอย่างเป็นการประเมินที่ทำซ้ำได้ และเตรียมพร้อมสำหรับการใช้งานจริงใน `detector.py`.

## 1. คำถามวิจัย

1. การเลือก contour ที่ครอบศูนย์กลางข้อความช่วยลดการขยายเกินบอลลูนได้มากกว่าวิธีขยายตามสัดส่วนคงที่หรือไม่
2. การใช้คะแนนหลายคุณลักษณะ (การครอบคลุมข้อความ, ความใกล้ศูนย์กลาง, ความเรียบของขอบ, และขนาด) ช่วยลด ellipse fallback ในภาพยาว/ภาพ stitched ได้หรือไม่
3. ค่าขอบเขตแบบแยกแกน (width/height) ให้ความสมดุลระหว่างการไม่ตัดข้อความกับการไม่ล้นบอลลูนดีกว่าค่าเดียวหรือไม่

## 2. สมมติฐานและตัวชี้วัด

**H1:** v0.3 มี median expansion ratio ไม่เกิน 1.75x และกรณีเกิน 2.5x น้อยกว่า 2% บนชุดทดสอบที่ไม่ซ้ำกับชุดปรับพารามิเตอร์

**H2:** อัตรา fallback บนภาพ stitched ลดจาก 75% เหลือน้อยกว่า 30% ด้วยการประมวลผลแบบ tile และ morphology ที่ปรับตามขนาด bbox

**H3:** text-coverage (ข้อความทั้งหมดอยู่ใน region) ไม่น้อยกว่า 99% และ balloon IoU เฉลี่ยไม่น้อยกว่า 0.85 บนชุดที่มี ground truth

ตัวชี้วัดที่ต้องบันทึกต่อ block: `expansion_w`, `expansion_h`, `text_coverage`, `balloon_iou`, `fallback`, `method`, `runtime_ms` และ `clipped_to_image`.

## 3. ชุดข้อมูลและ ground truth

- แบ่งข้อมูลเป็น train/dev/test ตามเรื่องหรือ chapter เพื่อป้องกันภาพใกล้เคียงกันข้ามชุด (แนะนำ 60/20/20)
- อย่างน้อย 200 blocks: วงรี, วงกลม, หยัก, แหลม, sci-fi/dark, ภาพ stitched และ SFX
- ผู้ตรวจทำ mask หรือ polygon ของบอลลูน และ bbox ของข้อความจริง
- รายงานค่าเฉลี่ยพร้อม bootstrap 95% confidence interval และรายงานผลแยกตามประเภทบอลลูน ไม่รายงานเฉพาะค่าเฉลี่ยรวม

## 4. Algorithm v0.3 ที่เสนอ

```mermaid
flowchart TD
 A[YOLO text bbox] --> B[search region แบบ scale-adaptive]
 B --> C{ภาพใหญ่/stitched?}
 C -->|ใช่| D[tile overlap 20%]
 C -->|ไม่ใช่| E[bilateral + Canny]
 D --> E
 E --> F[dilate/close kernel ตาม min(w,h)]
 F --> G[contour candidates + ellipse/convex hull]
 G --> H[คะแนน: coverage 0.40, center 0.25, edge 0.20, size 0.15]
 H --> I{คะแนนผ่าน threshold?}
 I -->|ใช่| J[เลือก candidate ที่เล็กสุดในกลุ่มคะแนนใกล้กัน]
 I -->|ไม่ใช่| K[robust ellipse fallback + uncertainty flag]
 J --> L[แยก cap width/height, recenter, clamp]
 K --> L
```

รายละเอียดสำคัญ:

- ใช้ `min_axis_expansion_w=1.15`, `min_axis_expansion_h=1.30`, `max_axis_expansion_w=1.45`, `max_axis_expansion_h=1.70` เป็นค่าเริ่มต้น แล้ว tune เฉพาะบน dev set
- สำหรับภาพ stitched ให้แบ่ง tile โดยมี overlap และรวม contour กลับเป็นพิกัดภาพเดิมก่อน scoring
- เก็บ candidate อันดับ 1–3 เพื่อให้ debug ได้ และตั้ง `confidence` ต่ำเมื่อใช้ fallback
- SFX/บล็อกที่ไม่มีข้อความให้ข้ามตั้งแต่ post-processing
- หากไม่มี candidate ที่ผ่าน threshold ให้คืน original text bbox อย่างปลอดภัย แทนการขยายแบบเดาสุ่ม

## 5. การทดลองเปรียบเทียบ

เปรียบเทียบอย่างน้อย 4 แบบ: (A) v0.1 fixed expansion, (B) v0.2 ปัจจุบัน, (C) v0.3 ไม่มี tile, (D) v0.3 เต็มรูปแบบ มี paired bootstrap และทดสอบ Wilcoxon บน expansion และ IoU เพื่อตรวจว่าความแตกต่างมีนัยสำคัญหรือไม่

เกณฑ์ยอมรับ release candidate: H1–H3 ผ่านทั้งหมด, fallback <30%, p<0.05 เมื่อเทียบกับ v0.2 ใน metric หลัก, และ p95 runtime เพิ่มไม่เกิน 50 ms ต่อ blockบน CPU

## 6. แผน implementation ที่ย้อนกลับได้

1. เพิ่ม pure function `smart_resize_balloon(text_bbox, image, config) -> BalloonRegion` ใน `backend/app/services/detector.py`
2. แยก dataclass/config: `enabled`, search pad, kernel scale, min/max axis, fallback scale, score threshold และ tile settings
3. เก็บ `original_bbox`, `method`, `confidence`, `fallback_reason` ในผลลัพธ์ทุกครั้ง
4. เพิ่ม `enable_smart_balloon` ใน Project Settings และ toggle ใน Frontend Settings (ค่าเริ่มต้น **ปิด** จนกว่าผล test set จะผ่าน)
5. เพิ่ม unit tests รูปทรงสังเคราะห์, regression tests ชุด 66 blocks เดิม และ golden test สำหรับภาพ stitched
6. เพิ่ม structured logging/telemetry แบบไม่เก็บภาพ เพื่อวัด fallback, clipping และ runtime ในการใช้งานจริง

## 7. ความเสี่ยงและการควบคุม

- ขอบบอลลูนสีเดียวกับพื้นหลัง: ลด threshold ไม่ได้เสมอไป ให้ fallback เป็น original bbox และแจ้ง confidence ต่ำ
- บอลลูนซ้อนกัน: ใช้ center containment และให้ผู้ใช้แก้กรอบได้ด้วย manual override
- ภาพความละเอียดต่างกัน: ใช้ kernel และ padding ที่คำนวณจากขนาด bbox ไม่ใช้พิกเซลคงที่
- ความเข้ากันได้: feature flag, schema version และ rollback ไป v0.2 ได้ทันที

## 8. ผลลัพธ์ที่คาดหวัง

ได้โมดูลที่วัดผลได้และอธิบายได้ ไม่ใช่เพียงภาพตัวอย่าง: ลดการขยายเกิน, รักษาข้อความครบ, ลด fallback ในภาพยาว และมีหลักฐานเพียงพอก่อนเปิดใช้เป็นค่าเริ่มต้น

