import sys
import os
import json
import argparse
from pathlib import Path

# Add current directory to Python PATH to resolve app imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import SessionLocal

def main():
    parser = argparse.ArgumentParser(description="Houmi ML Pipeline CLI Bridge")
    parser.add_argument("step", choices=["detect", "ocr", "layout", "inpaint", "render", "auto", "inpaint-preview", "train", "import-psd"])
    parser.add_argument("--page-id", type=str, required=False)
    parser.add_argument("--min-confidence", type=float, required=False)
    parser.add_argument("--file-path", type=str, required=False)
    args = parser.parse_args()

    # Create DB Session
    db = SessionLocal()
    try:
        if args.step == "detect":
            if not args.page_id:
                print(json.dumps({"status": "error", "detail": "Missing --page-id"}))
                sys.exit(1)
            from app.routes.pipeline import run_detect
            res = run_detect(page_id=args.page_id, min_confidence=args.min_confidence, db=db)
            print(json.dumps(res))
            
        elif args.step == "ocr":
            if not args.page_id:
                print(json.dumps({"status": "error", "detail": "Missing --page-id"}))
                sys.exit(1)
            from app.routes.pipeline import run_ocr
            res = run_ocr(page_id=args.page_id, db=db)
            print(json.dumps(res))
            
        elif args.step == "inpaint":
            if not args.page_id:
                print(json.dumps({"status": "error", "detail": "Missing --page-id"}))
                sys.exit(1)
            from app.routes.pipeline import run_inpaint
            res = run_inpaint(page_id=args.page_id, db=db)
            print(json.dumps(res))

        elif args.step == "layout":
            if not args.page_id:
                print(json.dumps({"status": "error", "detail": "Missing --page-id"}))
                sys.exit(1)
            from app.routes.pipeline import run_layout
            res = run_layout(page_id=args.page_id, db=db)
            print(json.dumps(res))
            
        elif args.step == "render":
            if not args.page_id:
                print(json.dumps({"status": "error", "detail": "Missing --page-id"}))
                sys.exit(1)
            from app.routes.pipeline import run_render
            res = run_render(page_id=args.page_id, db=db)
            print(json.dumps(res))
            
        elif args.step == "auto":
            if not args.page_id:
                print(json.dumps({"status": "error", "detail": "Missing --page-id"}))
                sys.exit(1)
            from app.routes.pipeline import run_auto
            res = run_auto(page_id=args.page_id, min_confidence=args.min_confidence, db=db)
            print(json.dumps(res))
            
        elif args.step == "inpaint-preview":
            if not args.page_id:
                print(json.dumps({"status": "error", "detail": "Missing --page-id"}))
                sys.exit(1)
            from app.routes.pipeline import run_inpaint_preview
            res = run_inpaint_preview(page_id=args.page_id, db=db)
            print(json.dumps(res))
            
        elif args.step == "train":
            from app.routes.pipeline import run_train
            res = run_train()
            print(json.dumps(res))
            
        elif args.step == "import-psd":
            if not args.page_id or not args.file_path:
                print(json.dumps({"status": "error", "detail": "Missing --page-id or --file-path"}))
                sys.exit(1)
            from app.services.psd_import import import_psd_to_page
            res = import_psd_to_page(page_id=args.page_id, psd_path=args.file_path, db=db)
            print(json.dumps(res))
            
    except Exception as e:
        print(json.dumps({"status": "error", "detail": str(e)}), file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
