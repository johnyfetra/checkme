"""
main.py — CheckMe FastAPI backend.

Full intelligence pipeline per frame:
  camera → motion pre-filter → YOLOv8 → SORT tracker
      → zone engine → SQLite DB → MP4 recorder → WhatsApp notifier
      → MJPEG stream + WebSocket events

Endpoints:
  GET  /api/video          — MJPEG stream
  GET  /api/status         — camera + AI info
  GET  /api/events         — recent events from DB
  GET  /api/clips          — recorded clip list
  GET  /api/stats          — last-24h detection stats
  POST /api/zones          — create/update a zone
  GET  /api/zones          — list active zones
  WS   /ws/events          — real-time event broadcast
"""

import asyncio
import base64
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import database as db
from camera import Camera
from config import settings
from detector import Detector
from motion import MotionDetector
from notifier import send_whatsapp_alert
from recorder import ClipRecorder
from tracker import Tracker
from zones import ZoneEngine

# ── Singletons ────────────────────────────────────────────────────────────────
camera        = Camera()
detector      = Detector()
motion_det    = MotionDetector()
tracker       = Tracker(
    max_age=settings.TRACKER_MAX_AGE,
    min_hits=settings.TRACKER_MIN_HITS,
    iou_threshold=settings.TRACKER_IOU_THRESHOLD,
)
zone_engine   = ZoneEngine()
recorder      = ClipRecorder(
    fps=15,
    width=settings.CAMERA_WIDTH,
    height=settings.CAMERA_HEIGHT,
)

_ws_clients: list[WebSocket] = []
_total_events: int = 0


# ── App lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    zone_engine.load_zones()
    camera.start()
    print("[CheckMe] Camera started ✓")
    yield
    recorder.flush()
    camera.stop()
    print("[CheckMe] Camera stopped")


app = FastAPI(title="CheckMe API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket broadcast ───────────────────────────────────────────────────────
async def _broadcast(event: dict) -> None:
    dead: list[WebSocket] = []
    for ws in _ws_clients:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


# ── Frame processing helpers (run in thread pool) ─────────────────────────────
def _encode_snapshot(frame) -> str:
    """Return a base64-encoded JPEG thumbnail (320×180)."""
    thumb = cv2.resize(frame, (320, 180))
    ok, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 60])
    if ok:
        return base64.b64encode(buf.tobytes()).decode()
    return ""


def _process_frame(frame):
    """
    Full synchronous pipeline — runs in asyncio.to_thread().
    Returns (annotated_frame, zone_events).
    """
    h, w = frame.shape[:2]

    # 1. YOLOv8 detection
    detections = detector.detect(frame)

    # 2. SORT tracker (enriches detections with track_id)
    if settings.TRACKER_ENABLED and detections:
        detections = tracker.update(detections)

    # 3. Zone rule engine
    zone_events = zone_engine.evaluate(detections, w, h)

    # 4. Annotate frame
    annotated = detector.draw(frame, detections)
    zone_engine.draw_zones(annotated, w, h)

    return annotated, detections, zone_events


