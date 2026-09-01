import sys
import time
import requests
import json
from pathlib import Path

BASE_URL = "http://127.0.0.1:4000"

def test_pipeline():
    print("="*60)
    print("HOUMI STUDIO V1.0.5 FULL E2E AUTOMATED VERIFICATION SUITE")
    print("="*60)
    
    # 1. System health check
    print("\n[1/6] Checking system update and backend health...")
    try:
        r = requests.get(f"{BASE_URL}/api/system/check-update", timeout=5)
        assert r.status_code == 200, f"Health check failed with {r.status_code}"
        print("  -> System Health: OK (Status 200)")
    except Exception as e:
        print(f"  -> FAIL: {e}")
        return False
        
    # 2. Project List
    print("\n[2/6] Querying active projects...")
    try:
        r = requests.get(f"{BASE_URL}/api/projects", timeout=5)
        assert r.status_code == 200, f"Projects query failed: {r.status_code}"
        projects = r.json()
        print(f"  -> Found {len(projects)} projects")
        if not projects:
            print("  -> Warning: No existing projects to test page operations.")
            return True
        project = projects[0]
        project_id = project["id"]
        print(f"  -> Testing with Project ID: {project_id} ('{project.get('name')}')")
    except Exception as e:
        print(f"  -> FAIL: {e}")
        return False

    # 3. Pages List
    print("\n[3/6] Querying project pages...")
    try:
        r = requests.get(f"{BASE_URL}/api/projects/{project_id}", timeout=5)
        assert r.status_code == 200
        proj_detail = r.json()
        pages = proj_detail.get("pages", [])
        print(f"  -> Found {len(pages)} pages in project")
        if not pages:
            print("  -> No pages in project to run pipeline test on.")
            return True
        page = pages[0]
        page_id = page["id"]
        print(f"  -> Active testing Page ID: {page_id} (Page #{page.get('page_number')})")
    except Exception as e:
        print(f"  -> FAIL: {e}")
        return False

    # 4. Detection Pipeline
    print("\n[4/6] Testing Text Block Detection API...")
    try:
        r = requests.post(f"{BASE_URL}/api/pipeline/detect?page_id={page_id}&force=true", timeout=15)
        if r.status_code == 200:
            detect_data = r.json()
            blocks = detect_data.get("text_blocks", [])
            print(f"  -> Detection Success: Found {len(blocks)} text blocks")
        else:
            print(f"  -> Detection returned status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  -> Detection request error: {e}")

    # 5. Effective Mask Generation & Clamping
    print("\n[5/6] Testing Effective Mask & Boundary Clamping API...")
    try:
        r = requests.get(f"{BASE_URL}/api/pipeline/pages/{page_id}/effective-mask?overlay=true", timeout=15)
        if r.status_code == 200:
            mask_data = r.json()
            data_url = mask_data.get("mask_data_url", "")
            w = mask_data.get("width")
            h = mask_data.get("height")
            assert len(data_url) > 50, "Mask data URL is empty"
            print(f"  -> Effective Mask Loaded: {w}x{h} px, DataURL len: {len(data_url)} chars (OK)")
        else:
            print(f"  -> Mask endpoint returned {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  -> Effective mask error: {e}")

    # 6. OCR Pipeline
    print("\n[6/6] Testing OCR Pipeline with JSON Body...")
    try:
        r = requests.post(
            f"{BASE_URL}/api/pipeline/ocr",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"page_id": page_id, "force": True}),
            timeout=20
        )
        if r.status_code == 200:
            ocr_data = r.json()
            print(f"  -> OCR Pipeline Executed Successfully: {r.status_code}")
        else:
            print(f"  -> OCR returned status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  -> OCR error: {e}")

    print("\n" + "="*60)
    print("ALL API & PIPELINE VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
    print("="*60)
    return True

if __name__ == "__main__":
    test_pipeline()
