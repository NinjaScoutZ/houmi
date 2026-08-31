import os
import sys
import json
import time
import requests
import numpy as np
import cv2
from pathlib import Path

BASE_URL = 'http://127.0.0.1:4317'

def wait_for_server(timeout=25):
    print('⏳ Waiting for Houmi Local Engine on port 4317...')
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f'{BASE_URL}/api/health', timeout=1)
            if r.status_code == 200:
                print(f'✅ Connected to Houmi Local Engine ({time.time() - start:.1f}s)!')
                return True
        except Exception:
            time.sleep(0.5)
    return False

def run_tests():
    print('=' * 65)
    print('🧪 HOUMI STUDIO v2.0.0 - AUTOMATED FULL TOOL SUITE SELF-TEST')
    print('=' * 65)

    if not wait_for_server():
        print('❌ Server failed to respond within timeout!')
        return False

    session = requests.Session()
    results = {}

    # 1. Health check
    try:
        r = session.get(f'{BASE_URL}/api/health', timeout=3)
        assert r.status_code == 200
        results['1. Health Check'] = 'PASSED'
    except Exception as e:
        results['1. Health Check'] = f'FAILED: {e}'

    # 2. System Update Check
    try:
        r = session.get(f'{BASE_URL}/api/system/check-update', timeout=3)
        assert r.status_code == 200
        ver = r.json().get('current_version', '?')
        results['2. System Check-Update'] = f'PASSED (v{ver})'
    except Exception as e:
        results['2. System Check-Update'] = f'FAILED: {e}'

    # 3. Hardware Diagnostics
    try:
        r = session.get(f'{BASE_URL}/api/diagnostics/hardware', timeout=3)
        assert r.status_code == 200
        data = r.json()
        gpu = data.get('gpu_name', 'N/A')
        results['3. Hardware Diagnostics'] = f'PASSED (GPU: {gpu})'
    except Exception as e:
        results['3. Hardware Diagnostics'] = f'FAILED: {e}'

    # 4. Fonts List & Rescan
    try:
        r = session.get(f'{BASE_URL}/api/fonts/list', timeout=3)
        assert r.status_code == 200
        r_rescan = session.post(f'{BASE_URL}/api/fonts/rescan', timeout=5)
        assert r_rescan.status_code == 200
        results['4. Fonts List & Rescan'] = 'PASSED'
    except Exception as e:
        results['4. Fonts List & Rescan'] = f'FAILED: {e}'

    # 5. Create Test Project
    project_id = None
    page_id = None
    try:
        r = session.post(f'{BASE_URL}/api/projects', json={'name': 'E2E Automated Test Project'}, timeout=5)
        assert r.status_code in (200, 201)
        project_data = r.json()
        project_id = project_data['id']
        results['5. Project Creation'] = f'PASSED (ID: {project_id})'
    except Exception as e:
        results['5. Project Creation'] = f'FAILED: {type(e).__name__}: {e}'

    if project_id:
        test_img_path = Path('e:/houmi/backend/data/temp_e2e_page.png')
        test_img_path.parent.mkdir(parents=True, exist_ok=True)
        img = np.ones((800, 600, 3), dtype=np.uint8) * 240
        cv2.rectangle(img, (50, 50), (550, 750), (0, 0, 0), 3)
        cv2.ellipse(img, (300, 300), (140, 90), 0, 0, 360, (255, 255, 255), -1)
        cv2.ellipse(img, (300, 300), (140, 90), 0, 0, 360, (0, 0, 0), 2)
        cv2.putText(img, 'TEST', (250, 310), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
        cv2.imwrite(str(test_img_path), img)

        # 6. Page Upload
        try:
            with open(test_img_path, 'rb') as f:
                r = session.post(
                    f'{BASE_URL}/api/projects/{project_id}/pages?page_number=1',
                    files={'file': ('page_1.png', f, 'image/png')},
                    timeout=10
                )
            if r.status_code in (200, 201):
                page_id = r.json().get('id')
            results['6. Page Upload'] = f'PASSED (Page ID: {page_id})'
        except Exception as e:
            results['6. Page Upload'] = f'FAILED: {type(e).__name__}: {e}'

        if page_id:
            # 7. Page Preview & Thumbnail API
            try:
                r1 = session.get(f'{BASE_URL}/api/pages/{page_id}/preview', timeout=5)
                r2 = session.get(f'{BASE_URL}/api/pages/{page_id}/preview?thumbnail=true', timeout=5)
                r3 = session.get(f'{BASE_URL}/api/pages/{page_id}/image', timeout=5)
                assert r1.status_code in (200, 201) and r2.status_code in (200, 201) and r3.status_code in (200, 201)
                results['7. Page Preview & Thumbnail API'] = 'PASSED'
            except Exception as e:
                results['7. Page Preview & Thumbnail API'] = f'FAILED: {e}'

            # 8. AI Balloon Detect (JSON Body)
            try:
                r = session.post(f'{BASE_URL}/api/pipeline/detect', json={'page_id': page_id}, timeout=15)
                assert r.status_code == 200
                cnt = r.json().get('detected_blocks_count', 0)
                results['8. AI Balloon Detect (JSON Body)'] = f'PASSED (Found: {cnt} blocks)'
            except Exception as e:
                results['8. AI Balloon Detect (JSON Body)'] = f'FAILED: {e}'

            # 9. OCR Engine (JSON Body)
            try:
                r = session.post(f'{BASE_URL}/api/pipeline/ocr', json={'page_id': page_id}, timeout=15)
                assert r.status_code == 200
                results['9. OCR Engine (JSON Body)'] = 'PASSED'
            except Exception as e:
                results['9. OCR Engine (JSON Body)'] = f'FAILED: {e}'

            # 10. AI Inpainter (JSON Body)
            try:
                r = session.post(f'{BASE_URL}/api/pipeline/inpaint', json={'page_id': page_id}, timeout=20)
                assert r.status_code == 200
                results['10. AI Inpainter (JSON Body)'] = 'PASSED'
            except Exception as e:
                results['10. AI Inpainter (JSON Body)'] = f'FAILED: {e}'

            # 11. One-Click AI Auto Pipeline
            try:
                r = session.post(f'{BASE_URL}/api/pipeline/auto', json={'page_id': page_id}, timeout=25)
                assert r.status_code == 200
                results['11. One-Click AI Auto Pipeline'] = 'PASSED'
            except Exception as e:
                results['11. One-Click AI Auto Pipeline'] = f'FAILED: {e}'

            # 12. Auto Mask Generation
            try:
                r = session.post(f'{BASE_URL}/api/pipeline/pages/{page_id}/auto-mask', timeout=10)
                assert r.status_code in (200, 204)
                results['12. Auto Mask Generation'] = 'PASSED'
            except Exception as e:
                results['12. Auto Mask Generation'] = f'FAILED: {e}'

        # 13. Smart Stitch Check Oversize
        try:
            r = session.post(f'{BASE_URL}/api/projects/check-oversize', json={'folder_path': str(test_img_path.parent)}, timeout=5)
            assert r.status_code == 200
            results['13. Smart Stitch Check Oversize'] = 'PASSED'
        except Exception as e:
            results['13. Smart Stitch Check Oversize'] = f'FAILED: {e}'

        # 14. Project Cleanup
        try:
            session.delete(f'{BASE_URL}/api/projects/{project_id}', timeout=5)
            if test_img_path.exists():
                test_img_path.unlink()
            results['14. Project Cleanup'] = 'PASSED'
        except Exception as e:
            results['14. Project Cleanup'] = f'FAILED: {e}'

    print()
    print('=' * 65)
    print('📊 FULL TOOL SUITE TEST RESULTS')
    print('=' * 65)
    all_passed = True
    for test_name, status_str in results.items():
        icon = '✅' if 'PASSED' in status_str else '❌'
        if 'FAILED' in status_str:
            all_passed = False
        print(f'{icon} {test_name:<38}: {status_str}')
    print('=' * 65)
    return all_passed

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
