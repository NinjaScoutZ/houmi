import unittest
from fastapi.testclient import TestClient
from app.main import app

class TestDiagnosticsRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_diagnostics_health_returns_all_subsystems(self):
        response = self.client.get("/api/diagnostics/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check overall status and timestamp
        self.assertIn("status", data)
        self.assertIn(data["status"], ["online", "degraded", "offline"])
        self.assertIn("timestamp", data)

        # Check all 5 required subsystems
        required_subsystems = ["database", "ocr", "yolo_detector", "psd_cli", "inpainter"]
        for sub in required_subsystems:
            self.assertIn(sub, data, f"Missing subsystem '{sub}' in diagnostics response")
            self.assertIsInstance(data[sub], dict, f"Subsystem '{sub}' payload must be a dict")
            self.assertIn("status", data[sub], f"Subsystem '{sub}' missing 'status'")

        # Detailed check for SQLite database
        db = data["database"]
        self.assertIn("latency_ms", db)
        self.assertIsInstance(db["latency_ms"], (int, float))

        # Detailed check for OCR
        ocr = data["ocr"]
        self.assertIn("message", ocr)

        # Detailed check for YOLO Model
        yolo = data["yolo_detector"]
        self.assertIn("latency_ms", yolo)
        self.assertIn("model_path", yolo)

        # Detailed check for PSD CLI
        psd = data["psd_cli"]
        self.assertIn("executable_path", psd)

        # Detailed check for Inpaint Engine
        inpainter = data["inpainter"]
        self.assertIn("engine", inpainter)
        self.assertIn("providers", inpainter)
        self.assertIsInstance(inpainter["providers"], list)

class TestHardwareDiagnosticsRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_hardware_status_endpoint(self):
        response = self.client.get("/api/diagnostics/hardware")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("cpu_cores", data)
        self.assertIn("ram_total_gb", data)
        self.assertIn("optimal_provider", data)
        self.assertIn("is_optimized", data)
        self.assertIsInstance(data["optimization_suggestions"], list)

    def test_auto_optimize_endpoint(self):
        response = self.client.post("/api/diagnostics/auto-optimize")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("applied", data)
        self.assertIn("hardware_report", data)
        self.assertTrue(data["hardware_report"]["is_optimized"])


if __name__ == "__main__":
    unittest.main()
