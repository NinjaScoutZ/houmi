import os
import sys
import time
import subprocess
import json
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Set paths
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = PROJECT_ROOT / "data"
DIAGNOSTICS_DIR = DATA_DIR / "diagnostics"

DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)

# Add backend directory to sys.path so we can import app modules if needed
sys.path.append(str(BACKEND_DIR))

# Use the virtual environment python
VENV_PYTHON = str(BACKEND_DIR / ".venv" / "Scripts" / "python.exe")
VENV_PLAYWRIGHT = str(BACKEND_DIR / ".venv" / "Scripts" / "playwright.exe")

def generate_test_image(output_path: Path):
    """Generates a synthetic manga-like page with clean bubble and text to guarantee detection/OCR success."""
    print(f"Generating synthetic test image at: {output_path}")
    # 800x1000 white canvas
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    
    # Draw simple panels
    draw.rectangle([20, 20, 780, 980], outline="black", width=4)
    draw.line([20, 500, 780, 500], fill="black", width=4)
    
    # Bubble 1 (Speech Bubble - Top Panel)
    # Circle/oval shape
    draw.ellipse([150, 100, 650, 400], fill="white", outline="black", width=3)
    # Tail for bubble
    draw.polygon([(400, 390), (370, 440), (430, 390)], fill="white", outline="black")
    draw.line([(370, 440), (430, 390)], fill="white", width=4) # Clean overlapping boundary
    
    # Bubble 2 (Narrative Box - Bottom Panel)
    draw.rectangle([100, 600, 700, 800], fill="white", outline="black", width=3)
    
    # Try to write clean Japanese text for OCR testing
    try:
        # Load system font
        font = ImageFont.truetype("C:/Windows/Fonts/msgothic.ttc", 36)
    except Exception:
        # Fallback to default
        font = ImageFont.load_default()
        
    # Draw text in Bubble 1
    # Multiline text vertical-aligned center
    txt1 = "こんにちは\nお元気ですか"
    draw.text((320, 200), txt1, fill="black", font=font, align="center")
    
    # Draw text in Bubble 2
    txt2 = "これはテストシステムです\nうまく検出できるでしょうか"
    draw.text((150, 660), txt2, fill="black", font=font, align="center")
    
    img.save(output_path, "PNG")
    print("Synthetic test image generated successfully.")

def kill_port(port):
    """Kill any process running on the specified port (Windows specific)."""
    try:
        output = subprocess.check_output(f'netstat -aon | findstr LISTENING | findstr :{port}', shell=True).decode()
        for line in output.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 5:
                pid = parts[-1]
                print(f"Port {port} in use by PID {pid}. Killing process...")
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except subprocess.CalledProcessError:
        # Port is not in use
        pass

def wait_for_url(url, timeout=30):
    t0 = time.time()
    print(f"Waiting for URL: {url} (max timeout {timeout}s)...")
    while time.time() - t0 < timeout:
        try:
            # Increase connection read timeout to 10s because OCR status checks can block backend startup responses
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                return True
        except Exception as e:
            # Print minimal debug log for exceptions
            pass
        time.sleep(1.5)
    return False

