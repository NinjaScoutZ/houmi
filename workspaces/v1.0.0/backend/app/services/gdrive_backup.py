"""
Houmi Studio - Google Drive Cloud Backup Service
Automatically backs up software releases, OTA delta patches, and database snapshots
to a structured Google Drive cloud storage hierarchy.
"""

from __future__ import annotations

import os
import io
import json
import shutil
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    HAS_GOOGLE_API = True
except ImportError:
    Credentials = None  # type: ignore
    Request = None  # type: ignore
    build = None  # type: ignore
    MediaFileUpload = None  # type: ignore
    HAS_GOOGLE_API = False

from app.config import DATA_DIR, APP_DIR, BASE_DIR

logger = logging.getLogger("houmi-gdrive-backup")

CREDENTIALS_DIR = DATA_DIR / "google_credentials"
CONFIG_FILE = CREDENTIALS_DIR / "google_config.json"
TOKEN_FILE = CREDENTIALS_DIR / "google_token.json"

ROOT_BACKUP_FOLDER_NAME = "Houmi Studio Cloud Backups"
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def _get_google_credentials() -> Optional[Credentials]:
    """Loads and automatically refreshes Google OAuth2 credentials."""
    # Check primary or fallback paths
    token_path = TOKEN_FILE
    if not token_path.exists():
        fallback = Path(r"C:\Users\dansa\Desktop\Alert Danel\data\google_token.json")
        if fallback.exists():
            token_path = fallback

    config_path = CONFIG_FILE
    if not config_path.exists():
        fallback_cfg = Path(r"C:\Users\dansa\Desktop\Alert Danel\data\google_config.json")
        if fallback_cfg.exists():
            config_path = fallback_cfg

    if not token_path.exists():
        logger.warning(f"Google Drive token file not found at {token_path}")
        return None

    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
        cfg = {}
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        client_id = cfg.get("client_id", "343246439295-snfrtmudlvuc0ghp024qen093epdkjpr.apps.googleusercontent.com")
        client_secret = cfg.get("client_secret", "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")

        token_scopes = data.get("scope", "").split() if data.get("scope") else SCOPES

        creds = Credentials(
            token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=token_scopes,
        )

        if creds and creds.expired and creds.refresh_token:
            logger.info("Google Drive token expired, refreshing...")
            creds.refresh(Request())
            data["access_token"] = creds.token
            try:
                TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
                TOKEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                pass

        return creds
    except Exception as exc:
        logger.error(f"Failed to load Google Drive credentials: {exc}")
        return None


def get_gdrive_auth_status() -> Dict[str, Any]:
    """Returns the current connection status to Google Drive."""
    creds = _get_google_credentials()
    if not creds:
        return {
            "connected": False,
            "email": None,
            "name": None,
            "picture": None,
        }

    email = "workingappapt@gmail.com"
    name = "Pratchaya"
    picture = None

    token_path = TOKEN_FILE if TOKEN_FILE.exists() else Path(r"C:\Users\dansa\Desktop\Alert Danel\data\google_token.json")
    if token_path.exists():
        try:
            d = json.loads(token_path.read_text(encoding="utf-8"))
            u = d.get("user_info", {})
            email = u.get("email", email)
            name = u.get("name", name)
            picture = u.get("picture", picture)
        except Exception:
            pass

    return {
        "connected": True,
        "email": email,
        "name": name,
        "picture": picture,
        "token_valid": creds.valid if creds else False,
    }


