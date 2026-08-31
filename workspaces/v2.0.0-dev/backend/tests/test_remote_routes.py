import asyncio
import io
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import UploadFile

from app.database import Base
from app.models.all_models import LicenseEntitlement, Project, User
from app.routes.assets import download_asset, upload_asset
from app.routes.jobs import JobCreateRequest, enqueue_job, get_job
from app.security.tokens import hash_password


class TestRemoteRoutes(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            username="remote-user",
            email="remote@example.test",
            password_hash=hash_password("password123"),
        )
        self.db.add(self.user)
        self.db.flush()
        self.project = Project(name="remote-project", owner_id=self.user.id)
        self.db.add(self.project)
        self.db.flush()
        from datetime import datetime, timedelta

        self.db.add(
            LicenseEntitlement(
                user_id=self.user.id,
                starts_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=1),
            )
        )
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.project)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def _png_upload() -> UploadFile:
        output = io.BytesIO()
        Image.new("RGB", (8, 12), (240, 240, 240)).save(output, format="PNG")
        output.seek(0)
        return UploadFile(filename="page.png", file=output, headers={"content-type": "image/png"})

    def test_remote_asset_upload_records_metadata_and_download_is_scoped(self):
        import app.routes.assets as assets_route

        with tempfile.TemporaryDirectory() as temp_dir:
            original_root = assets_route.ASSET_STORAGE_DIR
            assets_route.ASSET_STORAGE_DIR = Path(temp_dir)
            try:
                created = asyncio.run(
                    upload_asset(
                        self._png_upload(),
                        project_id=self.project.id,
                        db=self.db,
                        current_user=self.user,
                    )
                )
                self.assertEqual(created["media_type"], "image/png")
                self.assertEqual(created["width"], 8)

                response = download_asset(
                    created["id"],
                    db=self.db,
                    current_user=self.user,
                    _=self.user,
                )
                self.assertEqual(Path(response.path).read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            finally:
                assets_route.ASSET_STORAGE_DIR = original_root

    def test_job_api_is_idempotent_and_owner_scoped(self):
        request = JobCreateRequest(
            project_id=self.project.id,
            job_type="ocr",
            input_manifest={"asset_ids": []},
            idempotency_key="same-request",
        )
        first = enqueue_job(request, db=self.db, current_user=self.user)
        second = enqueue_job(request, db=self.db, current_user=self.user)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(get_job(first["id"], db=self.db, current_user=self.user, _=self.user)["status"], "queued")

        foreign = User(username="foreign-user", email="foreign@example.test", password_hash="hash")
        self.db.add(foreign)
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            get_job(first["id"], db=self.db, current_user=foreign, _=foreign)
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
