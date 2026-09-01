from fastapi.testclient import TestClient
import pytest
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_ocr_endpoint_query_binding_no_422(client):
    response = client.post("/api/pipeline/ocr?page_id=nonexistent_test_page_123")
    assert response.status_code == 404
    assert response.json().get("detail") == "Page not found"

def test_ocr_endpoint_json_body_binding(client):
    response = client.post("/api/pipeline/ocr", json={"page_id": "nonexistent_test_page_123"})
    assert response.status_code == 404
    assert response.json().get("detail") == "Page not found"

def test_font_judge_endpoint_alias(client):
    r1 = client.post("/api/pipeline/font_judge?page_id=nonexistent_test_page_123")
    assert r1.status_code == 404
    assert r1.json().get("detail") == "Page not found"

    r2 = client.post("/api/pipeline/style_judge?page_id=nonexistent_test_page_123")
    assert r2.status_code == 404
    assert r2.json().get("detail") == "Page not found"

def test_typeset_endpoint_alias(client):
    r = client.post("/api/pipeline/typeset?page_id=nonexistent_test_page_123")
    assert r.status_code == 404
    assert r.json().get("detail") == "Page not found"

def test_detect_endpoint_query_and_json(client):
    r1 = client.post("/api/pipeline/detect?page_id=nonexistent_test_page_123")
    assert r1.status_code == 404
    assert r1.json().get("detail") == "Page not found"

    r2 = client.post("/api/pipeline/detect", json={"page_id": "nonexistent_test_page_123"})
    assert r2.status_code == 404
    assert r2.json().get("detail") == "Page not found"

def test_ocr_engines_status(client):
    r = client.get("/api/pipeline/ocr/engines")
    assert r.status_code == 200
    data = r.json()
    assert "engines" in data
