"""
zones.py — Virtual detection zones and intelligent rule engine.

Zone types:
  polygon  → alert when object CENTER is inside the polygon (intrusion zone)
  line     → alert when object crosses the line (tripwire / line crossing)

Rule engine per zone:
  - Only trigger for configured classes (e.g. "person" only)
  - Loitering: alert if track stays in zone > loiter_seconds
  - Line cross: alert once per track crossing direction

All zone definitions are loaded from the SQLite DB at startup and
can be reloaded live without restarting the server.
"""

import json
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
import cv2


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Zone:
    id: int
    name: str
    type: str                          # "polygon" | "line"
    points: list                       # [[x,y], ...] normalized 0-1
    alert_classes: list[str]
    loiter_seconds: float = 10.0
    camera_id: str = "cam0"


@dataclass
class TrackState:
    """Per-track state inside a zone."""
    first_seen: float = field(default_factory=time.monotonic)
    alerted_loiter: bool = False
    last_side: Optional[int] = None    # for line-cross: +1 or -1


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _center(bbox: list) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _point_in_polygon(px: float, py: float, poly: list) -> bool:
    """Ray-casting algorithm (points in 0–1 normalized space)."""
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _line_side(px: float, py: float, p1: list, p2: list) -> int:
    """Returns +1 or -1 based on which side of line [p1→p2] point (px,py) is on."""
    val = (p2[0] - p1[0]) * (py - p1[1]) - (p2[1] - p1[1]) * (px - p1[0])
    return 1 if val >= 0 else -1


def _denormalize_points(points: list, w: int, h: int) -> list:
    """Convert normalized [0-1] points to pixel coords for drawing."""
    return [[int(p[0] * w), int(p[1] * h)] for p in points]


# ── Zone engine ───────────────────────────────────────────────────────────────

class ZoneEngine:
    def __init__(self) -> None:
        self._zones: list[Zone] = []
        # {zone_id: {track_id: TrackState}}
        self._track_states: dict[int, dict[int, TrackState]] = {}

    def load_zones(self, zone_rows: list[dict]) -> None:
        """Load zones from DB rows (call at startup + on config change)."""
        self._zones = []
        for row in zone_rows:
            try:
                points = json.loads(row["points_json"])
                classes = [c.strip() for c in row["alert_classes"].split(",")]
                self._zones.append(Zone(
                    id=row["id"],
                    name=row["name"],
                    type=row["type"],
                    points=points,
                    alert_classes=classes,
                    loiter_seconds=row["loiter_seconds"],
                    camera_id=row.get("camera_id", "cam0"),
                ))
                self._track_states.setdefault(row["id"], {})
            except Exception:
                pass

    def add_default_zones(self, frame_w: int, frame_h: int) -> None:
        """Add a full-frame zone if no zones are defined (safe default)."""
        if not self._zones:
            self._zones.append(Zone(
                id=0,
                name="Zone globale",
                type="polygon",
                points=[[0, 0], [1, 0], [1, 1], [0, 1]],
                alert_classes=["person", "car", "motorcycle", "bus", "truck"],
                loiter_seconds=5.0,
            ))
            self._track_states[0] = {}

    def evaluate(self, tracked_detections: list[dict], frame_w: int, frame_h: int) -> list[dict]:
        """
        Evaluate tracked detections against all zones.
        Returns a list of triggered rule events:
          {zone_name, track_id, class_name, event_type, confidence, bbox, duration_s}
        """
        triggered: list[dict] = []
        now = time.monotonic()

        # Collect active track IDs this frame
        active_ids = {d.get("track_id") for d in tracked_detections if d.get("track_id")}

        for zone in self._zones:
            zid = zone.id
            states = self._track_states.setdefault(zid, {})

            # Clean up stale track states
            for tid in list(states):
                if tid not in active_ids:
                    del states[tid]

            for det in tracked_detections:
                tid = det.get("track_id")
                if tid is None:
                    continue
                if det["class_name"] not in zone.alert_classes:
                    continue

                cx, cy = _center(det["bbox"])
                # Normalize to 0-1
                ncx, ncy = cx / frame_w, cy / frame_h

                if zone.type == "polygon":
                    inside = _point_in_polygon(ncx, ncy, zone.points)

                    if inside:
                        if tid not in states:
                            states[tid] = TrackState()
                        state = states[tid]
                        duration = now - state.first_seen

                        # Loitering alert
                        if duration >= zone.loiter_seconds and not state.alerted_loiter:
                            state.alerted_loiter = True
                            triggered.append({
                                "zone_name": zone.name,
                                "track_id": tid,
                                "class_name": det["class_name"],
                                "event_type": "loitering" if duration > 5 else "intrusion",
                                "confidence": det["confidence"],
                                "bbox": det["bbox"],
                                "duration_s": round(duration, 1),
                            })
                    else:
                        states.pop(tid, None)

                elif zone.type == "line" and len(zone.points) >= 2:
                    side = _line_side(ncx, ncy, zone.points[0], zone.points[1])
                    if tid not in states:
                        states[tid] = TrackState(last_side=side)
                    else:
                        prev_side = states[tid].last_side
                        if prev_side is not None and prev_side != side:
                            triggered.append({
                                "zone_name": zone.name,
                                "track_id": tid,
                                "class_name": det["class_name"],
                                "event_type": "line_cross",
                                "confidence": det["confidence"],
                                "bbox": det["bbox"],
                                "duration_s": None,
                            })
                        states[tid].last_side = side

        return triggered

    def draw_zones(self, frame: np.ndarray) -> np.ndarray:
        """Overlay zone polygons/lines on the frame."""
        h, w = frame.shape[:2]
        overlay = frame.copy()

        for zone in self._zones:
            pts = _denormalize_points(zone.points, w, h)
            color = (0, 200, 255) if zone.type == "polygon" else (0, 100, 255)

            if zone.type == "polygon" and len(pts) >= 3:
                arr = np.array(pts, dtype=np.int32)
                cv2.fillPoly(overlay, [arr], (*color, 40))
                cv2.polylines(frame, [arr], True, color, 2)
            elif zone.type == "line" and len(pts) >= 2:
                cv2.line(frame, tuple(pts[0]), tuple(pts[1]), color, 3)
                cv2.circle(frame, tuple(pts[0]), 5, color, -1)
                cv2.circle(frame, tuple(pts[1]), 5, color, -1)

            # Zone label
            label_pt = pts[0] if pts else (10, 10)
            cv2.putText(frame, zone.name, (label_pt[0], label_pt[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # Blend overlay for polygon fill transparency
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
        return frame

    @property
    def zones(self) -> list[Zone]:
        return self._zones
