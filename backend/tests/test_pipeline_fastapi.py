import sys
from pathlib import Path
sys.path.insert(0, str(Path(r"E:\houmi\backend").resolve()))

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_api_health():
    res = client.get("/api/system/check-update")
    assert res.status_code == 200
    print("Health check: PASS")

def test_api_projects():
    res = client.get("/api/projects")
    assert res.status_code == 200
    print(f"Projects count: {len(res.json())} - PASS")

if __name__ == "__main__":
    test_api_health()
    test_api_projects()
    print("ALL IN-PROCESS FASTAPI PIPELINE TESTS PASSED!")
