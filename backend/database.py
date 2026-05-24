"""
database.py — SQLite persistence layer.

Tables:
  events  → every detection event (person entered zone, loitering, etc.)
  clips   → recorded MP4 video clips linked to events
  zones   → virtual detection zones defined by the user
  stats   → hourly aggregated counters for the dashboard

Designed to be lightweight (no ORM) — raw sqlite3 for zero extra dependencies.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "data" / "checkme.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # write-ahead log for concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# Module-level connection pool (one connection per thread via threading.local)
_local = threading.local()


def get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _connect()
    return _local.conn


@contextmanager
def transaction():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,          -- ISO-8601 UTC
    camera_id   TEXT    NOT NULL DEFAULT 'cam0',
    class_name  TEXT    NOT NULL,          -- person / car / etc.
    confidence  REAL    NOT NULL,
    track_id    INTEGER,                   -- ByteTrack ID (NULL if tracking off)
    zone_name   TEXT,                      -- zone that was triggered (NULL = global)
    event_type  TEXT    NOT NULL DEFAULT 'detection',
    -- event_type: detection | intrusion | loitering | line_cross | tamper
    duration_s  REAL,                      -- seconds object was present (loitering)
    snapshot_b64 TEXT,                     -- base64 JPEG thumbnail
    clip_id     INTEGER REFERENCES clips(id)
);

CREATE TABLE IF NOT EXISTS clips (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT    NOT NULL UNIQUE,   -- relative to data/clips/
    started_at  TEXT    NOT NULL,
    ended_at    TEXT,
    camera_id   TEXT    NOT NULL DEFAULT 'cam0',
    trigger_event_id INTEGER,
    size_bytes  INTEGER
);

CREATE TABLE IF NOT EXISTS zones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id   TEXT    NOT NULL DEFAULT 'cam0',
    name        TEXT    NOT NULL,
    type        TEXT    NOT NULL DEFAULT 'polygon',
    -- type: polygon | line
    points_json TEXT    NOT NULL,          -- JSON array [[x,y], ...]
    enabled     INTEGER NOT NULL DEFAULT 1,
    alert_classes TEXT  NOT NULL DEFAULT 'person',
    loiter_seconds REAL NOT NULL DEFAULT 10.0
);

CREATE TABLE IF NOT EXISTS stats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hour        TEXT    NOT NULL,          -- YYYY-MM-DDTHH (UTC)
    camera_id   TEXT    NOT NULL DEFAULT 'cam0',
    class_name  TEXT    NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(hour, camera_id, class_name)
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_camera    ON events(camera_id);
CREATE INDEX IF NOT EXISTS idx_stats_hour       ON stats(hour);
"""


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()


# ── Write helpers ─────────────────────────────────────────────────────────────

def insert_event(
    class_name: str,
    confidence: float,
    event_type: str = "detection",
    track_id: Optional[int] = None,
    zone_name: Optional[str] = None,
    duration_s: Optional[float] = None,
    snapshot_b64: Optional[str] = None,
    clip_id: Optional[int] = None,
    camera_id: str = "cam0",
) -> int:
    ts = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        cur = conn.execute(
            """INSERT INTO events
               (timestamp, camera_id, class_name, confidence, track_id,
                zone_name, event_type, duration_s, snapshot_b64, clip_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (ts, camera_id, class_name, confidence, track_id,
             zone_name, event_type, duration_s, snapshot_b64, clip_id),
        )
        event_id = cur.lastrowid

    # Update hourly stats
    hour = ts[:13]  # "YYYY-MM-DDTHH"
    with transaction() as conn:
        conn.execute(
            """INSERT INTO stats (hour, camera_id, class_name, count)
               VALUES (?,?,?,1)
               ON CONFLICT(hour, camera_id, class_name)
               DO UPDATE SET count = count + 1""",
            (hour, camera_id, class_name),
        )
    return event_id


def insert_clip(filename: str, started_at: str, camera_id: str = "cam0") -> int:
    with transaction() as conn:
        cur = conn.execute(
            "INSERT INTO clips (filename, started_at, camera_id) VALUES (?,?,?)",
            (filename, started_at, camera_id),
        )
        return cur.lastrowid


def close_clip(clip_id: int, ended_at: str, size_bytes: int) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE clips SET ended_at=?, size_bytes=? WHERE id=?",
            (ended_at, size_bytes, clip_id),
        )


# ── Read helpers ──────────────────────────────────────────────────────────────

def get_events(limit: int = 100, camera_id: str = "cam0") -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM events WHERE camera_id=?
           ORDER BY timestamp DESC LIMIT ?""",
        (camera_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_clips(limit: int = 50, camera_id: str = "cam0") -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM clips WHERE camera_id=?
           ORDER BY started_at DESC LIMIT ?""",
        (camera_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_zones(camera_id: str = "cam0") -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM zones WHERE camera_id=? AND enabled=1",
        (camera_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_zone(name: str, points_json: str, zone_type: str = "polygon",
              alert_classes: str = "person", loiter_seconds: float = 10.0,
              camera_id: str = "cam0") -> int:
    with transaction() as conn:
        cur = conn.execute(
            """INSERT INTO zones (camera_id, name, type, points_json,
                                  alert_classes, loiter_seconds)
               VALUES (?,?,?,?,?,?)""",
            (camera_id, name, zone_type, points_json, alert_classes, loiter_seconds),
        )
        return cur.lastrowid


def get_stats_last_24h(camera_id: str = "cam0") -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT hour, class_name, count FROM stats
           WHERE camera_id=?
             AND hour >= datetime('now', '-24 hours', 'start of hour')
           ORDER BY hour ASC""",
        (camera_id,),
    ).fetchall()
    return [dict(r) for r in rows]