# ── MJPEG frame generator ─────────────────────────────────────────────────────
async def _frame_generator():
    global _total_events
    frame_interval = 1.0 / settings.STREAM_FPS
    status_counter = 0

    while True:
        t0 = time.monotonic()

        frame = await asyncio.to_thread(camera.read_frame)
        if frame is None:
            await asyncio.sleep(0.05)
            continue

        # Motion pre-filter — skip YOLO on static scenes
        has_motion, _ = await asyncio.to_thread(motion_det.detect, frame)

        annotated = frame.copy()
        detections: list[dict] = []
        zone_events: list[dict] = []

        if has_motion:
            annotated, detections, zone_events = await asyncio.to_thread(
                _process_frame, frame
            )

            # Persist zone events + notify
            for ev in zone_events:
                snapshot = await asyncio.to_thread(_encode_snapshot, frame)
                ts = datetime.now(timezone.utc).isoformat()

                # Register clip if not already recording
                clip_id: Optional[int] = None
                if settings.RECORDING_ENABLED and not recorder.is_recording:
                    clip_id = await asyncio.to_thread(
                        db.insert_clip, f"pending_{ts[:19]}.mp4", ts
                    )
                    recorder.trigger(clip_id=clip_id, started_at=ts)

                event_id = await asyncio.to_thread(
                    db.insert_event,
                    ev["class_name"],
                    ev["confidence"],
                    ev["event_type"],
                    ev.get("track_id"),
                    ev.get("zone_name"),
                    ev.get("duration_s"),
                    snapshot,
                    clip_id,
                )

                _total_events += 1

                payload = {**ev, "id": event_id, "snapshot_b64": snapshot, "ts": ts}
                await _broadcast({"type": "alert", "data": payload})

                # WhatsApp alert (async, non-blocking)
                asyncio.create_task(
                    send_whatsapp_alert(
                        ev["class_name"],
                        ev["event_type"],
                        ev.get("zone_name"),
                    )
                )

            # Also extend recording if detections keep arriving
            if detections and settings.RECORDING_ENABLED:
                if recorder.is_recording:
                    recorder.trigger()

        # Feed frame to recorder
        if settings.RECORDING_ENABLED:
            await asyncio.to_thread(recorder.write_frame, frame)

        # Motion indicator overlay
        if has_motion:
            cv2.putText(
                annotated, "MOTION", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 100), 2,
            )

        # Periodic status broadcast (~every 2 s)
        status_counter += 1
        if status_counter >= settings.STREAM_FPS * 2:
            status_counter = 0
            await _broadcast({
                "type": "status",
                "data": {
                    "motion": has_motion,
                    "detections": len(detections),
                    "events_total": _total_events,
                    "recording": recorder.is_recording,
                },
            })

        # Encode to JPEG and yield MJPEG boundary
        ok, buf = cv2.imencode(
            ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, settings.JPEG_QUALITY]
        )
        if ok:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buf.tobytes()
                + b"\r\n"
            )

        elapsed = time.monotonic() - t0
        sleep_t = frame_interval - elapsed
        if sleep_t > 0:
            await asyncio.sleep(sleep_t)


# ── REST endpoints ────────────────────────────────────────────────────────────
@app.get("/api/video")
async def video_stream():
    return StreamingResponse(
        _frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/status")
async def get_status():
    return {
        "camera_open": camera.is_open(),
        "model": detector.model_name,
        "device": detector.device,
        "events_total": _total_events,
        "recording": recorder.is_recording,
        "tracker_enabled": settings.TRACKER_ENABLED,
    }


@app.get("/api/events")
async def get_events(limit: int = 100):
    return await asyncio.to_thread(db.get_events, limit)


@app.get("/api/clips")
async def get_clips(limit: int = 50):
    return await asyncio.to_thread(db.get_clips, limit)


@app.get("/api/stats")
async def get_stats():
    return await asyncio.to_thread(db.get_stats_last_24h)


@app.get("/api/zones")
async def get_zones():
    return await asyncio.to_thread(db.get_zones)


class ZoneCreate(BaseModel):
    name: str
    type: str = "polygon"
    points_json: str
    alert_classes: str = "person"
    loiter_seconds: float = 10.0


@app.post("/api/zones", status_code=201)
async def create_zone(body: ZoneCreate):
    zone_id = await asyncio.to_thread(
        db.save_zone,
        body.name, body.points_json, body.type,
        body.alert_classes, body.loiter_seconds,
    )
    await asyncio.to_thread(zone_engine.load_zones)
    return {"id": zone_id, "name": body.name}


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    await ws.send_json({
        "type": "connected",
        "data": {
            "device": detector.device,
            "model": detector.model_name,
            "events_total": _total_events,
        },
    })
    try:
        while True:
            await ws.receive_text()   # keep-alive / ping
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


# ── Dev entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
