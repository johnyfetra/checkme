"""
motion.py — Fast motion pre-filter using OpenCV MOG2 background subtraction.

Why this exists:
  Running YOLOv8 on EVERY frame is wasteful when nothing moves.
  MOG2 is a cheap CPU-based filter: only frames with significant motion
  are passed to the AI, saving ~70–90% of inference calls in static scenes.

Handles:
  - Shadows (MOG2 detectShadows=True + threshold removes them)
  - Small insects / rain drops (MOTION_MIN_AREA threshold)
  - Camera noise (morphological open removes tiny blobs)
"""

import cv2
import numpy as np
from config import settings


class MotionDetector:
    def __init__(self) -> None:
        # MOG2 is robust to slow lighting changes and shadows
        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=50,
            detectShadows=True,   # marks shadows as gray (127), not white
        )
        # Structuring element for morphological noise removal
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def detect(self, frame: np.ndarray) -> tuple[bool, np.ndarray]:
        """
        Returns (has_significant_motion, binary_mask).

        has_significant_motion=True  → pass frame to YOLO
        has_significant_motion=False → skip YOLO, save GPU time
        """
        fg = self._bg.apply(frame)

        # Remove shadows: MOG2 marks shadows as 127, real foreground as 255
        _, fg = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)

        # Remove tiny noise blobs (insects, rain pixels, compression artefacts)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, self._kernel)
        fg = cv2.morphologyEx(fg, cv2.MORPH_DILATE, self._kernel, iterations=2)

        contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        max_area = max((cv2.contourArea(c) for c in contours), default=0)

        return max_area > settings.MOTION_MIN_AREA, fg
