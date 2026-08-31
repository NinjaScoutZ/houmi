import sys
import os
import torch
from PIL import Image, ImageDraw
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OCR-Test")

# Add current dir to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from server import OCRService, Config

def create_test_image(path):
    img = Image.new('RGB', (1024, 1024), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    # Simple text to recognize
    d.text((100, 100), "DeepSeek OCR Test Success", fill=(0, 0, 0))
    img.save(path)
    return path

def main():
    print("========================================")
    print("   DeepSeek-OCR-2 FINAL VALIDATION   ")
    print("========================================")
    
    test_image_path = "test_ocr_input.png"
    create_test_image(test_image_path)
    
    ocr_service = OCRService()
    
    print("🔄 Loading Model (this may take a minute)...")
    try:
        ocr_service.load_model()
        print("✅ Model Loaded.")
        
        print(f"🔄 Running Inference on {test_image_path}...")
        # Use a timeout for the overall process if possible, but here we just wait
        result = ocr_service.run_inference(test_image_path, (1024, 1024))
        
        print("\n" + "="*40)
        print("🎉 INFERENCE COMPLETED SUCCESSFULLY!")
        print("="*40)
        print(f"📄 RESULT:\n{result}")
        print("="*40)
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
