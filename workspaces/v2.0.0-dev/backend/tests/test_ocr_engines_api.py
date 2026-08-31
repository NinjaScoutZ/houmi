import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.config import (
    get_project_setting,
    get_ocr_engine,
    get_inpaint_engine,
    get_execution_provider_setting,
    get_project_dictionary,
)

class TestOcrEnginesAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_ocr_engines_endpoint(self):
        response = self.client.get("/api/pipeline/ocr/engines")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("engines", data)
        self.assertIsInstance(data["engines"], list)
        
        engine_ids = [eng["id"] for eng in data["engines"]]
        for expected_id in ["gemini", "glm", "deepseek", "paddleocr"]:
            self.assertIn(expected_id, engine_ids)

        for eng in data["engines"]:
            self.assertIn("id", eng)
            self.assertIn("name", eng)
            self.assertIn("category", eng)
            self.assertIn(eng["category"], ["cloud", "local_vlm", "local_offline"])
            self.assertIn("status", eng)
            self.assertIn(eng["status"], ["available", "disabled"])
            self.assertIn("available", eng)
            self.assertIsInstance(eng["available"], bool)
            self.assertIn("reason", eng)

class TestSettingsConsolidationHelpers(unittest.TestCase):
    def test_ocr_engine_fallback(self):
        # 1. Canonical key present
        self.assertEqual(get_ocr_engine({"ocr_engine": "gemini", "ocr_model": "glm"}), "gemini")
        # 2. Legacy key fallback
        self.assertEqual(get_ocr_engine({"ocr_model": "paddleocr"}), "paddleocr")
        # 3. Default fallback
        self.assertEqual(get_ocr_engine({}), "glm")

    def test_inpaint_engine_fallback(self):
        # 1. Canonical key present
        self.assertEqual(get_inpaint_engine({"inpaint_engine": "mat"}), "mat")
        # 2. Active legacy key fallback
        self.assertEqual(get_inpaint_engine({"active_inpaint_engine": "telea"}), "telea")
        # 3. Default method legacy fallback
        self.assertEqual(get_inpaint_engine({"default_image_inpaint_method": "Telea"}), "Telea")
        # 4. Default fallback
        self.assertEqual(get_inpaint_engine({}), "LamaInpaint")

    def test_execution_provider_fallback(self):
        # 1. Canonical key present
        self.assertEqual(get_execution_provider_setting({"execution_provider": "CUDA"}), "CUDA")
        # 2. Legacy key fallback
        self.assertEqual(get_execution_provider_setting({"gpu_execution_provider": "DirectML"}), "DirectML")
        # 3. Default fallback
        self.assertIsNone(get_execution_provider_setting({}))

    def test_project_dictionary_fallback(self):
        # 1. Canonical key present
        self.assertEqual(get_project_dictionary({"project_dictionary": ["Name1", "Name2"]}), ["Name1", "Name2"])
        # 2. Legacy key fallback
        self.assertEqual(get_project_dictionary({"thai_dictionary": ["ThaiName"]}), ["ThaiName"])
        # 3. Default fallback
        self.assertEqual(get_project_dictionary({}), [])

if __name__ == "__main__":
    unittest.main()
