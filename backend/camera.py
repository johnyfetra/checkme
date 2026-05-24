"""
camera.py — Thread-safe camera capture.

A background thread reads frames from the camera continuously so that
the latest frame is always available without blocking the event loop.
Supports both the built-in MacBook camera (index=0) and RTSP streams.
"""

import os
import threading
import time
import cv2
import numpy as np
from typing import Optional, Union
from config import settings

# Supprime les logs OBSENSOR (depth-sensors) d'OpenCV — bruit sans utilité
os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")


class Camera:
    def __init__(self, source: Union[int, str] = settings.CAMERA_SOURCE):
        self._source = source
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        # AVFoundation = backend natif macOS (plus rapide, supporte Continuity Camera)
        backend = cv2.CAP_AVFOUNDATION if isinstance(self._source, int) else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(self._source, backend)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera source '{self._source}'. "
                "Check that the MacBook camera is not used by another app."
            )
        # Request resolution & FPS (best-effort — camera may cap these)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.CAMERA_HEIGHT)
        self._cap.set(cv2.CAP_PROP_FPS, settings.CAMERA_FPS)

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="CameraThread")
        self._thread.start()

    def read_frame(self) -> Optional[np.ndarray]:
        """Return a copy of the latest captured frame (thread-safe)."""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap:
            self._cap.release()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _capture_loop(self) -> None:
        while self._running:
            ret, frame = self._cap.read()
            if ret and frame is not None:
                with self._lock:
                    self._frame = frame
            else:
                # Brief pause before retrying (handles transient read errors)
                time.sleep(0.05)
