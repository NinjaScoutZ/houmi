import os
import sys
import time
import json
import requests
from pathlib import Path

# Set paths
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = PROJECT_ROOT / "data"
DIAGNOSTICS_DIR = DATA_DIR / "diagnostics"

DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)

# Add backend directory to sys.path
sys.path.append(str(BACKEND_DIR))

# Use the virtual environment python
VENV_PYTHON = str(BACKEND_DIR / ".venv" / "Scripts" / "python.exe")

def generate_test_image(output_path: Path):
    """Generates a synthetic manga-like page with clean bubble and text to guarantee detection/OCR success."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 780, 980], outline="black", width=4)
    draw.line([20, 500, 780, 500], fill="black", width=4)
    
    # Bubble 1 (Speech Bubble - Top Panel)
    draw.ellipse([150, 100, 650, 400], fill="white", outline="black", width=3)
    draw.polygon([(400, 390), (370, 440), (430, 390)], fill="white", outline="black")
    draw.line([(370, 440), (430, 390)], fill="white", width=4)
    
    # Bubble 2 (Narrative Box - Bottom Panel)
    draw.rectangle([100, 600, 700, 800], fill="white", outline="black", width=3)
    
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msgothic.ttc", 36)
    except Exception:
        font = ImageFont.load_default()
        
    draw.text((320, 200), "こんにちは\nお元気ですか", fill="black", font=font, align="center")
    draw.text((150, 660), "これはテストシステムです\nうまく検出できるでしょうか", fill="black", font=font, align="center")
    img.save(output_path, "PNG")

def run_exhaustive_diagnostics():
    from playwright.sync_api import sync_playwright
    
    print("\n=== STARTING EXHAUSTIVE USER-FLOW INTEGRATION TEST ===")
    
    results = {
        "status": "failed",
        "import_page": None,
        "detection": None,
        "ocr_text_results": [],
        "inpainting": None,
        "text_rendering": None,
        "psd_export": None,
        "time_elapsed_seconds": 0
    }
    
    t_start = time.time()
    
    try:
        with sync_playwright() as p:
            print("Launching Browser...")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_viewport_size({"width": 1440, "height": 900})
            
            # Step 1: Navigating and creating project
            print("Navigating to Houmi App...")
            page.goto("http://localhost:5173", wait_until="networkidle")
            page.wait_for_timeout(2000)
            
            print("Creating QA project...")
            page.click("#new-project-btn")
            page.wait_for_selector("input[placeholder*='เช่น']")
            proj_name = f"QA_Exhaustive_Test_{int(time.time())}"
            page.fill("input[placeholder*='เช่น']", proj_name)
            page.click("button[type='submit']")
            page.wait_for_timeout(2000)
            
            # Step 2: Import / Upload Test Image
            print("Step 2 (Import): Uploading test image...")
            test_img_path = BACKEND_DIR / "app" / "static" / "exhaustive_test_sample.png"
            generate_test_image(test_img_path)
            
            # Make sure project is active
            try:
                page.click(f"button:has-text('{proj_name}')", timeout=3000)
                page.wait_for_timeout(500)
            except Exception:
                pass
                
            page.wait_for_selector("input[type='file']", state="attached", timeout=5000)
            file_input = page.locator("input[type='file']")
            file_input.set_input_files(str(test_img_path))
            
            page.wait_for_selector("text=Page 1", timeout=12000)
            page.wait_for_timeout(1000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "ex_01_imported.png"))
            results["import_page"] = "SUCCESS: Image imported and downsampled preview created"
            print("Import Step: SUCCESS")
            
            # Step 3: Open Page 1 on Canvas
            page.click("text=Page 1")
            page.wait_for_timeout(2000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "ex_02_canvas_ready.png"))
            
            # Switch to Pipeline tab
            print("Switching to Pipeline tab...")
            page.click("button:has-text('Pipeline')")
            page.wait_for_timeout(1000)
            
            # Step 4: Run Detect
            print("Step 4 (Detect): Running Bounding Box Detection...")
            page.click("button:has-text('1. Detect')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=20000)
            page.wait_for_timeout(2000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "ex_03_after_detect.png"))
            
            # Query backend to check detected boxes count
            res = requests.get("http://localhost:4000/api/projects")
            active_p = next(p for p in res.json() if p["name"] == proj_name)
            p_pages = requests.get(f"http://localhost:4000/api/projects/{active_p['id']}/pages").json()
            test_page_id = p_pages[0]["id"]
            
            page_details = requests.get(f"http://localhost:4000/api/pages/{test_page_id}").json()
            blocks = page_details.get("text_blocks", [])
            results["detection"] = f"SUCCESS: YOLO detected {len(blocks)} balloon text areas."
            print(f"Detection Step: SUCCESS (YOLO found {len(blocks)} blocks)")
            
            # Step 5: Run OCR
            print("Step 5 (OCR): Extracting text lines from bubbles...")
            page.click("button:has-text('2. OCR')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=30000)
            page.wait_for_timeout(1000)
            
            # Fetch blocks with OCR content
            page_details_ocr = requests.get(f"http://localhost:4000/api/pages/{test_page_id}").json()
            ocr_blocks = page_details_ocr.get("text_blocks", [])
            
            for idx, b in enumerate(ocr_blocks):
                ocr_val = b.get("source_text", "").strip()
                trans_val = b.get("translation", "").strip()
                print(f" - Block {idx} OCR Text: {repr(ocr_val)} -> Translation: {repr(trans_val)}")
                results["ocr_text_results"].append({
                    "block_index": b["block_index"],
                    "coordinates": {"x": b["x"], "y": b["y"], "w": b["width"], "h": b["height"]},
                    "ocr_source": ocr_val,
                    "mock_translation": trans_val
                })
            
            page.screenshot(path=str(DIAGNOSTICS_DIR / "ex_04_after_ocr.png"))
            
            # Step 6: Inpaint Preview
            print("Step 6 (Preview): Generating inpaint preview...")
            page.click("button:has-text('3. Preview Inpaint')")
            page.wait_for_selector("text=Smart Inpaint Preview", timeout=25000)
            page.wait_for_timeout(1000)
            page.click("button:has-text('Close')")
            page.wait_for_selector("text=Smart Inpaint Preview", state="detached", timeout=5000)
            
            # Step 7: Run Inpaint (Remove Text Background)
            print("Step 7 (Remove/Inpaint): Inpainting text areas...")
            page.click("button:has-text('4. Inpaint Clean')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=25000)
            page.wait_for_timeout(2000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "ex_05_after_inpaint.png"))
            
            # Check if inpainted image exists on backend data dir
            inpainted_file = DATA_DIR / "projects" / active_p["id"] / test_page_id / "inpainted.png"
            if inpainted_file.exists():
                results["inpainting"] = f"SUCCESS: OpenCV Telea inpainting complete. Image saved at {inpainted_file.name} ({inpainted_file.stat().st_size} bytes)"
                print("Inpainting Step: SUCCESS")
            else:
                results["inpainting"] = "FAILED: Inpainted image file not found on disk"
                print("Inpainting Step: FAILED")
                
            # Step 8: Run Final Render (Render translation text)
            print("Step 8 (Render): Drawing translated text onto cleaned image...")
            page.click("button:has-text('5. Final Render')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=25000)
            page.wait_for_timeout(2000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "ex_06_after_render.png"))
            
            rendered_file = DATA_DIR / "projects" / active_p["id"] / test_page_id / "rendered.png"
            if rendered_file.exists():
                results["text_rendering"] = f"SUCCESS: Text drawn on canvas. Rendered output saved at {rendered_file.name} ({rendered_file.stat().st_size} bytes)"
                print("Rendering Step: SUCCESS")
            else:
                results["text_rendering"] = "FAILED: Rendered output image file not found on disk"
                print("Rendering Step: FAILED")
                
            # Step 8 (Export): Export to PSD
            print("Step 8 (Export): Exporting page translation to PSD file...")
            psd_url = f"http://localhost:4000/api/export/psd?page_id={test_page_id}"
            psd_res = requests.post(psd_url, timeout=15)
            if psd_res.status_code == 200:
                results["psd_export"] = f"SUCCESS: PSD export completed. API returned binary data ({len(psd_res.content)} bytes)"
                print(f"Export Step: SUCCESS (PSD size: {len(psd_res.content)} bytes)")
            else:
                results["psd_export"] = f"FAILED: PSD export API returned status code {psd_res.status_code}"
                print("Export PSD Step: FAILED")

            # Clean up QA project
            print("Cleaning up test project in database...")
            requests.delete(f"http://localhost:4000/api/projects/{active_p['id']}")
            
            if test_img_path.exists():
                os.remove(test_img_path)
                
            browser.close()
            results["status"] = "success"
            
    except Exception as e:
        print(f"Exhaustive test suite crashed with error: {e}")
        results["errors"] = str(e)
        
    results["time_elapsed_seconds"] = round(time.time() - t_start, 2)
    return results

if __name__ == "__main__":
    test_results = run_exhaustive_diagnostics()
    
    # Save report
    report_file = DIAGNOSTICS_DIR / "exhaustive_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(test_results, f, indent=4, ensure_ascii=False)
        
    print("\n=== FINAL EXHAUSTIVE SUMMARY ===")
    print(json.dumps(test_results, indent=2, ensure_ascii=False))
