import datetime
import unittest

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.all_models import Project, User
from app.services.asset_service import validate_asset_payload
from app.services.job_service import (
    append_job_event,
    claim_next_job,
    create_job,
    heartbeat_job,
    recover_expired_jobs,
)
from app.security.tokens import hash_password


class TestAssetAndJobServices(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(username="worker-user", email="worker@example.test", password_hash=hash_password("password123"))
        self.db.add(self.user)
        self.db.flush()
        self.project = Project(name="remote", owner_id=self.user.id)
        self.db.add(self.project)
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.project)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_asset_validation_uses_magic_bytes_and_pixel_budget(self):
        image = Image.new("RGB", (10, 20), (255, 255, 255))
        from io import BytesIO

        output = BytesIO()
        image.save(output, format="PNG")
        payload = output.getvalue()
        validated = validate_asset_payload(payload, declared_media_type="image/png")
        self.assertEqual(validated.media_type, "image/png")
        self.assertEqual((validated.width, validated.height), (10, 20))
        with self.assertRaises(ValueError):
            validate_asset_payload(b"not-an-image", filename="fake.png")

    def test_job_claim_heartbeat_and_recovery(self):
        job = create_job(
            self.db,
            user_id=self.user.id,
            project_id=self.project.id,
            job_type="ocr",
            input_manifest={"asset_ids": []},
            idempotency_key="request-1",
        )
        claimed = claim_next_job(self.db, worker_id="gpu-1")
        self.assertEqual(claimed.id, job.id)
        self.assertTrue(heartbeat_job(self.db, job_id=job.id, worker_id="gpu-1", lease_token=claimed.lease_token))
        event = append_job_event(self.db, job_id=job.id, event_type="progress", payload={"percent": 10})
        self.assertEqual(event.sequence_num, 0)

        stale_at = datetime.datetime.utcnow() - datetime.timedelta(seconds=61)
        claimed.lease_expires_at = stale_at
        claimed.heartbeat_at = stale_at
        self.db.commit()
        recovered = recover_expired_jobs(self.db)
        self.assertEqual(recovered, [job.id])


if __name__ == "__main__":
    unittest.main()
