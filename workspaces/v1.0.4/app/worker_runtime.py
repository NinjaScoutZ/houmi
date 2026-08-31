"""Dedicated GPU/OCR runtime entrypoint.

Run this as a separate process from the Host API:

    HOUMI_RUNTIME_MODE=worker python -m app.worker_runtime

The process owns the OCR subprocess and GPU model warm-up. It deliberately
does not import ``app.main`` or start a web server, which keeps API restarts
and worker restarts operationally independent.
"""

from __future__ import annotations

import logging
import signal
import threading
import time

from app.config import RUNTIME_MODE
from app.ocr_manager import ocr_manager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("houmi-worker-runtime")
stop_event = threading.Event()


def _preload_models() -> None:
    try:
        from app.services.detector import balloon_detector

        logger.info("Warming up Balloon detector")
        balloon_detector.load_model()
    except Exception:
        logger.exception("Failed to preload Balloon detector")

    try:
        from app.services.inpainter import _get_lama

        logger.info("Warming up LaMa inpainter")
        _get_lama()
    except Exception:
        logger.exception("Failed to preload LaMa inpainter")


def _request_stop(*_args) -> None:
    stop_event.set()


def run() -> None:
    if RUNTIME_MODE != "worker":
        raise RuntimeError("app.worker_runtime requires HOUMI_RUNTIME_MODE=worker")

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    logger.info("Starting dedicated GPU/OCR worker runtime")
    ocr_manager.start_server()
    maintain_thread = threading.Thread(target=ocr_manager.maintain_server, daemon=True)
    maintain_thread.start()
    threading.Thread(target=_preload_models, daemon=True).start()

    try:
        while not stop_event.wait(1.0):
            pass
    finally:
        logger.info("Stopping dedicated GPU/OCR worker runtime")
        ocr_manager.stop_server()


if __name__ == "__main__":
    run()
