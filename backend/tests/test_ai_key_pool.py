import pytest
from app.services.ai_key_pool import AIKeyPool

def test_key_pool_round_robin_and_failover():
    pool = AIKeyPool(cooldown_seconds=0.5, max_consecutive_failures=2)
    keys = ["AIzaSyKey1_AAAA", "AIzaSyKey2_BBBB", "AIzaSyKey3_CCCC"]
    pool.register_keys("gemini", keys)

    # 1. Round-robin rotation
    k1 = pool.acquire_key("gemini")
    k2 = pool.acquire_key("gemini")
    k3 = pool.acquire_key("gemini")
    k4 = pool.acquire_key("gemini")

    assert k1 == keys[0]
    assert k2 == keys[1]
    assert k3 == keys[2]
    assert k4 == keys[0]

    # 2. Rate limit key 1
    pool.report_failure("gemini", keys[0], is_rate_limit=True)
    
    # Next acquire should skip key 1 and give key 2
    next_k = pool.acquire_key("gemini")
    assert next_k == keys[1]

    # Status check
    status = pool.get_pool_status()
    assert status["gemini"]["total_keys"] == 3
    assert status["gemini"]["active_keys"] == 2
    assert status["gemini"]["cooldown_keys"] == 1
