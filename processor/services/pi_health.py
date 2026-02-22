"""Pi/ancs-bridge health checking service."""

import os
from datetime import datetime

import httpx

PI_HEALTH_URL = os.getenv("PI_HEALTH_URL", "")


async def get_pi_health() -> dict:
    """Fetch health status from Pi's ancs-bridge."""
    if not PI_HEALTH_URL:
        return {"status": "disabled", "phone_connected": None, "last_activity_ago": None}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(PI_HEALTH_URL)
            # Parse JSON even on 503 - it contains useful error details
            return resp.json()
    except Exception as e:
        return {"status": "unreachable", "phone_connected": None, "last_activity_ago": None, "error": str(e)}


def format_time_ago(seconds: int) -> str:
    """Format seconds into human-readable time ago."""
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60}m ago"
    else:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m ago"


def get_last_notification_ago(db, hidden_apps: set) -> str | None:
    """Get human-readable time since last visible notification."""
    last_time = db.get_last_notification_time(exclude_apps=hidden_apps)
    if not last_time:
        return None
    try:
        # Parse the SQLite timestamp
        dt = datetime.fromisoformat(last_time.replace(" ", "T"))
        seconds_ago = int((datetime.utcnow() - dt).total_seconds())
        return format_time_ago(max(0, seconds_ago))
    except Exception:
        return None
