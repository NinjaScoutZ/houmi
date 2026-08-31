# Hardware Testing Checklist for Houmi Studio

## Pre-Release Hardware Validation Checklist

### 1. GPU Detection & Auto-Optimization ✅
- [ ] NVIDIA GPU detection (CUDA available)
- [ ] AMD GPU detection (DirectML available)
- [ ] Intel GPU detection (DirectML available)
- [ ] CPU-only fallback detection
- [ ] Auto-Optimize button sets correct provider
- [ ] Hardware diagnostics API returns correct specs

### 2. Execution Provider Testing
**Test on each configuration:**

#### A. NVIDIA CUDA Path
- [ ] CUDA Toolkit installed → CUDAExecutionProvider selected
- [ ] CUDA not installed → fallback to DirectML/CPU
- [ ] LaMa inpainting runs on CUDA (check logs)
- [ ] Balloon detection runs on CUDA
- [ ] Text mask segmentation runs on CUDA
- [ ] No CUDA out-of-memory crashes

#### B. DirectML Path (AMD/Intel/Nvidia)
- [ ] DirectML detected on AMD GPU
- [ ] DirectML detected on Intel GPU
- [ ] DirectML works on Nvidia GPU (fallback)
- [ ] LaMa inpainting runs on DirectML
- [ ] Balloon detection runs on DirectML
- [ ] Performance 3-5x faster than CPU

#### C. CPU Fallback Path
- [ ] CPU mode selected when no GPU available
- [ ] Thread count auto-set (e.g., cpu_cores - 2)
- [ ] No 100% CPU lockup during inference
- [ ] Inpainting completes without crash
- [ ] Slower but stable performance

### 3. Performance Profiles
- [ ] Eco mode works on low-end hardware (4GB RAM)
- [ ] Balanced mode works on mid-range hardware
- [ ] Performance mode works on high-end hardware
- [ ] Switching profiles applies settings correctly

### 4. Memory Management
- [ ] Large images (8000x8000px) process without OOM
- [ ] Multiple concurrent inpaints don't crash
- [ ] RAM usage stays under limit on Eco mode
- [ ] VRAM usage monitored (if available)

### 5. Thread Management
- [ ] Auto thread count calculation works
- [ ] Manual thread override works
- [ ] No system freeze with high thread count
- [ ] CPU usage stays reasonable during idle

### 6. Error Handling & Graceful Degradation
- [ ] Missing CUDA → auto-fallback to DirectML
- [ ] Missing DirectML → auto-fallback to CPU
- [ ] Driver crash → restart with CPU fallback
- [ ] Out-of-memory → error message (not silent crash)

---

## Test Configurations

### Configuration 1: High-End Desktop
- **CPU**: Intel i9-13900K / AMD Ryzen 9 7950X
- **RAM**: 32 GB DDR5
- **GPU**: NVIDIA RTX 4080 (16 GB VRAM)
- **Expected**: CUDA, Performance mode, 5-10x speed

### Configuration 2: Mid-Range Desktop
- **CPU**: Intel i5-12400 / AMD Ryzen 5 5600X
- **RAM**: 16 GB DDR4
- **GPU**: NVIDIA RTX 3060 (12 GB) / AMD RX 6600 (8 GB)
- **Expected**: CUDA/DirectML, Balanced mode, 3-5x speed

### Configuration 3: Budget Desktop
- **CPU**: Intel i3-10100 / AMD Ryzen 3 3300X
- **RAM**: 8 GB DDR4
- **GPU**: GTX 1650 (4 GB) / Intel UHD Graphics 630
- **Expected**: DirectML/CPU, Eco mode, 2-3x speed

### Configuration 4: Laptop (Gaming)
- **CPU**: Intel i7-12700H
- **RAM**: 16 GB DDR4
- **GPU**: NVIDIA RTX 3060 Mobile (6 GB)
- **Expected**: CUDA, Balanced mode, 4-6x speed

### Configuration 5: Laptop (Office)
- **CPU**: Intel i5-1135G7
- **RAM**: 8 GB DDR4
- **GPU**: Intel Iris Xe Graphics
- **Expected**: DirectML, Eco mode, 2-3x speed

### Configuration 6: CPU-Only Server
- **CPU**: Intel Xeon E5-2680 v4 (14 cores)
- **RAM**: 64 GB DDR4
- **GPU**: None
- **Expected**: CPU, custom threads, 1x baseline speed

---

## Automated Test Script

