import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.security.tokens import create_access_token
from app.models.all_models import User
from app.database import SessionLocal

@pytest.mark.asyncio
async def test_admin_portal_html_and_metrics():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Test Admin HTML Portal Render
        res_html = await ac.get("/admin")
        assert res_html.status_code == 200
        assert "COMMAND CENTER" in res_html.text
        assert "Overview & Telemetry" in res_html.text

        # 2. Setup mock admin token
        db = SessionLocal()
        admin_user = db.query(User).filter(User.username == "admin").first()
        db.close()
        
        admin_id = admin_user.id if admin_user else "mock-admin-id"
        token = create_access_token(user_id=admin_id, role="admin")

        headers = {"Authorization": f"Bearer {token}"}

        # 3. Test Admin Metrics Endpoint
        res_metrics = await ac.get("/api/admin/system/metrics", headers=headers)
        assert res_metrics.status_code == 200
        metrics = res_metrics.json()
        assert "active_version" in metrics
        assert "gpu" in metrics
        assert "total_users" in metrics

        # 4. Test Connectivity Diagnostic Endpoint
        res_diag = await ac.get("/api/admin/test-connectivity", headers=headers)
        assert res_diag.status_code == 200
        assert "overall_status" in res_diag.json()

        # 5. Test Tools GC
        res_gc = await ac.post("/api/admin/tools/gc", headers=headers)
        assert res_gc.status_code == 200
        assert res_gc.json().get("gc_collected") is True