def run_e2e_tests():
    from playwright.sync_api import sync_playwright
    
    print("\n=== STARTING PLAYWRIGHT E2E TEST (USER PERSPECTIVE) ===")
    
    report = {
        "status": "failed",
        "timestamp": time.time(),
        "steps": [],
        "errors": []
    }
    
    try:
        with sync_playwright() as p:
            # We run in headful/headless depending on choice, default to headless for automation
            print("Launching Chromium browser...")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Set a large viewport
            page.set_viewport_size({"width": 1280, "height": 800})
            
            # Step 1: Open main page
            print("Step 1: Navigating to Houmi UI...")
            page.goto("http://localhost:5173", wait_until="networkidle")
            page.wait_for_timeout(2000)
            
            # Verify UI title
            app_title = page.locator("text=Houmi Studio").first
            if app_title.is_visible():
                print("Connected to React UI: Success")
                report["steps"].append("1. Navigated to main page - SUCCESS")
            else:
                raise Exception("React UI header not found on page load")
            
            # Take loading screenshot
            page.screenshot(path=str(DIAGNOSTICS_DIR / "01_page_load.png"))
            
            # Step 2: Create a new project
            print("Step 2: Creating E2E Test Project...")
            # Click New Project button
            page.click("#new-project-btn")
            page.wait_for_selector("input[placeholder*='เช่น']")
            
            # Fill project name
            proj_name = f"E2E_Diagnostic_Project_{int(time.time())}"
            page.fill("input[placeholder*='เช่น']", proj_name)
            
            # Select target language to Thai (should default)
            page.select_option("#project-target-lang", "th")
            
            # Submit project creation
            page.click("button[type='submit']")
            page.wait_for_timeout(2000)
            
            # Screen after project creation
            page.screenshot(path=str(DIAGNOSTICS_DIR / "02_project_created.png"))
            print(f"Project '{proj_name}' created: Success")
            report["steps"].append("2. Created project - SUCCESS")
            
            # Step 3: Upload page image
            print("Step 3: Uploading test sample image...")
            # Explicitly click the newly created project in the sidebar list to guarantee it is active
            try:
                page.click(f"button:has-text('{proj_name}')", timeout=5000)
                print(f"Clicked project '{proj_name}' in sidebar to ensure it's selected.")
                page.wait_for_timeout(1000)
            except Exception:
                pass
                
            # Wait for file input to appear in DOM (even if hidden)
            page.wait_for_selector("input[type='file']", state="attached", timeout=10000)
            file_input = page.locator("input[type='file']")
            test_img_path = BACKEND_DIR / "app" / "static" / "test_sample.png"
            file_input.set_input_files(str(test_img_path))
            
            # Wait for upload to process (should create page list item)
            page.wait_for_selector("text=Page 1", timeout=15000)
            page.wait_for_timeout(2000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "03_image_uploaded.png"))
            print("Uploaded test sample: Success")
            report["steps"].append("3. Uploaded test image - SUCCESS")
            
            # Step 4: Open canvas page
            print("Step 4: Opening canvas workspace...")
            page.click("text=Page 1")
            page.wait_for_timeout(3000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "04_canvas_opened.png"))
            report["steps"].append("4. Opened Canvas Workspace - SUCCESS")
            
            # Switch to Pipeline tab
            print("Switching to Pipeline tab...")
            page.click("button:has-text('Pipeline')")
            page.wait_for_timeout(1000)
            
            # Step 5: Run Detect
            print("Step 5: Clicking Detect button in Auto Pipeline...")
            page.click("button:has-text('1. Detect')")
            # Wait for spinner / processing to end
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=20000)
            page.wait_for_timeout(3000) # Let canvas render boxes
            
            # Screenshot of Canvas boxes overlay
            page.screenshot(path=str(DIAGNOSTICS_DIR / "05_after_detect.png"))
            print("Detection pipeline completed. Checking database values...")
            
            # Step 6: Verify boxes in database
            res = requests.get("http://localhost:4000/api/projects")
            projects = res.json()
            active_p = next(p for p in projects if p["name"] == proj_name)
            p_pages = requests.get(f"http://localhost:4000/api/projects/{active_p['id']}/pages").json()
            test_page_id = p_pages[0]["id"]
            
            # Check Text Blocks count
            full_page_details = requests.get(f"http://localhost:4000/api/pages/{test_page_id}").json()
            blocks = full_page_details.get("text_blocks", [])
            print(f"YOLO detected {len(blocks)} blocks in the database.")
            
            if len(blocks) == 0:
                raise Exception("Detection produced 0 boxes. Detection model or preprocessing coordinate mapping is broken.")
                
            report["steps"].append(f"5. Detect run - SUCCESS ({len(blocks)} bubbles found)")
            
            # Report coordinates
            for idx, b in enumerate(blocks):
                print(f" - Block {idx}: x={b['x']:.1f}, y={b['y']:.1f}, w={b['width']:.1f}, h={b['height']:.1f}, confidence={b['confidence']:.2f}")
                
            # Step 7: Run OCR
            print("Step 6: Running OCR step...")
            page.click("button:has-text('2. OCR')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=30000)
            page.wait_for_timeout(2000)
            page.screenshot(path=str(DIAGNOSTICS_DIR / "06_after_ocr.png"))
            
            # Step 8: Run Inpaint & Render
            print("Step 7: Running Inpaint & Final Render steps...")
            page.click("button:has-text('4. Inpaint Clean')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=30000)
            page.wait_for_timeout(2000)
            
            page.click("button:has-text('5. Final Render')")
            page.wait_for_selector("text=Running Pipeline", state="detached", timeout=30000)
            page.wait_for_timeout(3000)
            
            # Capture final rendered canvas
            page.screenshot(path=str(DIAGNOSTICS_DIR / "07_final_rendered.png"))
            print("Pipeline E2E Test execution complete!")
            report["steps"].append("6. Run OCR, Inpaint, Render - SUCCESS")
            
            # Clean up test project by deleting it
            print("Cleaning up test project...")
            requests.delete(f"http://localhost:4000/api/projects/{active_p['id']}")
            
            browser.close()
            report["status"] = "success"
            
    except Exception as e:
        print(f"E2E Test Failed with error: {e}")
        report["errors"].append(str(e))
        
    return report

def main():
    print("=== HOUMI E2E DIAGNOSTIC AND INTEGRATION TESTING SYSTEM ===")
    
    # 1. Clean ports
    print("Cleaning local ports 4000 and 5173...")
    kill_port(4000)
    kill_port(5173)
    
    # 2. Generate sample image
    static_sample_dir = BACKEND_DIR / "app" / "static"
    static_sample_dir.mkdir(parents=True, exist_ok=True)
    generate_test_image(static_sample_dir / "test_sample.png")
    
    # 3. Start Backend subprocess
    print("Starting Backend FastAPI Server (Port 4000)...")
    backend_proc = subprocess.Popen(
        [VENV_PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "4000"],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # Start thread to log backend output silently or to file
    backend_log = open(DIAGNOSTICS_DIR / "backend_test.log", "w", encoding="utf-8")
    def stream_log(proc, log_file):
        for line in proc.stdout:
            log_file.write(line)
            log_file.flush()
            
    import threading
    t_log = threading.Thread(target=stream_log, args=(backend_proc, backend_log), daemon=True)
    t_log.start()
    
    # 4. Wait for Backend (allow up to 60 seconds because OCR model loading takes time)
    print("Waiting for FastAPI server to become active...")
    if not wait_for_url("http://127.0.0.1:4000/api/health", 60):
        print("Backend failed to start. Exiting.")
        backend_proc.terminate()
        return
        
    print("Backend is online!")
    
    # 5. Start Frontend subprocess
    print("Starting Frontend Vite Dev Server (Port 5173)...")
    # Using shell=True for npm command in Windows
    frontend_proc = subprocess.Popen(
        "npm run dev",
        cwd=str(FRONTEND_DIR),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    frontend_log = open(DIAGNOSTICS_DIR / "frontend_test.log", "w", encoding="utf-8")
    t_flog = threading.Thread(target=stream_log, args=(frontend_proc, frontend_log), daemon=True)
    t_flog.start()
    
    # 6. Wait for Frontend (allow up to 40 seconds)
    print("Waiting for Vite dev server to become active...")
    if not wait_for_url("http://localhost:5173", 40):
        print("Frontend failed to start. Exiting.")
        backend_proc.terminate()
        frontend_proc.terminate()
        return
        
    print("Frontend is online!")
    
    # 7. Run Playwright Tests
    e2e_report = run_e2e_tests()
    
    # 8. Clean up servers
    print("\nTerminating Backend and Frontend subprocesses...")
    backend_proc.terminate()
    # In Windows, killing npm dev server running under shell requires taskkill
    kill_port(5173)
    kill_port(4000)
    
    backend_log.close()
    frontend_log.close()
    
    # Write report
    report_file = DIAGNOSTICS_DIR / "e2e_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(e2e_report, f, indent=4)
        
    print(f"\nDiagnostics Completed. Status: {e2e_report['status'].upper()}")
    print(f"Report saved to: {report_file}")
    print("Visual screenshots saved to:", DIAGNOSTICS_DIR)

if __name__ == "__main__":
    main()
