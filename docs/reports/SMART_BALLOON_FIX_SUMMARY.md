# 🎯 Smart Balloon V15 Classification Fix - Summary

## Problem Fixed
บอลลูนที่มีขอบหยัก/ขนฟูชัดเจน (SPIKY_FUZZY) ถูกจำแนกผิดเป็น SMOOTH_OVAL

## Root Cause
ระบบทำ classification **หลังจาก morphological CLOSE operation** (kernel 25×25 px) ซึ่งทำให้ขนฟู/spikes ถูก smooth ออกไปก่อนแล้ว

## Solution
1. **เก็บ raw contour ก่อน morphology** → ขนฟู/spikes ไม่ถูกทำลาย
2. **ใช้ raw contour สำหรับ classification** → ได้ roughness ที่แม่นยำ
3. **ลด Gaussian sigma** จาก 12.0 → 5.0 → เพิ่มความไว
4. **ปรับ thresholds** → สมดุลระหว่าง sensitivity/specificity

## Changes
- `backend/app/services/smart_balloon.py`:
  - Line 471-480: Extract raw contour before morphology
  - Line 523-528: Use raw contour for classification
  - Line 35: Reduce sigma to 5.0
  - Line 246-256: Adjust SPIKY_FUZZY thresholds

## Test Results
✅ **21/21 tests passed** (including detector + smart balloon tests)
- All archetype classifications working correctly
- No regressions in detector pipeline
- Smooth balloons NOT misclassified as spiky

## Next Steps
1. ✅ Code changes completed
2. ✅ Unit tests passing
3. ⏳ Manual testing with real manga images (recommended)
4. ⏳ Ready for commit & deployment
