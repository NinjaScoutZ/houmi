import pytest
from app.telemetry import (
    get_gpu_memory_status,
    force_garbage_collection,
    check_vram_and_auto_gc,
    pipeline_tracker,
    get_system_health,
)

def test_gpu_memory_telemetry():
    status = get_gpu_memory_status()
    assert "cuda_available" in status
    assert "system_ram_total_mb" in status
    assert status["system_ram_total_mb"] > 0

def test_force_garbage_collection():
    res = force_garbage_collection()
    assert res["gc_collected"] is True
    assert "status_after" in res

def test_auto_vram_gc_logic():
    # If not on high VRAM, should return False
    triggered = check_vram_and_auto_gc(threshold_ratio=0.99)
    assert isinstance(triggered, bool)

def test_pipeline_queue_tracker():
    pipeline_tracker.job_submitted()
    pipeline_tracker.job_started()
    pipeline_tracker.job_completed(latency_ms=120.5)
    
    metrics = pipeline_tracker.get_metrics()
    assert metrics.completed_jobs_total >= 1
    assert metrics.avg_latency_ms >= 0

def test_system_health_endpoint():
    health = get_system_health()
    assert health["status"] in ("healthy", "degraded")
    assert "hardware" in health
    assert "disk" in health
    assert "queue" in health
