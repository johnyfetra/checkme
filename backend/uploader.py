"""
uploader.py — Upload images to imgbb (free, no credit card needed).

imgbb free tier: unlimited uploads, 32MB max per image.
Get your API key at https://api.imgbb.com (sign up free).

Falls back gracefully: if no API key or upload fails, returns None.
"""

import base64
from typing import Optional

import httpx

from config import settings


async def upload_snapshot(image_b64: str) -> Optional[str]:
    """
    Upload a base64-encoded JPEG to imgbb.
    Returns the public URL or None if upload is not possible.
    """
    api_key = getattr(settings, "IMGBB_API_KEY", "")
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.imgbb.com/1/upload",
                data={
                    "key": api_key,
                    "image": image_b64,
                    "expiration": 86400,  # 24h — auto-delete (saves space)
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["data"]["url"]
    except Exception as e:
        print(f"[Uploader] imgbb failed: {e}")

    return None