def _get_drive_service():
    creds = _get_google_credentials()
    if not creds:
        raise RuntimeError("Google Drive is not authenticated. Please check google_token.json.")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _find_or_create_folder(service, folder_name: str, parent_id: Optional[str] = None) -> str:
    """Finds an existing folder by name and parent or creates a new one."""
    q = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        q += f" and '{parent_id}' in parents"

    results = service.files().list(q=q, spaces="drive", fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        file_metadata["parents"] = [parent_id]

    folder = service.files().create(body=file_metadata, fields="id, webViewLink").execute()
    return folder.get("id")


def _upload_or_replace_file(service, file_path: Path, parent_folder_id: str, mime_type: str = "application/zip") -> Dict[str, Any]:
    """Uploads or updates a file in Google Drive."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = file_path.name
    q = f"name = '{filename}' and '{parent_folder_id}' in parents and trashed = false"
    res = service.files().list(q=q, spaces="drive", fields="files(id, name, webViewLink)").execute()
    existing_files = res.get("files", [])

    media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)

    if existing_files:
        file_id = existing_files[0]["id"]
        logger.info(f"Updating existing Google Drive file {filename} (id={file_id})...")
        updated = service.files().update(fileId=file_id, media_body=media, fields="id, name, webViewLink, size").execute()
        return {
            "id": updated.get("id"),
            "name": filename,
            "web_link": updated.get("webViewLink"),
            "size_mb": round(file_path.stat().st_size / (1024 * 1024), 2),
            "action": "updated",
        }
    else:
        logger.info(f"Creating new Google Drive file {filename} in folder {parent_folder_id}...")
        file_metadata = {"name": filename, "parents": [parent_folder_id]}
        created = service.files().create(body=file_metadata, media_body=media, fields="id, name, webViewLink, size").execute()
        return {
            "id": created.get("id"),
            "name": filename,
            "web_link": created.get("webViewLink"),
            "size_mb": round(file_path.stat().st_size / (1024 * 1024), 2),
            "action": "created",
        }


def backup_releases_to_gdrive() -> Dict[str, Any]:
    """
    Backs up all version archives (v1.0.4, v1.0.1, v1.0.0, latest_patch.zip) to Google Drive.
    """
    service = _get_drive_service()
    root_id = _find_or_create_folder(service, ROOT_BACKUP_FOLDER_NAME)
    releases_folder_id = _find_or_create_folder(service, "Releases & OTA Patches", parent_id=root_id)

    uploaded_files = []

    # 1. Backup latest_patch.zip
    latest_zip = DATA_DIR / "patches" / "latest_patch.zip"
    if not latest_zip.exists():
        latest_zip = APP_DIR / "houmi_latest_patch.zip"
    if latest_zip.exists():
        info = _upload_or_replace_file(service, latest_zip, releases_folder_id)
        uploaded_files.append(info)

    # 2. Backup update_manifest.json
    manifest_file = DATA_DIR / "update_manifest.json"
    if manifest_file.exists():
        info = _upload_or_replace_file(service, manifest_file, releases_folder_id, mime_type="application/json")
        uploaded_files.append(info)

    # 3. Backup all archived releases (v1.0.4, etc.)
    releases_dir = DATA_DIR / "releases"
    if releases_dir.exists():
        for rel_dir in releases_dir.iterdir():
            if rel_dir.is_dir():
                v_zip = rel_dir / "patch.zip"
                if v_zip.exists():
                    target_name = f"HoumiStudio_Release_{rel_dir.name}.zip"
                    temp_copy = DATA_DIR / target_name
                    shutil.copy2(v_zip, temp_copy)
                    try:
                        info = _upload_or_replace_file(service, temp_copy, releases_folder_id)
                        uploaded_files.append(info)
                    finally:
                        if temp_copy.exists():
                            temp_copy.unlink()

    folder_meta = service.files().get(fileId=releases_folder_id, fields="id, webViewLink").execute()

    return {
        "ok": True,
        "folder_name": "Releases & OTA Patches",
        "folder_url": folder_meta.get("webViewLink", f"https://drive.google.com/drive/folders/{releases_folder_id}"),
        "uploaded_count": len(uploaded_files),
        "files": uploaded_files,
        "timestamp": datetime.utcnow().isoformat(),
    }


def backup_database_to_gdrive() -> Dict[str, Any]:
    """
    Creates a snapshot of the database and changelogs and uploads it to Google Drive.
    """
    service = _get_drive_service()
    root_id = _find_or_create_folder(service, ROOT_BACKUP_FOLDER_NAME)
    db_folder_id = _find_or_create_folder(service, "Database Snapshots", parent_id=root_id)

    uploaded_files = []
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # 1. Backup SQLite or snapshot
    db_file = DATA_DIR / "houmi.db"
    if db_file.exists():
        snapshot_name = f"houmi_db_snapshot_{timestamp}.db"
        temp_db = DATA_DIR / snapshot_name
        shutil.copy2(db_file, temp_db)
        try:
            info = _upload_or_replace_file(service, temp_db, db_folder_id, mime_type="application/x-sqlite3")
            uploaded_files.append(info)
        finally:
            if temp_db.exists():
                temp_db.unlink()

    # 2. Backup changelogs.json and rollback_ledger.json
    for json_name in ["changelogs.json", "rollback_ledger.json", "update_manifest.json"]:
        target = DATA_DIR / json_name
        if not target.exists():
            target = DATA_DIR / "patches" / json_name
        if target.exists():
            info = _upload_or_replace_file(service, target, db_folder_id, mime_type="application/json")
            uploaded_files.append(info)

    folder_meta = service.files().get(fileId=db_folder_id, fields="id, webViewLink").execute()

    return {
        "ok": True,
        "folder_name": "Database Snapshots",
        "folder_url": folder_meta.get("webViewLink", f"https://drive.google.com/drive/folders/{db_folder_id}"),
        "uploaded_count": len(uploaded_files),
        "files": uploaded_files,
        "timestamp": datetime.utcnow().isoformat(),
    }


def run_full_system_backup_to_gdrive() -> Dict[str, Any]:
    """Runs a complete cloud backup of all releases, database snapshots, and manifests to Google Drive."""
    rel_res = backup_releases_to_gdrive()
    db_res = backup_database_to_gdrive()

    return {
        "ok": True,
        "google_account": get_gdrive_auth_status().get("email", "Google Drive Connected"),
        "releases_backup": rel_res,
        "database_backup": db_res,
        "total_files_uploaded": rel_res.get("uploaded_count", 0) + db_res.get("uploaded_count", 0),
        "completed_at": datetime.utcnow().isoformat(),
    }
