import pytest
from app.config import get_execution_providers, EXECUTION_PROVIDER_MAP
from app.services.detector import BalloonDetector
from app.services.inpainter import LamaONNXInpainter, should_use_lama_inpaint, _get_lama


def test_get_execution_providers_mapping(monkeypatch):
    """Verify execution provider string mapping converts user settings to ORT provider lists."""
    import onnxruntime as ort
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"])
    assert get_execution_providers("CUDA") == ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"]
    assert get_execution_providers("DirectML") == ["DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
    assert get_execution_providers("CPU") == ["CPUExecutionProvider"]
    assert get_execution_providers("cuda") == ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"]
    assert get_execution_providers("directml") == ["DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
    assert get_execution_providers("cpu") == ["CPUExecutionProvider"]
    assert get_execution_providers("CUDAExecutionProvider") == ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"]
    assert get_execution_providers("DmlExecutionProvider") == ["DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
    assert get_execution_providers("CPUExecutionProvider") == ["CPUExecutionProvider"]


def test_detector_execution_provider_setting():
    """Verify BalloonDetector accepts and stores execution provider selection."""
    detector = BalloonDetector()
    detector.load_model(execution_provider="DirectML")
    assert detector.current_providers is not None
    
    # Reloading with CPU switches provider
    detector.load_model(execution_provider="CPU")
    assert detector.current_providers == ["CPUExecutionProvider"]


def test_inpainter_engine_and_provider_selection():
    """Verify should_use_lama_inpaint and _get_lama resolution for R3 inpaint settings."""
    assert should_use_lama_inpaint({"inpaint_engine": "lama_onnx"}) is True
    assert should_use_lama_inpaint({"inpaint_engine": "telea"}) is False
    assert should_use_lama_inpaint({"active_inpaint_engine": "lama_onnx"}) is True
    assert should_use_lama_inpaint({"active_inpaint_engine": "telea"}) is False

    lama = _get_lama(execution_provider="DirectML")
    if lama is not None:
        assert lama.current_providers is not None


def test_detector_multi_model_selection():
    """Verify BalloonDetector correctly resolves model names and defaults to SAO Balloon model."""
    from app.services.detector import get_model_path
    from app.config import BALLOON_MODEL_PATH

    sao_path = get_model_path("เวอร์ชั่นเบต้าเทสแอลฟ่าโอเมก้าแห่ง SAO")
    assert sao_path == BALLOON_MODEL_PATH

    default_path = get_model_path(None)
    assert default_path == BALLOON_MODEL_PATH

    detector = BalloonDetector()
    detector.load_model(execution_provider="CPU", model_name="เวอร์ชั่นเบต้าเทสแอลฟ่าโอเมก้าแห่ง SAO")
    assert detector.current_model_path == str(BALLOON_MODEL_PATH)

