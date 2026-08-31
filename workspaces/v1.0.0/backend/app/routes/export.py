"""
Export API Routes for Houmi.
Provides endpoints for flattened images or PSD ZIP bundles.
"""
import logging
from typing import Optional
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import DATA_DIR
from app.services.zip_export import export_project_psd_zip
from app.services.image_export import export_project_images
from app.security.dependencies import get_current_user_or_local, require_resource_access

router = APIRouter(
    tags=["Export"],
    dependencies=[Depends(get_current_user_or_local), Depends(require_resource_access)],
)
logger = logging.getLogger("houmi-export-router")


@router.post("/projects/{project_id}/export/images")
def api_export_images(
    project_id: str,
    format: str = "png",
    db: Session = Depends(get_db),
):
    """Render every page and write PNG/JPEG files beside the source images."""
    try:
        paths = export_project_images(project_id, db, format)
        return {"status": "success", "format": format.lower(), "paths": [str(path) for path in paths]}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Image export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image export failed: {e}",
        )


@router.get("/export/page/{page_id}/jsx")
def api_export_page_jsx(
    page_id: str,
    text_mode: str = "paragraph",
    db: Session = Depends(get_db)
):
    """Export page as an ImageTrans-style ExtendScript (.jsx) file for direct Photoshop execution."""
    try:
        from app.services.jsx_export import export_page_jsx
        jsx_path = export_page_jsx(page_id=page_id, db=db, text_mode=text_mode)
        return FileResponse(
            path=str(jsx_path),
            media_type="text/plain",
            filename=jsx_path.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("JSX export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"JSX export failed: {e}",
        )


@router.post("/export/open-in-photoshop")
def api_open_in_photoshop(
    page_id: Optional[str] = None,
    project_id: Optional[str] = None,
    text_mode: str = "paragraph",
    force: bool = True,
    db: Session = Depends(get_db)
):
    """
    Executes ImageTrans-style native JSX generation directly inside Photoshop via COM/CLI.
    Launches Photoshop on screen with 100% native Photoshop text layers for single page OR whole project.
    """
    try:
        from app.services.jsx_export import (
            generate_page_jsx_script,
            export_page_jsx,
            generate_project_jsx_script,
            export_project_jsx
        )

        if project_id:
            jsx_script = generate_project_jsx_script(project_id=project_id, db=db, text_mode=text_mode, auto_save_psd=True)
            jsx_path = export_project_jsx(project_id=project_id, db=db, text_mode=text_mode)
            msg = f"Opened project {project_id} in Photoshop with master JSX script!"
        elif page_id:
            jsx_script = generate_page_jsx_script(page_id=page_id, db=db, text_mode=text_mode, auto_save_psd=True)
            jsx_path = export_page_jsx(page_id=page_id, db=db, text_mode=text_mode)
            msg = f"Opened page {page_id} in Photoshop with native JSX script!"
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either page_id or project_id must be provided")

        # Execute in Photoshop via COM if active/available
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()
            ps = win32com.client.Dispatch("Photoshop.Application")
            ps.DoJavaScript(jsx_script)
            logger.info(msg)
        except Exception as com_err:
            logger.warning(f"Photoshop COM dispatch failed: {com_err}. Launching Photoshop process with JSX...")
            ps_exe = Path(r"C:\Program Files\Adobe\Adobe Photoshop 2026\Photoshop.exe")
            if not ps_exe.exists():
                found = list(Path(r"C:\Program Files\Adobe").glob("Adobe Photoshop */Photoshop.exe"))
                if found:
                    ps_exe = found[-1]

            if ps_exe.exists():
                import subprocess
                subprocess.Popen([str(ps_exe), str(jsx_path)])
            else:
                import os
                os.startfile(str(jsx_path))

        return {
            "status": "success",
            "message": msg,
            "jsx_path": str(jsx_path),
        }
    except Exception as e:
        logger.exception("Failed to open Photoshop via JSX")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to open Photoshop: {e}"
        )


