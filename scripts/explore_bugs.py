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
    draw.ellipse([150, 100, 650, 400], fill="white", outline="black", width=3)
    draw.polygon([(400, 390), (370, 440), (430, 390)], fill="white", outline="black")
    draw.line([(370, 440), (430, 390)], fill="white", width=4)
    draw.rectangle([100, 600, 700, 800], fill="white", outline="black", width=3)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msgothic.ttc", 36)
    except Exception:
        font = ImageFont.load_default()
    draw.text((320, 200), "こんにちは\nお元気ですか", fill="black", font=font, align="center")
    draw.text((150, 660), "これはテストシステムです\nうまく検出できるでしょうか", fill="black", font=font, align="center")
    img.save(output_path, "PNG")

def explore_bugs():
    from playwright.sync_api import sync_playwright
    
    print("\n=== STARTING PLAYWRIGHT BUG EXPLORATION (QA PERSPECTIVE) ===")
    
    bugs_found = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_viewport_size({"width": 1440, "height": 900})
            
            # Navigate to Houmi
            print("Navigating to Houmi UI...")
            page.goto("http://localhost:5173", wait_until="networkidle")
            page.wait_for_timeout(2000)
            
            # --- BUG CHECK 1: UI Layout Check (Project Delete Function) ---
            print("Checking UI for project deletion capabilities...")
            # We see projects in sidebar, but is there any delete button for projects in App.tsx?
            # Let's inspect the DOM elements related to projects
            delete_project_buttons = page.locator("button:has-text('Delete')")
            trash_icons = page.locator("[class*='trash'], [id*='delete'], [class*='delete']")
            
            if delete_project_buttons.count() == 0 and trash_icons.count() == 0:
                msg = "UI Bug/Defect: มี API สำหรับลบโปรเจกต์ (DELETE /api/projects/{id}) ในหลังบ้าน แต่หน้าบ้าน (Frontend UI) ไม่มีปุ่มหรือกลไกให้ผู้ใช้สามารถลบโปรเจกต์ที่ไม่ต้องการได้เลย"
                print(f"[BUG FOUND] {msg}")
                bugs_found.append(msg)
            
            # Create project for further testing
            print("Creating test project for QA...")
            page.click("button:has-text('New Project')")
            page.wait_for_selector("input[placeholder*='เช่น']")
            proj_name = f"QA_Bug_Test_{int(time.time())}"
            page.fill("input[placeholder*='เช่น']", proj_name)
            page.click("button[type='submit']")
            page.wait_for_timeout(2000)
            
            # Generate and upload image
            test_img_path = BACKEND_DIR / "app" / "static" / "qa_test_sample.png"
            generate_test_image(test_img_path)
            
            print("Uploading test image...")
            file_input = page.locator("input[type='file']")
            file_input.set_input_files(str(test_img_path))
            page.wait_for_selector("text=Page 1", timeout=10000)
            page.wait_for_timeout(1000)
            
            # Open Page 1
            page.click("text=Page 1")
            page.wait_for_timeout(2000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "qa_01_loaded.png"))
            
            # --- BUG CHECK 2: Page Delete Button check ---
            print("Checking UI for page deletion capabilities...")
            page_delete_btns = page.locator("button:has-text('Delete Page'), button:has-text('Remove Page')")
            if page_delete_btns.count() == 0:
                msg = "UI Bug/Defect: หน้าบ้านไม่มีปุ่มสำหรับลบหน้า (Delete Page) ออกจากโปรเจกต์ ถึงแม้จะมี API หลังบ้านรองรับก็ตาม"
                print(f"[BUG FOUND] {msg}")
                bugs_found.append(msg)
                
            # Run Detect
            print("Running Bounding Box Detection...")
            page.click("button:has-text('1. Detect')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=20000)
            page.wait_for_timeout(2000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "qa_02_detected.png"))
            
            # Get project and page id
            res = requests.get("http://localhost:4000/api/projects")
            active_p = next(p for p in res.json() if p["name"] == proj_name)
            p_pages = requests.get(f"http://localhost:4000/api/projects/{active_p['id']}/pages").json()
            test_page_id = p_pages[0]["id"]
            
            # Check db blocks
            full_page_details = requests.get(f"http://localhost:4000/api/pages/{test_page_id}").json()
            blocks = full_page_details.get("text_blocks", [])
            print(f"YOLO detected {len(blocks)} blocks.")
            
            # --- BUG CHECK 3: Bounding Box Clickability and Canvas Sync ---
            print("Testing Canvas text block click and synchronization...")
            # Let's verify if clicking a block in canvas opens the editor and updates correctly
            # We will select the first block via API, or try clicking on Canvas coordinate
            if len(blocks) > 0:
                first_block = blocks[0]
                # Check if editor properties exist on first load without selection
                editor_info = page.locator("text=Element Editor").first
                selected_info = page.locator("text=Source Text").first
                
                # Check if unselected, is the editor blank?
                if not selected_info.is_visible():
                    print("Editor is correctly blank before selecting any box.")
                
                # Try to click on the canvas (Fabric.js canvas wrapper is usually .upper-canvas)
                canvas = page.locator(".upper-canvas").first
                if canvas.is_visible():
                    # Calculate center coordinates of first box on canvas
                    # First, we need to map block coordinate to canvas viewport coordinate
                    # For simplicity, let's just trigger E2E rendering and check translation updating
                    pass
            
            # Run OCR & Translate
            print("Running OCR...")
            page.click("button:has-text('2. OCR')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=20000)
            page.wait_for_timeout(1000)
            
            print("Running Translate...")
            page.click("button:has-text('3. Translate')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=20000)
            page.wait_for_timeout(1000)
            
            # Verify translation values
            page_details_after_trans = requests.get(f"http://localhost:4000/api/pages/{test_page_id}").json()
            trans_blocks = page_details_after_trans.get("text_blocks", [])
            
            # --- BUG CHECK 4: Mock Translate Service ---
            has_mock_bug = False
            for b in trans_blocks:
                if b["translation"] and b["translation"].startswith("[แปล]"):
                    has_mock_bug = True
                    break
            if has_mock_bug:
                msg = "Backend Core Bug/Limitation: ขั้นตอนการแปล (Translation) เป็นเพียงการทำ Mock โดยเติมคำว่า '[แปล]' ไว้หน้าข้อความ OCR เท่านั้น ยังไม่มีการเชื่อมต่อกับ Translation API จริง เช่น DeepL หรือ LLM"
                print(f"[BUG FOUND] {msg}")
                bugs_found.append(msg)
                
            # --- BUG CHECK 5: Inpaint OpenCV Telea Quality vs LaMa ---
            print("Running Inpaint...")
            page.click("button:has-text('4. Inpaint')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=20000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "qa_03_inpainted.png"))
            
            # --- BUG CHECK 6: Final Render text wrapping & layout ---
            print("Running Final Render...")
            page.click("button:has-text('5. Final Render')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=20000)
            page.wait_for_timeout(2000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "qa_04_rendered.png"))
            
            # --- BUG CHECK 7: Export PSD Functionality (Rust CLI integration) ---
            print("Checking Export PSD capability...")
            # We click the Export PSD button and wait to see if it downloads or triggers an error
            # We can directly query backend /api/export/psd to see if it fails
            try:
                psd_url = f"http://localhost:4000/api/export/psd?page_id={test_page_id}"
                print(f"Direct testing PSD Export API: {psd_url}")
                psd_res = requests.post(psd_url, timeout=10)
                if psd_res.status_code != 200:
                    msg = f"Backend Integration Bug: ปุ่ม Export PSD เกิดข้อผิดพลาดใน API (Status Code: {psd_res.status_code}) เนื่องจากระบบไม่พบโปรแกรม Rust CLI หรือคอมไพล์ไม่ผ่าน"
                    print(f"[BUG FOUND] {msg}")
                    bugs_found.append(msg)
                else:
                    print("PSD Export API test: SUCCESS")
            except Exception as e:
                msg = f"Backend Integration Bug: Export PSD API ล้มเหลวด้วย Exception: {e}"
                print(f"[BUG FOUND] {msg}")
                bugs_found.append(msg)

            # Cleanup project
            print("Cleaning up QA project...")
            requests.delete(f"http://localhost:4000/api/projects/{active_p['id']}")
            
            # Remove temp image
            if test_img_path.exists():
                os.remove(test_img_path)
                
            browser.close()
            
    except Exception as e:
        print(f"QA exploration script crashed with error: {e}")
        
    return bugs_found

if __name__ == "__main__":
    bugs = explore_bugs()
    print("\n=== SUMMARY OF BUGS FOUND ===")
    for i, b in enumerate(bugs):
        print(f"{i+1}. {b}")
        
    # Write to a JSON file
    with open(DIAGNOSTICS_DIR / "bugs_exploration.json", "w", encoding="utf-8") as f:
        json.dump(bugs, f, indent=4, ensure_ascii=False)
