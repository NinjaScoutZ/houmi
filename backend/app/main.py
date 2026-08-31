import threading
import logging
import shutil
import json
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import AUTO_CREATE_SCHEMA, CORS_ORIGINS, HOST, PORT, PROJECTS_DIR, RUNTIME_MODE
from app.database import Base, engine, ensure_local_schema_compatibility, get_db
from app.ocr_manager import ocr_manager
from app.routes import projects, pages, blocks, exchange, pipeline, diagnostics, export, typesetting, fonts, auth, assets, jobs, admin
from app.ws_manager import ws_manager
from fastapi import WebSocket, WebSocketDisconnect
import app.services.serializer_hook

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("houmi-api")

try:
    from app.services.crash_logger import install_crash_handlers
    install_crash_handlers()
except Exception as e:
    logger.warning("Could not install crash handlers: %s", e)

# Local Desktop keeps the legacy first-run convenience of creating its SQLite
# schema. Host/worker/admin deployments must run Alembic before startup and
# deliberately fail closed if the schema is not prepared.
if AUTO_CREATE_SCHEMA:
    logger.info("Initializing local database tables...")
    Base.metadata.create_all(bind=engine)
    ensure_local_schema_compatibility()
else:
    logger.info(
        "Skipping automatic schema creation (runtime_mode=%s); use Alembic migrations",
        RUNTIME_MODE,
    )

maintain_thread = None
ocr_started_by_this_process = False


