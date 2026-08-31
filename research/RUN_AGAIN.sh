#!/bin/bash
# วิธีรันงานวิจัย Smart Balloon v2 ซ้ำ

cd "$(dirname "$0")"

echo "=== Smart Balloon v2 Research ==="
echo "Project: E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350"
echo "Samples: #06, #09, #10, #14, #15, #18, #19, #26, #28"
echo ""

# ตรวจสอบว่าโฟลเดอร์โปรเจกต์มีจริง
PROJECT_DIR="/e/Chapter Download/Kuaikanmanhua/ลิขิตตัวร้าย/350"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "ERROR: Project directory not found at $PROJECT_DIR"
    exit 1
fi

echo "Running smart_balloon_v2.py..."
python smart_balloon_v2.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Done. Preview images saved to: smart_balloon_previews_v2/"
    echo "✓ Summary: SMART_BALLOON_V2_SUMMARY.txt"
    echo ""
    echo "To view results:"
    echo "  - Open smart_balloon_previews_v2/*.png (4-panel previews)"
    echo "  - Read REPORT_TH.md (full analysis in Thai)"
    echo "  - Read SMART_BALLOON_V2_FINDINGS.md (findings in English)"
else
    echo ""
    echo "✗ Script failed. Check error messages above."
    exit 1
fi