```python
# backend/tests/test_hardware_compatibility.py
import pytest
import onnxruntime as ort
from app.config import get_execution_providers
from app.routes.diagnostics import get_hardware_diagnostics, auto_optimize_hardware

def test_execution_provider_detection():
    """Test that at least one provider is available."""
    providers = ort.get_available_providers()
    assert "CPUExecutionProvider" in providers
    # At least CPU should always work
    active = get_execution_providers()
    assert len(active) > 0

def test_hardware_diagnostics_api():
    """Test hardware diagnostics endpoint."""
    result = get_hardware_diagnostics()
    assert result["status"] == "ok"
    assert "cpu_cores" in result
    assert "ram_total_gb" in result
    assert result["cpu_cores"] > 0

def test_auto_optimize():
    """Test auto-optimization logic."""
    result = auto_optimize_hardware()
    assert result["status"] == "ok"
    assert "applied" in result
    assert result["applied"]["execution_provider"] in ["CUDA", "DirectML", "CPU"]

@pytest.mark.skipif(
    "CUDAExecutionProvider" not in ort.get_available_providers(),
    reason="CUDA not available"
)
def test_cuda_inference():
    """Test CUDA inference on sample model."""
    from app.services.inpainter import LamaONNXInpainter
    from app.config import INPAINT_MODEL_PATH
    
    inpainter = LamaONNXInpainter(str(INPAINT_MODEL_PATH))
    assert "CUDAExecutionProvider" in inpainter.current_providers

@pytest.mark.skipif(
    "DmlExecutionProvider" not in ort.get_available_providers(),
    reason="DirectML not available"
)
def test_directml_inference():
    """Test DirectML inference on sample model."""
    from app.services.inpainter import LamaONNXInpainter
    from app.config import INPAINT_MODEL_PATH
    
    inpainter = LamaONNXInpainter(str(INPAINT_MODEL_PATH))
    assert "DmlExecutionProvider" in inpainter.current_providers

def test_cpu_fallback_always_works():
    """Test CPU fallback works regardless of GPU."""
    providers = get_execution_providers(provider="CPU")
    assert providers == ["CPUExecutionProvider"]
```

---

## Performance Benchmarks

Track these metrics across hardware configs:

| Operation | CPU-only | DirectML | CUDA |
|-----------|----------|----------|------|
| Balloon Detection (1 page) | ~3-5s | ~1-2s | ~0.5-1s |
| Text Mask Generation | ~5-8s | ~2-3s | ~1-2s |
| LaMa Inpainting (1024x1024) | ~15-30s | ~5-10s | ~2-5s |
| OCR (1 page, 10 blocks) | ~2-4s | ~2-4s | ~2-4s |
| Full Pipeline (1 page) | ~25-45s | ~10-20s | ~5-10s |

---

## Known Hardware Issues

### Issue: CUDA out-of-memory on RTX 3060 (12GB)
- **Cause**: Large images + concurrent operations
- **Fix**: Implemented tile-based inpainting, max 2048x2048 tiles
- **Status**: ✅ Fixed in v1.0.0

### Issue: DirectML slow on Intel Iris Xe
- **Cause**: Older DirectML runtime on Windows 10
- **Fix**: Recommend Windows 11, or use CPU mode
- **Status**: ⚠️ User workaround available

### Issue: CPU 100% lockup on 4-core systems
- **Cause**: onnxruntime using all threads
- **Fix**: Auto-limit to `max(2, cpu_cores - 2)`
- **Status**: ✅ Fixed in v0.4.0

---

## Release Validation

Before each release, run:

1. **Automated tests**: `pytest backend/tests/test_hardware_compatibility.py`
2. **Manual smoke test** on at least 3 configurations:
   - 1x CUDA (Nvidia high-end)
   - 1x DirectML (AMD or Intel)
   - 1x CPU-only
3. **Performance regression check**: Compare benchmark times vs. previous release
4. **Hardware diagnostics UI**: Verify Auto-Optimize works and suggestions are correct

---

## Customer Support Quick Reference

### "My GPU isn't working"
1. Check `/diagnostics/hardware` API
2. Verify driver installation (CUDA Toolkit for Nvidia)
3. Try Auto-Optimize button
4. Check Windows version (DirectML needs Win10 1809+)

### "The app is too slow"
1. Check if CPU fallback mode (no GPU detected)
2. Recommend CUDA Toolkit install (Nvidia users)
3. Lower Performance Profile to Eco
4. Reduce concurrent operations

### "Out of memory error"
1. Check RAM (need 8GB minimum)
2. Check GPU VRAM (recommend 6GB+)
3. Enable tile-based inpainting
4. Process fewer pages at once

---

## Continuous Integration

Add to CI pipeline:

```yaml
# .github/workflows/hardware-tests.yml
name: Hardware Compatibility Tests

on: [push, pull_request]

jobs:
  test-cpu-fallback:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run CPU-only tests
        run: pytest backend/tests/test_hardware_compatibility.py -k cpu

  test-gpu-sim:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run GPU simulation tests
        run: pytest backend/tests/test_hardware_compatibility.py
```
