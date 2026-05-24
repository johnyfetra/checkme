"""
alerts.py — Alert debounce and history management.

Debounce logic:
  1. A detection must appear in ALERT_TRIGGER_FRAMES consecutive frames
     before an alert fires (avoids single-frame false positives).
  2. Once an alert fires for a class, a ALERT_COOLDOWN_SECONDS cooldown
     prevents re-alerting for the same class immediately.
  3. Alerts are stored in a bounded deque (MAX_ALERTS_HISTORY).
"""

import base64
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np

from config import settings


class Alert:
    def __init__(
        self,
        class_name: str,
        confidence: float,
        snapshot: Optional[np.ndarray] = None,
    ) -> None:
        self.id = int(time.time() * 1000)
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.class_name = class_name
        self.confidence = confidence
        self.snapshot_b64: Optional[str] = None

        if snapshot is not None:
            ok, buf = cv2.imencode(".jpg", snapshot, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ok:
                self.snapshot_b64 = base64.b64encode(buf).decode()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "snapshot": self.snapshot_b64,
        }


class AlertManager:
    def __init__(self) -> None:
        self._history: deque[Alert] = deque(maxlen=settings.MAX_ALERTS_HISTORY)
        self._last_alert_at: dict[str, float] = {}
        self._consecutive: dict[str, int] = {}
        self.total_alerts: int = 0

    def process(self, detections: list[dict], frame: np.ndarray) -> list[Alert]:
        """
        Evaluate detections against debounce rules.
        Returns a (possibly empty) list of newly triggered Alert objects.
        """
        current_classes = {d["class_name"] for d in detections}

        # Reset consecutive counters for classes that disappeared
        for cls in list(self._consecutive):
            if cls not in current_classes:
                self._consecutive[cls] = 0

        new_alerts: list[Alert] = []
        for det in detections:
            cls = det["class_name"]
            self._consecutive[cls] = self._consecutive.get(cls, 0) + 1

            now = time.monotonic()
            last = self._last_alert_at.get(cls, 0.0)
            cooldown_ok = (now - last) >= settings.ALERT_COOLDOWN_SECONDS

            if self._consecutive[cls] >= settings.ALERT_TRIGGER_FRAMES and cooldown_ok:
                alert = Alert(cls, det["confidence"], frame)
                self._history.appendleft(alert)
                self._last_alert_at[cls] = now
                self._consecutive[cls] = 0
                self.total_alerts += 1
                new_alerts.append(alert)

        return new_alerts

    def get_history(self) -> list[dict]:
        return [a.to_dict() for a in self._history]
