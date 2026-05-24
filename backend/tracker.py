"""
tracker.py — Lightweight multi-object tracker (SORT algorithm).

Why not ByteTrack/DeepSORT?
  Both require scipy + numpy already installed.
  This is a clean SORT implementation with no extra deps.
  Gives each detected object a stable track_id across frames —
  the key ingredient for loitering detection and behavior analysis.

How it works:
  1. Detections arrive as bounding boxes.
  2. Existing tracks are predicted forward using a Kalman filter.
  3. Hungarian algorithm matches predictions to detections (IoU cost).
  4. Unmatched detections → new tracks.
  5. Tracks not seen for MAX_AGE frames → removed.
"""

import numpy as np
from typing import Optional


# ── Kalman filter for a single track ─────────────────────────────────────────

class KalmanBox:
    """
    State vector: [x, y, w, h, vx, vy, vw, vh]
    Observation:  [x, y, w, h]
    (x, y) = center; w, h = width, height
    """
    _count = 0

    def __init__(self, bbox: list[float]) -> None:
        x, y, w, h = self._xyxy_to_xywh(bbox)
        self.state = np.array([x, y, w, h, 0, 0, 0, 0], dtype=float)

        # Transition matrix (constant velocity)
        self.F = np.eye(8)
        for i in range(4):
            self.F[i, i + 4] = 1.0

        # Measurement matrix
        self.H = np.eye(4, 8)

        # Process noise
        self.Q = np.eye(8) * 0.01
        self.Q[4:, 4:] *= 10.0

        # Measurement noise
        self.R = np.eye(4) * 1.0

        # Covariance
        self.P = np.eye(8) * 10.0
        self.P[4:, 4:] *= 100.0

        KalmanBox._count += 1
        self.id = KalmanBox._count
        self.hits = 1
        self.no_hit = 0
        self.age = 0

    def predict(self) -> np.ndarray:
        self.state = self.F @ self.state
        self.P = self.F @ self.P @ self.F.T + self.Q
        self.age += 1
        self.no_hit += 1
        return self._xywh_to_xyxy(self.state[:4])

    def update(self, bbox: list[float]) -> None:
        z = np.array(self._xyxy_to_xywh(bbox))
        y = z - self.H @ self.state
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.state = self.state + K @ y
        self.P = (np.eye(8) - K @ self.H) @ self.P
        self.hits += 1
        self.no_hit = 0

    def get_bbox(self) -> list[float]:
        return self._xywh_to_xyxy(self.state[:4])

    @staticmethod
    def _xyxy_to_xywh(b: list[float]) -> list[float]:
        x1, y1, x2, y2 = b
        return [(x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1]

    @staticmethod
    def _xywh_to_xyxy(b) -> list[float]:
        x, y, w, h = b
        return [x - w / 2, y - h / 2, x + w / 2, y + h / 2]


# ── IoU + Hungarian matching ──────────────────────────────────────────────────

def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def _hungarian(cost: np.ndarray):
    """Simple greedy matching (sufficient for typical camera scenes <30 objects)."""
    matched_t, matched_d = [], []
    used_d = set()
    for t_idx in range(cost.shape[0]):
        best_d = -1
        best_v = -1.0
        for d_idx in range(cost.shape[1]):
            if d_idx not in used_d and cost[t_idx, d_idx] > best_v:
                best_v = cost[t_idx, d_idx]
                best_d = d_idx
        if best_d >= 0 and best_v > 0:
            matched_t.append(t_idx)
            matched_d.append(best_d)
            used_d.add(best_d)
    return matched_t, matched_d


# ── Public tracker ────────────────────────────────────────────────────────────

class Tracker:
    """
    Usage:
        tracker = Tracker()
        tracked = tracker.update(detections)
        # tracked: list of dicts with track_id added
    """

    def __init__(self, iou_threshold: float = 0.3, max_age: int = 10, min_hits: int = 2):
        self.iou_threshold = iou_threshold
        self.max_age = max_age      # frames before dropping an unmatched track
        self.min_hits = min_hits    # min hits before a track is considered confirmed
        self._tracks: list[KalmanBox] = []

    def update(self, detections: list[dict]) -> list[dict]:
        """
        detections: list of dicts with 'bbox': [x1,y1,x2,y2]
        Returns same dicts enriched with 'track_id' (int).
        """
        # Predict all existing tracks
        predicted = [t.predict() for t in self._tracks]

        results: list[dict] = []

        if not detections:
            self._tracks = [t for t in self._tracks if t.no_hit <= self.max_age]
            return results

        det_boxes = [d["bbox"] for d in detections]

        if predicted:
            # Build IoU cost matrix  [n_tracks × n_detections]
            cost = np.zeros((len(predicted), len(det_boxes)))
            for ti, tp in enumerate(predicted):
                for di, db in enumerate(det_boxes):
                    cost[ti, di] = _iou(tp, db)

            matched_t, matched_d = _hungarian(cost)

            # Filter by threshold
            valid_pairs = [
                (ti, di) for ti, di in zip(matched_t, matched_d)
                if cost[ti, di] >= self.iou_threshold
            ]
        else:
            valid_pairs = []

        matched_det_indices = {di for _, di in valid_pairs}

        # Update matched tracks
        for ti, di in valid_pairs:
            self._tracks[ti].update(det_boxes[di])
            track = self._tracks[ti]
            if track.hits >= self.min_hits:
                det = dict(detections[di])
                det["track_id"] = track.id
                results.append(det)

        # Create new tracks for unmatched detections
        for di, det in enumerate(detections):
            if di not in matched_det_indices:
                new_track = KalmanBox(det["bbox"])
                self._tracks.append(new_track)
                if new_track.hits >= self.min_hits:
                    d = dict(det)
                    d["track_id"] = new_track.id
                    results.append(d)

        # Remove stale tracks
        self._tracks = [t for t in self._tracks if t.no_hit <= self.max_age]

        return results
