from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any
from app.services.dev_patch_service import get_dev_history, record_dev_patch

router = APIRouter(prefix="/dev-map", tags=["dev-map"])

class ChangeItem(BaseModel):
    category: str = "Updated"
    description: str

class RecordPatchRequest(BaseModel):
    title: str
    summary: Optional[str] = ""
    component_tags: Optional[List[str]] = ["General"]
    author: Optional[str] = "Antigravity AI"
    changes: Optional[List[ChangeItem]] = []
    modified_files: Optional[List[str]] = []
    is_customer_release: Optional[bool] = False
    customer_version: Optional[str] = None
    model_config = ConfigDict(extra="allow")

@router.get("/history")
def get_history():
    return get_dev_history()

@router.get("/context")
def get_recent_context():
    history = get_dev_history()
    nodes = history.get("nodes", [])[:5]
    return {
        "recent_patches": nodes,
        "total": len(history.get("nodes", []))
    }

@router.post("/record")
def record_patch(req: RecordPatchRequest):
    data = req.model_dump()
    return record_dev_patch(data)

# --- Dev Notes Management ---
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
NOTES_DIR = DATA_DIR / "notes"

def ensure_initial_notes():
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    guide_note = NOTES_DIR / "Dev_Guidelines.md"
    if not guide_note.exists():
        with open(guide_note, "w", encoding="utf-8") as f:
            f.write("# Houmi Studio - Development Guidelines & Notes\n\n"
                    "Welcome to the Houmi Studio Dev Notes Manager!\n\n"
                    "## Key Rules\n"
                    "- Work directly as patches.\n"
                    "- Customer release tags (e.g. v0.3.1) are locked until explicit customer release announcement.\n"
                    "- All ongoing work is tagged under Dev label.\n"
                    "- Dev patches are logged under `data/dev_patches/` and synchronized to `CHANGELOG.md`.\n")

class SaveNoteRequest(BaseModel):
    filename: str
    content: str

@router.get("/notes")
def list_notes():
    ensure_initial_notes()
    notes = []
    for f in sorted(NOTES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        notes.append({
            "filename": f.name,
            "title": f.stem.replace("_", " ").title(),
            "updated_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            "size": f.stat().st_size
        })
    return {"notes": notes}

@router.get("/notes/{filename}")
def read_note(filename: str):
    file_path = NOTES_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Note not found")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"filename": filename, "title": file_path.stem.replace("_", " ").title(), "content": content}

@router.post("/notes")
def save_note(req: SaveNoteRequest):
    ensure_initial_notes()
    clean_name = req.filename.strip().replace(" ", "_")
    if not clean_name.endswith(".md"):
        clean_name += ".md"
    file_path = NOTES_DIR / clean_name
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(req.content)
    return {"status": "success", "filename": clean_name}

@router.delete("/notes/{filename}")
def delete_note(filename: str):
    file_path = NOTES_DIR / filename
    if file_path.exists():
        file_path.unlink()
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Note not found")

