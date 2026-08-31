import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.services.typesetting.rules_manager import (
    get_typesetting_rules,
    save_typesetting_rules,
    reset_typesetting_rules_to_default,
    simulate_rules_evaluation,
    DEFAULT_TYPESETTING_RULES,
)

def test_rules_manager_operations():
    # 1. Reset rules
    rules = reset_typesetting_rules_to_default()
    assert "ก็" in rules["forward_glue_particles"]
    assert "นะ" in rules["backward_glue_particles"]
    assert "นายน้อยฉางเกอ" in rules["custom_compound_words"]
    
    # 2. Add rule
    rules["forward_glue_particles"].append("จึ่ง")
    save_typesetting_rules(rules)
    
    updated = get_typesetting_rules()
    assert "จึ่ง" in updated["forward_glue_particles"]
    
    # 3. Test simulation with word "ก็"
    res = simulate_rules_evaluation("อะไรนะ!? สูงกว่ามหาบุรุษก็มีชื่อบนทำเนียบได้แล้วรึ?", target_lines=3)
    assert any("ก็" in tok for tok in res.tokens)

@pytest.mark.asyncio
async def test_rules_api_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/typesetting/rules")
        assert response.status_code == 200
        data = response.json()
        assert "forward_glue_particles" in data
        assert "backward_glue_particles" in data
        assert "custom_compound_words" in data
