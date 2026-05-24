"""
recorder.py — Event-triggered MP4 clip recording.

Usage:
    recorder = ClipRecorder()
    recorder.trigger(clip_id, started_at)   # start or extend recording
    recorder.write_frame(frame)             # call on every camera frame
    await recorder.flush()                  # call at shutdown
"""

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2

from config import settings
import database as db

CLIPS_DIR = Path(__file__).parent / "data" / "clips"


class ClipRecorder:
    """
    Writes MP4 clips to data/clips/ when triggered by a detection event.
    Recording extends automatically while new triggers arrive within
    CLIP_POST_SECONDS seconds of the last trigger.
    """

    def __init__(self, fps: int = 15, width: int = 1280, height: int = 720):
        self._fps = fps
        self._width = width
        self._height = height

        self._lock = threading.Lock()
        self._writer: Optional[cv2.VideoWriter] = None
        self._clip_id: Optional[int] = None
        self._filename: Optional[str] = None
        self._last_trigger_ts: float = 0.0
        self._started_at: Optional[str] = None
        self._active = False

        CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def trigger(self, clip_id: Optional[int] = None, started_at: Optional[str] = None) -> None:
        """
        Start or extend an ongoing clip recording.
        Pass clip_id + started_at only on the first trigger for a new event.
        """
        if not settings.RECORDING_ENABLED:
            return

        with self._lock:
            self._last_trigger_ts = time.monotonic()

            if self._active:
                return  # already recording — just refresh the expiry time

            # Start a fresh clip
            ts_str = started_at or datetime.now(timezone.utc).isoformat()
            safe_ts = ts_str[:19].replace(":", "-").replace("T", "_")
            filename = f"clip_{safe_ts}.mp4"
            filepath = CLIPS_DIR / filename

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._writer = cv2.VideoWriter(
                str(filepath), fourcc, self._fps, (self._width, self._height)
            )
            self._filename = filename
            self._started_at = ts_str
            self._clip_id = clip_id
            self._active = True

    def write_frame(self, frame) -> None:
        """Feed the current camera frame into the active recording."""
        if not self._active:
            return

        with self._lock:
            if not self._active:
                return

            # Stop if no new trigger has arrived within CLIP_POST_SECONDS
            idle = time.monotonic() - self._last_trigger_ts
            if idle > settings.CLIP_POST_SECONDS:
                self._stop_locked()
                return

            if self._writer and self._writer.isOpened():
                resized = cv2.resize(frame, (self._width, self._height))
                self._writer.write(resized)

    def flush(self) -> None:
        """Force-stop any active clip (call at shutdown)."""
        with self._lock:
            if self._active:
                self._stop_locked()

    @property
    def is_recording(self) -> bool:
        return self._active

    # ── Internal ──────────────────────────────────────────────────────────────

    def _stop_locked(self) -> None:
        """Must be called with self._lock held."""
        if self._writer:
            self._writer.release()
            self._writer = None

        ended_at = datetime.now(timezone.utc).isoformat()
        filepath = CLIPS_DIR / self._filename if self._filename else None
        size_bytes = filepath.stat().st_size if filepath and filepath.exists() else 0

        if self._clip_id is not None:
            try:
                db.close_clip(self._clip_id, ended_at, size_bytes)
            except Exception as e:
                print(f"[Recorder] DB update failed: {e}")

        print(f"[Recorder] Saved clip: {self._filename} ({size_bytes // 1024} KB)")
        self._active = False
        self._filename = None
        self._clip_id = None
        self._started_at = None
