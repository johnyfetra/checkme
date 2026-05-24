"""
detector.py — YOLOv8 object detection wrapper.

Automatically uses the best available device:
  - MPS   → Apple M1/M2/M3 GPU (Metal Performance Shaders)
  - CUDA  → NVIDIA GPU
  - CPU   → fallback

Only detects TARGET_CLASSES to eliminate false positives out-of-the-box
(e.g. birds, cats, dogs, insects are ignored because they are not in the list).
"""

import cv2
import numpy as np
import torch
from ultralytics import YOLO
from config import settings

# COCO class names for the classes we care about
CLASS_NAMES: dict[int, str] = {
    0: "person",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# BGR colors per class
COLORS: dict[int, tuple] = {
    0: (0, 60, 255),    # person  — red
    2: (0, 165, 255),   # car     — orange
    3: (255, 0, 200),   # moto    — magenta
    5: (255, 200, 0),   # bus     — cyan-yellow
    7: (180, 0, 180),   # truck   — purple
}


class Detector:
    def __init__(self) -> None:
        if torch.backends.mps.is_available():
            self.device = "mps"
        elif torch.cuda.is_available():
            self.device = "cuda"
        else:
            self.device = "cpu"

        print(f"[Detector] Loading {settings.MODEL_NAME} on {self.device} …")
        self.model = YOLO(settings.MODEL_NAME)
        self.model_name = settings.MODEL_NAME
        print(f"[Detector] Ready — device={self.device}")

    # ── Public API ────────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> list[dict]:
        """Run inference and return a list of detection dicts."""
        results = self.model(
            frame,
            conf=settings.CONFIDENCE_THRESHOLD,
            classes=settings.TARGET_CLASSES,
            device=self.device,
            verbose=False,
        )
        detections: list[dict] = []
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                detections.append(
                    {
                        "class_id": cls,
                        "class_name": CLASS_NAMES.get(cls, "unknown"),
                        "confidence": round(conf, 3),
                        "bbox": [x1, y1, x2, y2],
                    }
                )
        return detections

    def draw(self, frame: np.ndarray, detections: list[dict]) -> np.ndarray:
        """Draw bounding boxes and labels on a copy of the frame."""
        annotated = frame.copy()
        for det in detections:
            cls = det["class_id"]
            color = COLORS.get(cls, (0, 255, 0))
            x1, y1, x2, y2 = det["bbox"]

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            label = f"{det['class_name']} {det['confidence']:.0%}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, -1)
            cv2.putText(
                annotated, label, (x1 + 3, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
            )
        return annotated