@router.get("/projects/{project_id}/export/psd-zip")
def api_export_psd_zip(
    project_id: str,
    text_mode: str = "paragraph",
    db: Session = Depends(get_db)
):
    """Export all pages as individual PSD files bundled in a ZIP archive."""
    try:
        zip_path = export_project_psd_zip(
            project_id=project_id,
            db=db,
            text_mode=text_mode,
        )
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=zip_path.name,
            headers={
                "X-Houmi-Export-Path": quote(str(zip_path), safe=""),
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("PSD ZIP export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PSD ZIP export failed: {e}"
        )


@router.get("/projects/{project_id}/export/jsx-zip")
def api_export_jsx_zip(
    project_id: str,
    text_mode: str = "point",
    db: Session = Depends(get_db)
):
    """Export all pages as individual JSX ExtendScript files bundled in a ZIP archive."""
    try:
        from app.services.zip_export import export_project_jsx_zip
        zip_path = export_project_jsx_zip(
            project_id=project_id,
            db=db,
            text_mode=text_mode,
        )
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=zip_path.name,
            headers={
                "X-Houmi-Export-Path": quote(str(zip_path), safe=""),
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("JSX ZIP export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"JSX ZIP export failed: {e}"
        )


@router.get("/projects/export-yolo-dataset")
def api_export_yolo_dataset(
    project_ids: str,
    db: Session = Depends(get_db)
):
    """
    Export multiple projects as a single ZIP file containing images and labels in YOLO format.
    Accepts project_ids as a comma-separated string of project IDs.
    """
    from app.services.yolo_dataset_export import export_yolo_dataset
    
    if not project_ids or not project_ids.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required project_ids parameter"
        )
        
    pids = [pid.strip() for pid in project_ids.split(",") if pid.strip()]
    if not pids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project_ids parameter format"
        )
        
    try:
        zip_path = export_yolo_dataset(
            project_ids=pids,
            db=db
        )
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename="yolo_dataset.zip",
            headers={"Content-Disposition": "attachment; filename=yolo_dataset.zip"}
        )
    except Exception as e:
        logger.exception("YOLO dataset export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"YOLO dataset export failed: {e}"
        )


@router.get("/export/jsx-script")
def api_download_jsx_script():
    """Download the Photoshop JSX helper script for Thai World-Ready Composer formatting."""
    jsx_path = DATA_DIR / "scratch" / "format_thai_text.jsx"
    jsx_path.parent.mkdir(parents=True, exist_ok=True)
    jsx_path.write_text("""/* Houmi Photoshop JSX Helper Script */
#target photoshop
(function main() {
    if (app.documents.length === 0) { alert("กรุณาเปิดไฟล์ PSD ใน Photoshop ก่อนรันสคริปต์นี้"); return; }
    var doc = app.activeDocument;
    var count = 0;
    for (var i = 0; i < doc.layers.length; i++) {
        var layer = doc.layers[i];
        if (layer.kind === LayerKind.TEXT) {
            try { layer.textItem.autoLeading = true; layer.textItem.useFractionalLineWidths = true; } catch(e){}
            try {
                var idsetd = charIDToTypeID("setd");
                var desc1 = new ActionDescriptor();
                var ref1 = new ActionReference();
                ref1.putEnumerated(charIDToTypeID("TxLr"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
                desc1.putReference(charIDToTypeID("null"), ref1);
                var descText = new ActionDescriptor();
                descText.putInteger(stringIDToTypeID("composer"), 2);
                desc1.putObject(charIDToTypeID("to  "), charIDToTypeID("TxLr"), descText);
                executeAction(idsetd, desc1, DialogModes.NO);
            } catch(e){}
            count++;
        }
    }
    try {
        doc.save();
    } catch(err) {}
    alert("ปรับแต่งฟอร์แมตภาษาไทยและบันทึกไฟล์เรียบร้อยแล้ว! (" + count + " เลเยอร์)");
})();
""", encoding="utf-8")
    return FileResponse(
        path=str(jsx_path),
        media_type="text/plain",
        filename="format_thai_text.jsx",
    )

