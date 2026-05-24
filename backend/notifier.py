"""
notifier.py — WhatsApp alert notifications via Twilio.

Requires in .env:
    TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_AUTH_TOKEN=your_auth_token
    WHATSAPP_FROM=whatsapp:+14155238886    (Twilio sandbox number)
    WHATSAPP_TO=whatsapp:+261XXXXXXXXX    (your phone)
"""

import asyncio
import time
from typing import Optional

from config import settings

# Per-class cooldown state (class_name → last_sent_timestamp)
_last_sent: dict[str, float] = {}
_COOLDOWN = 60  # seconds between alerts for the same class

# French labels + icons
_LABELS = {
    "person":     ("🚶 Personne détectée", "Mouvement humain détecté"),
    "car":        ("🚗 Véhicule détecté",  "Véhicule repéré"),
    "motorcycle": ("🏍️ Moto détectée",     "Moto repérée"),
    "bus":        ("🚌 Bus détecté",       "Bus repéré"),
    "truck":      ("🚛 Camion détecté",    "Camion repéré"),
}


def _is_configured() -> bool:
    return bool(
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.WHATSAPP_TO
    )


def _build_message(class_name: str, event_type: str, zone_name: Optional[str]) -> str:
    title, body = _LABELS.get(class_name, (f"🔍 {class_name} détecté", "Objet détecté"))
    parts = [f"*CheckMe* — {title}", body]
    if zone_name:
        parts.append(f"Zone : {zone_name}")
    if event_type == "intrusion":
        parts.append("⚠️ Intrusion détectée !")
    elif event_type == "loitering":
        parts.append("⏱️ Rôdeur détecté !")
    elif event_type == "line_cross":
        parts.append("🚧 Ligne franchie !")
    return "\n".join(parts)


async def send_whatsapp_alert(
    class_name: str,
    event_type: str = "detection",
    zone_name: Optional[str] = None,
    media_url: Optional[str] = None,
) -> bool:
    """
    Send a WhatsApp message via Twilio asynchronously.
    Returns True if sent, False if skipped (cooldown or not configured).
    """
    if not _is_configured():
        return False

    now = time.monotonic()
    if now - _last_sent.get(class_name, 0) < _COOLDOWN:
        return False  # cooldown active

    _last_sent[class_name] = now
    body = _build_message(class_name, event_type, zone_name)

    try:
        # Run blocking Twilio call in a thread pool so we don't block the event loop
        await asyncio.to_thread(_send_sync, body, media_url)
        print(f"[Notifier] WhatsApp sent: {class_name} / {event_type}")
        return True
    except Exception as e:
        print(f"[Notifier] WhatsApp failed: {e}")
        return False


def _send_sync(body: str, media_url: Optional[str]) -> None:
    """Blocking Twilio call (runs in thread pool)."""
    from twilio.rest import Client  # lazy import — only needed if configured

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    kwargs = {
        "from_": settings.WHATSAPP_FROM,
        "to": settings.WHATSAPP_TO,
        "body": body,
    }
    if media_url:
        kwargs["media_url"] = [media_url]

    client.messages.create(**kwargs)
