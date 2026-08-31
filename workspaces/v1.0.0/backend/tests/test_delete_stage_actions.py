import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_delete_stage_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_proj_blocks = await ac.delete("/api/projects/non-existent-id/blocks")
        assert res_proj_blocks.status_code in (404, 200)

        res_page_blocks = await ac.delete("/api/pages/non-existent-id/blocks")
        assert res_page_blocks.status_code in (404, 200)

        res_proj_masks = await ac.delete("/api/projects/non-existent-id/masks")
        assert res_proj_masks.status_code in (404, 200, 400)

        res_page_masks = await ac.delete("/api/pages/non-existent-id/masks")
        assert res_page_masks.status_code in (404, 200, 400)
