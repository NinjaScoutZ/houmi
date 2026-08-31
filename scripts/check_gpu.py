"""Quick GPU diagnostic script"""
import sys

try:
    import onnxruntime as ort
    print("ONNX Runtime version:", ort.__version__)
    print("Available providers:", ort.get_available_providers())

    # Test DirectML
    if "DmlExecutionProvider" in ort.get_available_providers():
        print("\n✓ DirectML available")
        try:
            import numpy as np
            # Create simple test session
            test_model = "E:\\houmi\\backend\\models\\inpainting\\lama_manga.onnx"
            session = ort.InferenceSession(test_model, providers=["DmlExecutionProvider"])
            print("✓ DirectML LaMa session created successfully")
            print("  Active providers:", session.get_providers())
        except Exception as e:
            print("✗ DirectML test failed:", e)
            print("  → GPU might be suspended or busy")

    # Test CUDA
    if "CUDAExecutionProvider" in ort.get_available_providers():
        print("\n✓ CUDA available")
    else:
        print("\n✗ CUDA NOT available (LaMa will be VERY slow on CPU)")

except ImportError as e:
    print("Error:", e)
    sys.exit(1)
