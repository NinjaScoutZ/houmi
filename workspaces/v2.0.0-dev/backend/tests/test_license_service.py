import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.services.license_service import save_offline_license, verify_offline_license


class TestLicenseService(unittest.TestCase):
    def test_save_and_verify_valid_license(self):
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            license_path = tmppath / "license.json"

            with patch("app.services.license_service.LICENSE_FILE_PATH", license_path):
                future_expiry = datetime.now(timezone.utc) + timedelta(days=30)
                save_offline_license(
                    user_id="user-123",
                    username="testclient",
                    redeem_code="TEST-CODE-1234",
                    expires_at=future_expiry,
                    max_offline_days=30,
                )

                res = verify_offline_license()
                self.assertTrue(res["valid"])
                self.assertEqual(res["status"], "active")
                self.assertGreaterEqual(res["days_left"], 29)
                self.assertEqual(res["username"], "testclient")

    def test_verify_expired_license(self):
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            license_path = tmppath / "license.json"

            with patch("app.services.license_service.LICENSE_FILE_PATH", license_path):
                past_expiry = datetime.now(timezone.utc) - timedelta(days=1)
                save_offline_license(
                    user_id="user-123",
                    username="expiredclient",
                    redeem_code="EXPIRED-CODE-000",
                    expires_at=past_expiry,
                    max_offline_days=30,
                )

                res = verify_offline_license()
                self.assertFalse(res["valid"])
                self.assertEqual(res["status"], "expired")

    def test_verify_missing_license(self):
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir) / "nonexistent_license.json"
            with patch("app.services.license_service.LICENSE_FILE_PATH", tmppath):
                res = verify_offline_license()
                self.assertFalse(res["valid"])
                self.assertEqual(res["status"], "unactivated")


if __name__ == "__main__":
    unittest.main()
