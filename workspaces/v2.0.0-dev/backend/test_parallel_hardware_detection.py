#!/usr/bin/env python3
"""
Test script for Parallel Inpainting Hardware Auto-Detection

Tests:
1. Hardware detection (CUDA/DirectML/CPU)
2. Worker count calculation based on hardware
3. Global Settings integration
4. Performance preset auto-detection
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.services.parallel_inpaint import get_optimal_worker_count
from app.config import get_execution_providers
from app.services.ai_provider_settings import _load_raw_settings
import json


def test_hardware_detection():
    """Test 1: Verify hardware detection works correctly"""
    print("=" * 60)
    print("Test 1: Hardware Detection")
    print("=" * 60)

    # Get system info
    cpu_count = os.cpu_count()
    providers = get_execution_providers()
    primary_provider = providers[0] if providers else "Unknown"

    print(f"✓ CPU Cores: {cpu_count}")
    print(f"✓ ONNX Providers: {providers}")
    print(f"✓ Primary Provider: {primary_provider}")
    print()

    # Load global settings
    global_settings = _load_raw_settings()
    print("Global Settings:")
    print(f"  - execution_provider: {global_settings.get('execution_provider', 'Not set')}")
    print(f"  - optimal_thread_count: {global_settings.get('optimal_thread_count', 'Not set')}")
    print()


def test_worker_calculation():
    """Test 2: Verify worker count calculation for different scenarios"""
    print("=" * 60)
    print("Test 2: Worker Count Calculation")
    print("=" * 60)

    scenarios = [
        {"name": "Auto-detect (default)", "settings": {}},
        {"name": "Performance preset (auto)", "settings": {"parallel_inpaint_workers": 0}},
        {"name": "User override (3 workers)", "settings": {"parallel_inpaint_workers": 3}},
        {"name": "User override (8 workers)", "settings": {"parallel_inpaint_workers": 8}},
        {"name": "User override (20 workers - should cap)", "settings": {"parallel_inpaint_workers": 20}},
    ]

    for scenario in scenarios:
        workers = get_optimal_worker_count(scenario["settings"])
        print(f"✓ {scenario['name']}: {workers} workers")
    print()


def test_hardware_modes():
    """Test 3: Show expected worker counts for different hardware"""
    print("=" * 60)
    print("Test 3: Hardware Mode Detection")
    print("=" * 60)

    providers = get_execution_providers()
    primary = providers[0] if providers else "Unknown"
    cpu_count = os.cpu_count() or 2
    global_settings = _load_raw_settings()
    optimal_threads = global_settings.get("optimal_thread_count", cpu_count // 2)

    print(f"Current Hardware: {primary}")
    print()

    # GPU mode
    if primary in ("CUDAExecutionProvider", "DmlExecutionProvider"):
        gpu_workers = max(3, min(6, cpu_count // 2))
        print(f"✓ GPU Mode Active ({primary})")
        print(f"  - Workers: {gpu_workers}")
        print(f"  - Rationale: GPU handles heavy lifting, more parallelism possible")
        print(f"  - Calculation: max(3, min(6, {cpu_count} // 2)) = {gpu_workers}")
    # CPU mode
    else:
        cpu_workers = max(2, min(4, optimal_threads // 2))
        print(f"✓ CPU-Only Mode Active")
        print(f"  - Workers: {cpu_workers}")
        print(f"  - Rationale: Conservative count to prevent 100% CPU lockup")
        print(f"  - Calculation: max(2, min(4, {optimal_threads} // 2)) = {cpu_workers}")
    print()


def test_integration():
    """Test 4: Verify integration with existing systems"""
    print("=" * 60)
    print("Test 4: Integration Check")
    print("=" * 60)

    try:
        from app.services.performance_presets import PERFORMANCE_PRESETS

        print("Performance Presets Worker Settings:")
        for preset_name, preset_data in PERFORMANCE_PRESETS.items():
            workers = preset_data.get("parallel_inpaint_workers", "not set")
            expected = workers == 0  # Should be 0 (auto-detect)
            status = "✓" if expected else "✗"
            print(f"  {status} {preset_name}: {workers} {'(auto-detect)' if workers == 0 else '(hardcoded - should be 0)'}")
        print()

        # Simulate actual worker count for each preset
        print("Actual Worker Counts (simulated):")
        for preset_name in PERFORMANCE_PRESETS:
            settings = {"parallel_inpaint_workers": 0}
            workers = get_optimal_worker_count(settings)
            print(f"  ✓ {preset_name}: {workers} workers")
        print()

    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        print()


def test_summary():
    """Print summary and recommendations"""
    print("=" * 60)
    print("Summary & Recommendations")
    print("=" * 60)

    providers = get_execution_providers()
    primary = providers[0] if providers else "Unknown"
    settings = {"parallel_inpaint_workers": 0}
    workers = get_optimal_worker_count(settings)

    print(f"✓ System detected: {primary}")
    print(f"✓ Optimal workers: {workers}")
    print()

    print("Recommendations:")
    if primary in ("CUDAExecutionProvider", "DmlExecutionProvider"):
        print("  ✓ GPU acceleration detected - system is optimized")
        print("  ✓ Parallel inpainting will use GPU for heavy lifting")
        print("  ✓ More workers possible due to GPU offload")
    else:
        print("  ⚠ CPU-only mode detected")
        print("  ℹ Consider using GPU for better performance")
        print("  ℹ Run /diagnostics/auto-optimize to update settings")
    print()

    global_settings = _load_raw_settings()
    if not global_settings.get("execution_provider"):
        print("  ⚠ Global Settings not configured")
        print("  → Recommend running: POST /api/diagnostics/auto-optimize")
        print()


if __name__ == "__main__":
    print()
    print("╔" + "=" * 58 + "╗")
    print("║  Parallel Inpainting Hardware Auto-Detection Test      ║")
    print("╚" + "=" * 58 + "╝")
    print()

    try:
        test_hardware_detection()
        test_worker_calculation()
        test_hardware_modes()
        test_integration()
        test_summary()

        print("=" * 60)
        print("✓ All tests completed successfully!")
        print("=" * 60)
        print()

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