def check_models_integrity_on_startup():
    """Exhaustively inspect all required AI model files on application startup and report to console."""
    try:
        from app.config import MODELS_DIR, INPAINT_MODEL_PATH, BALLOON_MODEL_PATH
        unet_path = MODELS_DIR / "manga_text_segmentation" / "manga_unet.onnx"
        sam_path = MODELS_DIR / "sam" / "sam2.1_hiera_base_plus.encoder.onnx"
        
        models = [
            ("Manga UNet++ (สแกนอักษร AI)", unet_path, True),
            ("LaMa-Manga Inpainter (AI ลบคำ)", INPAINT_MODEL_PATH, True),
            ("YOLO Balloon Detector (AI บอลลูน)", BALLOON_MODEL_PATH, True),
            ("Meta SAM 2.1 Segmenter (AI SFX)", sam_path, False),
        ]
        
        missing_critical = []
        print("\n" + "=" * 65)
        print("🤖 HOUMI STUDIO - STARTUP AI ENGINE INTEGRITY AUDIT")
        print("=" * 65)
        print(f"📁 Models Directory: {MODELS_DIR}")
        for name, path, critical in models:
            exists = path.exists()
            if exists:
                size_mb = round(path.stat().st_size / 1024 / 1024, 1)
                print(f"  ✅ {name:<35}: READY ({size_mb} MB)")
            else:
                status_text = "MISSING [CRITICAL]" if critical else "OPTIONAL (Not Installed)"
                print(f"  ❌ {name:<35}: {status_text}")
                if critical:
                    missing_critical.append((name, str(path)))
        print("-" * 65)
        if not missing_critical:
            print("🎉 STATUS: 🟢 ALL AI ENGINES ARE READY AND OPERATIONAL!")
        else:
            print(f"⚠️  STATUS: 🔴 DEGRADED - {len(missing_critical)} CRITICAL AI MODEL(S) MISSING!")
            print("💡 FIX: Run online update or place models in the models directory.")
        print("=" * 65 + "\n")
    except Exception as e_audit:
        logger.warning(f"Startup model integrity audit error: {e_audit}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global maintain_thread, ocr_started_by_this_process
    logger.info("Application starting up...")
    check_models_integrity_on_startup()

    # Host/Admin must remain a lightweight API process. GPU/OCR services are
    # owned by the desktop process or app.worker_runtime so a web restart
    # cannot duplicate them.
    if RUNTIME_MODE == "local":
        # 0. Auto-Check & Apply Delta Patch from Central Server on startup if update is available
        def _auto_apply_patch_on_startup():
            try:
                from app.routes.updater import check_for_update, apply_patch
                logger.info("Checking for startup delta patches from Central Server...")
                info = check_for_update()
                if info.get("update_available"):
                    logger.info("Update available (%s -> %s). Applying delta patch...", info.get("current_version"), info.get("latest_version"))
                    res = apply_patch()
                    logger.info("Startup delta patch result: %s", res)
                else:
                    logger.info("Application is up to date (v%s).", info.get("current_version"))
            except Exception as e_ap:
                logger.warning("Startup delta patch check skipped: %s", e_ap)

        threading.Thread(target=_auto_apply_patch_on_startup, daemon=True).start()

        # 1. Start OCR Managed Subprocess
        logger.info("Launching DeepSeek OCR Subprocess...")
        ocr_manager.start_server()
        ocr_started_by_this_process = True

        # 2. Start Keep-Alive daemon thread for OCR
        maintain_thread = threading.Thread(target=ocr_manager.maintain_server, daemon=True)
        maintain_thread.start()

        # 3. Pre-load YOLO and LaMa models in a background daemon thread
        def preload_models():
            try:
                from app.services.detector import balloon_detector
                logger.info("Background warming up Balloon detector...")
                balloon_detector.load_model()
            except Exception as e:
                logger.error(f"Failed to preload Balloon detector: {e}")

            try:
                from app.services.inpaint_server_manager import inpaint_manager
                inpaint_manager.start_server_if_needed()
            except Exception as e:
                logger.warning(f"Failed to auto-start GPU inpaint server: {e}")

            try:
                from app.services.inpainter import _get_lama
                logger.info("Background warming up GPU/Port inpainter...")
                _get_lama()
            except Exception as e:
                logger.error(f"Failed to preload Inpainter: {e}")

        threading.Thread(target=preload_models, daemon=True).start()
    else:
        logger.info("Skipping OCR/GPU model startup in %s runtime; use app.worker_runtime.", RUNTIME_MODE)

    # 4. Generate missing project.json files for existing projects in background
    def generate_missing_project_jsons():
        from app.database import SessionLocal
        from app.models.all_models import Project
        from app.services.project_serializer import save_project_json
        from app.services.project_paths import project_workspace_dir, uses_external_workspace
        
        db = SessionLocal()
        try:
            projects = db.query(Project).all()
            for p in projects:
                # A missing manifest in a folder-backed project is deliberate:
                # it means the user removed its local state to import fresh.
                # Only recover internal project metadata automatically.
                if uses_external_workspace(p):
                    continue
                json_path = project_workspace_dir(p) / "project.json"
                if not json_path.exists():
                    logger.info(f"Generating missing project.json for project: {p.name} ({p.id})")
                    save_project_json(p.id, db)
        except Exception as e:
            logger.error(f"Failed to generate missing project jsons: {e}")
        finally:
            db.close()

    threading.Thread(target=generate_missing_project_jsons, daemon=True).start()

    yield

    logger.info("Application shutting down...")

    try:
        from app.services.text_mask import shutdown_high_quality_text_mask_worker
        shutdown_high_quality_text_mask_worker()
    except Exception as e:
        logger.warning("Failed to stop high-quality text-mask worker: %s", e)
    
    # 1. Terminate OCR Subprocess only when this process owns it.
    if ocr_started_by_this_process:
        logger.info("Stopping DeepSeek OCR Subprocess...")
        ocr_manager.stop_server()


app = FastAPI(
    title="Houmi API",
    description="Manga Translation Studio Backend API",
    version="1.0.0",
    lifespan=lifespan
)

from fastapi import Response

@app.get("/runtime-config.js", include_in_schema=False)
def runtime_config_script() -> Response:
    mode = "remote" if RUNTIME_MODE in {"host", "admin"} else "local"
    payload = {
        "mode": mode,
        "apiBaseUrl": "https://houmi.click" if mode == "remote" else "",
        "wsBaseUrl": "wss://houmi.click" if mode == "remote" else "",
    }
    return Response(
        content=f"window.__HOUMI_RUNTIME_CONFIG__ = {json.dumps(payload)};",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )

class CacheControlledStaticFiles(StaticFiles):
    def __init__(self, *args, cache_max_age: int = 31536000, **kwargs):
        self.cache_max_age = cache_max_age
        super().__init__(*args, **kwargs)

    async def get_response(self, path: str, scope) -> Response:
        from pathlib import Path
        import logging
        
        full_path = Path(self.directory) / path
        
        # Page-list thumbnails are deliberately separate from canvas previews:
        # a webtoon preview can be 1200x60,000 even when displayed at 48x64.
        if path.endswith("thumbnail.jpg") and not full_path.exists():
            source_file = None
            for ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
                candidate = full_path.parent / f"source{ext}"
                if candidate.exists():
                    source_file = candidate
                    break
            if not source_file and (full_path.parent / "preview.jpg").exists():
                source_file = full_path.parent / "preview.jpg"
            if not source_file and full_path.parent.exists():
                for f in full_path.parent.glob("*"):
                    if f.is_file() and f.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp", ".bmp"] and not f.name.endswith("thumbnail.jpg"):
                        source_file = f
                        break
            if source_file:
                try:
                    from app.routes.pages import create_page_thumbnail
                    create_page_thumbnail(source_file, output_path=full_path)
                    logging.getLogger("houmi-static").info(
                        "Dynamically generated page thumbnail: %s", full_path
                    )
                except Exception as e:
                    logging.getLogger("houmi-static").error(
                        "Failed to dynamically generate thumbnail: %s", e
                    )

        # 1. Check if the requested file is a JPEG preview but is missing on disk
        elif path.endswith("preview.jpg") and not full_path.exists():
            # Find any source candidate file in the directory
            source_file = None
            for ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
                candidate = full_path.parent / f"source{ext}"
                if candidate.exists():
                    source_file = candidate
                    break
            if not source_file and full_path.parent.exists():
                for f in full_path.parent.glob("*"):
                    if f.is_file() and f.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp", ".bmp"] and not f.name.endswith("preview.jpg") and not f.name.endswith("thumbnail.jpg"):
                        source_file = f
                        break
            
            if source_file:
                try:
                    from app.routes.pages import create_preview_image
                    create_preview_image(source_file, output_path=full_path)
                    logging.getLogger("houmi-static").info(f"Dynamically generated JPEG preview: {full_path}")
                except Exception as e:
                    logging.getLogger("houmi-static").error(f"Failed to dynamically generate JPEG preview: {e}")
        
        # 2. Check if requested file is inpainted preview but is missing on disk
        elif path.endswith("preview_inpainted.jpg") and not full_path.exists():
            inpainted_png = full_path.parent / "inpainted.png"
            if not inpainted_png.exists() and full_path.parent.name == "clean":
                legacy_inpainted = full_path.parent.parent / "inpainted.png"
                if legacy_inpainted.exists():
                    inpainted_png.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(legacy_inpainted, inpainted_png)
                    except OSError:
                        inpainted_png = legacy_inpainted
            if inpainted_png.exists():
                try:
                    from PIL import Image
                    with Image.open(inpainted_png) as img:
                        w, h = img.size
                        new_w, new_h = w, h
                        # Downscale if wider than 1200px
                        if w > 1200:
                            ratio = 1200 / w
                            new_w = 1200
                            new_h = int(h * ratio)
                        # JPEG limit check
                        if new_h > 60000:
                            scale_ratio = 60000 / new_h
                            new_w = int(new_w * scale_ratio)
                            new_h = 60000
                        if (new_w, new_h) != (w, h):
                            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                        img.save(full_path, "JPEG", quality=80)
                    logging.getLogger("houmi-static").info(f"Dynamically generated inpainted JPEG preview: {full_path}")
                except Exception as e:
                    logging.getLogger("houmi-static").error(f"Failed to dynamically generate inpainted JPEG: {e}")
            else:
                # Fallback to serving the original preview.jpg if page is not inpainted yet
                preview_jpg_path = full_path.parent / "preview.jpg"
                if not preview_jpg_path.exists():
                    # Generate preview.jpg first
                    source_file = None
                    for ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
                        candidate = full_path.parent / f"source{ext}"
                        if candidate.exists():
                            source_file = candidate
                            break
                    if source_file:
                        try:
                            from app.routes.pages import create_preview_image
                            create_preview_image(source_file)
                        except Exception:
                            pass
                
                if preview_jpg_path.exists():
                    fallback_path = str(Path(path).parent / "preview.jpg")
                    return await super().get_response(fallback_path, scope)
                    
        return await super().get_response(path, scope)

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = f"public, max-age={self.cache_max_age}, immutable"
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        return response

# Serve manga project images statically with immutable caching
app.mount("/static/projects", CacheControlledStaticFiles(directory=str(PROJECTS_DIR)), name="projects")
_diagnostics_dir = PROJECTS_DIR.parent / "diagnostics"
_diagnostics_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/diagnostics", StaticFiles(directory=str(_diagnostics_dir)), name="diagnostics")

# CORS middleware for React UI & Desktop App connections
allowed_origins = list(dict.fromkeys(CORS_ORIGINS + [
    f"http://localhost:{PORT}",
    f"http://127.0.0.1:{PORT}",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://tauri.localhost",
    "https://tauri.localhost",
]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routes import projects, pages, blocks, exchange, pipeline, diagnostics, export, typesetting, fonts, auth, assets, jobs, admin, updater, dev_map, performance, qa, sfx, comic_export_routes, reading_order_routes, tm_routes
from app.routes import license_routes, cloud_service_routes

# Include API Routers — work routes always mounted
app.include_router(projects.router, prefix="/api")
app.include_router(pages.router, prefix="/api")
app.include_router(blocks.router, prefix="/api")
app.include_router(exchange.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(diagnostics.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(typesetting.router, prefix="/api")
app.include_router(fonts.router, prefix="/api")
app.include_router(assets.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(updater.router, prefix="/api")
app.include_router(dev_map.router, prefix="/api")
app.include_router(performance.router)
app.include_router(qa.router, prefix="/api")
app.include_router(sfx.router, prefix="/api")
app.include_router(comic_export_routes.router, prefix="/api")
app.include_router(reading_order_routes.router, prefix="/api")
app.include_router(tm_routes.router, prefix="/api")
app.include_router(cloud_service_routes.router, prefix="/api")

# --- Auth & License routing depends on RUNTIME_MODE ---
# Local desktop: frontend calls Central Server directly for auth; local backend
#   only provides license save/status endpoints + ws-ticket.
# Host/Admin (Central Server): full auth routes against PostgreSQL.
if RUNTIME_MODE == "local":
    app.include_router(license_routes.router, prefix="/api")
    # Mount only the license-status and ws-ticket endpoints from auth router
    app.include_router(auth.router, prefix="/api")
    logger.info("Local mode: license_routes mounted; auth routes available but redeem/login/register redirect to Central Server")
else:
    app.include_router(auth.router, prefix="/api")
    app.include_router(license_routes.router, prefix="/api")
    logger.info("Host mode: full auth routes mounted against PostgreSQL")

# Live Admin Remote Telemetry & Log Stream WebSocket
@app.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Stream health & diagnostics logs
            data = await websocket.receive_text()
            await websocket.send_json({
                "status": "connected",
                "server": "houmi-desktop",
                "timestamp": time.time(),
                "received": data,
            })
    except WebSocketDisconnect:
        logger.info("Admin telemetry WebSocket disconnected.")
    except Exception as exc:
        logger.warning(f"Telemetry WS error: {exc}")

# WebSocket progress tracking endpoint
@app.websocket("/ws/pipeline/{project_id}")
async def pipeline_ws(websocket: WebSocket, project_id: str):
    # Browser WebSocket clients cannot reliably attach an Authorization header.
    # They first obtain a single-use, 60-second ticket through REST. Never use
    # a reusable access token in this URL.
    ticket = websocket.query_params.get("ticket")
    if not ticket and RUNTIME_MODE != "local":
        await websocket.close(code=4001, reason="WebSocket ticket required")
        return

    if ticket:
        from app.routes.auth import consume_ws_ticket

        db_gen = get_db()
        db = next(db_gen)
        try:
            user_id = consume_ws_ticket(ticket, project_id, db)
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        if user_id is None:
            await websocket.close(code=4003, reason="Invalid or expired WebSocket ticket")
            return

    await ws_manager.connect(project_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep-alive
    except WebSocketDisconnect:
        ws_manager.disconnect(project_id, websocket)

# Health endpoint
@app.get("/api/health")
def api_health():
    return {
        "status": "online",
        "ocr_server_alive": ocr_manager.check_health()
    }

# Serve frontend statically in production
import os
import sys
from fastapi.responses import FileResponse
from pathlib import Path

def get_frontend_dist_dir() -> Path:
    # 1. Primary Authority: Explicit environment variable set by launcher/runtime
    env_dist = os.environ.get("HOUMI_FRONTEND_DIST")
    if env_dist:
        p = Path(env_dist).resolve()
        if p.exists() and (p / "index.html").exists():
            return p
        logger.warning(f"HOUMI_FRONTEND_DIST set to '{env_dist}' but index.html was not found.")

    # 2. Local workspace / worktree dist adjacent to backend
    worktree_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if worktree_dist.exists() and (worktree_dist / "index.html").exists():
        return worktree_dist

    # 3. PyInstaller frozen bundled assets
    if getattr(sys, "frozen", False):
        frozen_internal = Path(sys.executable).parent / "_internal" / "frontend" / "dist"
        if frozen_internal.exists() and (frozen_internal / "index.html").exists():
            return frozen_internal
        frozen_direct = Path(sys.executable).parent / "frontend" / "dist"
        if frozen_direct.exists() and (frozen_direct / "index.html").exists():
            return frozen_direct

    # 4. Fallback in data/patches/current ONLY if auto patch is explicitly allowed
    if os.environ.get("HOUMI_DISABLE_AUTO_PATCH") != "1":
        patch_dist = DATA_DIR / "patches" / "current" / "frontend" / "dist"
        if patch_dist.exists() and (patch_dist / "index.html").exists():
            return patch_dist

    return worktree_dist

FRONTEND_DIST_DIR = get_frontend_dist_dir()

if FRONTEND_DIST_DIR.exists() or True:
    logger.info(f"Serving frontend dynamically from: {FRONTEND_DIST_DIR}")

    from app.routes.admin import get_web_admin_portal
    
    @app.get("/admin", response_class=HTMLResponse)
    @app.get("/admin/", response_class=HTMLResponse)
    @app.get("/api/admin", response_class=HTMLResponse)
    @app.get("/api/admin/", response_class=HTMLResponse)
    async def serve_admin_portal():
        return get_web_admin_portal()

    from app.routes.central_landing import get_central_landing_html

    # Catch-all fallback route
    @app.get("/{fallback_path:path}")
    async def fallback(fallback_path: str):
        if fallback_path == "admin" or fallback_path == "admin/":
            return get_web_admin_portal()

        if fallback_path == "download" or fallback_path == "download/":
            return HTMLResponse(content=get_central_landing_html())

        # Prevent catching API or Static paths
        if (fallback_path.startswith("api") or 
            fallback_path.startswith("static")):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")

        dist = get_frontend_dist_dir()
        if fallback_path.startswith("assets/"):
            sub = fallback_path.replace("assets/", "", 1)
            apath = dist / "assets" / sub
            if apath.is_file():
                return FileResponse(str(apath))

        # On Central Server (host/admin mode), serve Central Service Portal on root
        if RUNTIME_MODE != "local" and (fallback_path == "" or fallback_path == "/"):
            return HTMLResponse(content=get_central_landing_html())

        file_path = dist / fallback_path
        if file_path.is_file():
            return FileResponse(str(file_path))
            
        if RUNTIME_MODE != "local":
            return HTMLResponse(content=get_central_landing_html())

        return FileResponse(
            str(dist / "index.html"),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
        )






# Add placeholder endpoints for routing structures (to be populated)
# app.include_router(projects.router, prefix="/api")
# app.include_router(pages.router, prefix="/api")
# app.include_router(blocks.router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
