import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the backend/ directory (works wherever the process is launched from)
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path)


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, default))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, default))


def _str(key: str, default: str) -> str:
    return os.getenv(key, default)


def _list_int(key: str, default: list) -> list:
    raw = os.getenv(key)
    if raw:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    return default


def _list_str(key: str, default: list) -> list:
    raw = os.getenv(key)
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return default


def _camera_source():
    """
    Resolve camera source from env in priority order:
      1. CAMERA_SOURCE — int index OR URL string (rtsp://, http://)
      2. CAMERA_INDEX  — legacy int-only fallback
    """
    from typing import Union
    raw = os.getenv("CAMERA_SOURCE")
    if raw:
        raw = raw.strip()
        # RTSP / HTTP stream URL
        if raw.startswith(("rtsp://", "rtsps://", "http://", "https://")):
            return raw
        # Numeric index (MacBook built-in = 0, Continuity Camera = 1 or 2)
        try:
            return int(raw)
        except ValueError:
            return raw  # unknown string — pass as-is to OpenCV
    return _int("CAMERA_INDEX", 0)


class _Settings:
    # ── Camera ────────────────────────────────────────────────────────────────
    CAMERA_SOURCE            = _camera_source()   # int | str
    CAMERA_INDEX: int        = _int("CAMERA_INDEX", 0)  # kept for compat
    CAMERA_WIDTH: int        = _int("CAMERA_WIDTH", 1280)
    CAMERA_HEIGHT: int       = _int("CAMERA_HEIGHT", 720)
    CAMERA_FPS: int          = _int("CAMERA_FPS", 30)

    # ── AI Detection ──────────────────────────────────────────────────────────
    MODEL_NAME: str          = _str("MODEL_NAME", "yolov8n.pt")
    CONFIDENCE_THRESHOLD: float = _float("CONFIDENCE_THRESHOLD", 0.50)
    # 0=person  2=car  3=motorcycle  5=bus  7=truck
    TARGET_CLASSES: list     = _list_int("TARGET_CLASSES", [0, 2, 3, 5, 7])

    # ── Motion pre-filter ─────────────────────────────────────────────────────
    MOTION_MIN_AREA: int     = _int("MOTION_MIN_AREA", 2000)

    # ── Alert debounce ────────────────────────────────────────────────────────
    ALERT_TRIGGER_FRAMES: int   = _int("ALERT_TRIGGER_FRAMES", 5)
    ALERT_COOLDOWN_SECONDS: int = _int("ALERT_COOLDOWN_SECONDS", 30)
    MAX_ALERTS_HISTORY: int     = _int("MAX_ALERTS_HISTORY", 100)

    # ── MJPEG stream ──────────────────────────────────────────────────────────
    JPEG_QUALITY: int        = _int("JPEG_QUALITY", 75)
    STREAM_FPS: int          = _int("STREAM_FPS", 25)

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str                = _str("HOST", "0.0.0.0")
    PORT: int                = _int("PORT", 8000)
    CORS_ORIGINS: list       = _list_str("CORS_ORIGINS", ["http://localhost:3000"])


settings = _Settings()
