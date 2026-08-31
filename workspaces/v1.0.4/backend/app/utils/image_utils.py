import cv2
import numpy as np
from pathlib import Path
from typing import Union, Optional

def cv2_imread_unicode(filename: Union[str, Path], flags: int = cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
    """
    Unicode-safe OpenCV image reader for Windows.
    Handles non-ASCII file paths (Thai, Japanese, Korean, Chinese, etc.) cleanly without returning None.
    """
    path_str = str(filename)
    try:
        with open(path_str, "rb") as f:
            data = np.frombuffer(f.read(), dtype=np.uint8)
        if data.size > 0:
            img = cv2.imdecode(data, flags)
            if img is not None:
                return img
    except Exception:
        pass

    try:
        from PIL import Image
        with Image.open(path_str) as pimg:
            if flags == cv2.IMREAD_GRAYSCALE:
                return np.array(pimg.convert("L"))
            else:
                return cv2.cvtColor(np.array(pimg.convert("RGB")), cv2.COLOR_RGB2BGR)
    except Exception:
        pass

    try:
        data = np.fromfile(path_str, dtype=np.uint8)
        if data.size > 0:
            img = cv2.imdecode(data, flags)
            if img is not None:
                return img
    except Exception:
        pass

    try:
        return cv2.imread(path_str, flags)
    except Exception:
        return None


def cv2_imwrite_unicode(filename: Union[str, Path], img: np.ndarray, params=None) -> bool:
    """
    Unicode-safe OpenCV image writer for Windows.
    Handles non-ASCII file paths (Thai, Japanese, Chinese, etc.) cleanly.
    """
    path_str = str(filename)
    try:
        ext = Path(path_str).suffix.lower() or ".jpg"
        success, buf = cv2.imencode(ext, img, params)
        if success:
            with open(path_str, "wb") as f:
                f.write(buf.tobytes())
            return True
    except Exception:
        pass

    try:
        if params is not None:
            return cv2.imwrite(path_str, img, params)
        return cv2.imwrite(path_str, img)
    except Exception:
        return False
