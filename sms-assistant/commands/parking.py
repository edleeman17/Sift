"""Parking commands: RINGGO (Text to Park)."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

from commands import register_command

log = logging.getLogger(__name__)

DATA_FILE = Path.home() / ".sms-assistant" / "data.json"
STATE_FILE = Path.home() / ".sms-assistant" / "parking_state.json"
IMESSAGE_GATEWAY = os.getenv("IMESSAGE_GATEWAY_URL", "http://localhost:8095")
RINGGO_SMS_NUMBER = "81025"


def load_data() -> dict:
    """Load user data from ~/.sms-assistant/data.json."""
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}


def load_state() -> dict:
    """Load parking state (last location, etc)."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    """Save parking state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def get_cvv(explicit: str = None) -> Optional[str]:
    """Get CVV from explicit arg or saved data."""
    if explicit:
        return explicit
    data = load_data()
    return data.get("ringgo", {}).get("cvv")


async def send_ringgo_sms(message: str) -> tuple[bool, str]:
    """Send SMS to RingGo via iMessage gateway."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{IMESSAGE_GATEWAY}/send",
                json={
                    "recipient": RINGGO_SMS_NUMBER,
                    "message": message,
                }
            )

            if resp.status_code == 200:
                return True, "sent"
            else:
                error = resp.json().get("error", "unknown")
                return False, error

    except httpx.TimeoutException:
        return False, "timeout"
    except Exception as e:
        return False, str(e)[:50]


@register_command("RINGGO")
async def handle_ringgo(args: str = "") -> str:
    """RingGo Text to Park - start or extend parking.

    Usage:
        RINGGO [location] [duration]     Start parking
        RINGGO EXTEND [duration]         Extend current session
        RINGGO STATUS                    Show last parking location

    Examples:
        RINGGO 26205 2h
        RINGGO EXTEND 1h
        RINGGO EXTEND 30m

    Duration units: m=minutes, h=hours, d=days

    Configure CVV in ~/.sms-assistant/data.json:
        {"ringgo": {"cvv": "123"}}
    """
    if not args:
        state = load_state()
        last_loc = state.get("last_location")
        if last_loc:
            return f"Usage: RINGGO [loc] [time] or RINGGO EXTEND [time] | Last: {last_loc}"
        return "Usage: RINGGO [location] [duration] e.g. RINGGO 26205 2h"

    parts = args.strip().split()
    cmd = parts[0].upper()

    # RINGGO STATUS - show last parking
    if cmd == "STATUS":
        state = load_state()
        last_loc = state.get("last_location")
        last_duration = state.get("last_duration")
        if last_loc:
            return f"Last parking: {last_loc} for {last_duration}"
        return "No recent parking"

    # RINGGO TEST [location] [duration] or RINGGO TEST EXTEND [duration]
    if cmd == "TEST":
        if len(parts) < 2:
            return "Usage: RINGGO TEST 26205 2h or RINGGO TEST EXTEND 1h"

        subcmd = parts[1].upper()
        if subcmd == "EXTEND":
            if len(parts) < 3:
                return "Usage: RINGGO TEST EXTEND 1h"
            duration = parts[2].lower()
            cvv = get_cvv(parts[3] if len(parts) >= 4 else None)
            if not cvv:
                return "No CVV configured"
            masked_cvv = cvv[0] + "**"
            return f"[DRY RUN] To 81025: RingGo extend {duration} {masked_cvv}"
        else:
            location_code = parts[1]
            if len(parts) < 3:
                return "Usage: RINGGO TEST 26205 2h"
            duration = parts[2].lower()
            cvv = get_cvv(parts[3] if len(parts) >= 4 else None)
            if not cvv:
                return "No CVV configured"
            masked_cvv = cvv[0] + "**"
            return f"[DRY RUN] To 81025: RingGo {location_code} {duration} {masked_cvv}"

    # RINGGO EXTEND [duration] [cvv?]
    if cmd == "EXTEND":
        if len(parts) < 2:
            return "Usage: RINGGO EXTEND [duration] e.g. RINGGO EXTEND 1h"

        duration = parts[1].lower()
        if not any(duration.endswith(u) for u in ("m", "h", "d", "w")):
            return "Duration needs unit: 30m, 1h, 2h, etc."

        cvv = get_cvv(parts[2] if len(parts) >= 3 else None)
        if not cvv:
            return "No CVV. Add to data.json or: RINGGO EXTEND 1h 123"

        ringgo_message = f"RingGo extend {duration} {cvv}"
        log.info(f"RingGo extend: {duration}")

        success, error = await send_ringgo_sms(ringgo_message)
        if success:
            return f"Extend sent: +{duration}"
        return f"Failed: {error}"

    # RINGGO [location] [duration] [cvv?] - start parking
    if len(parts) < 2:
        return "Usage: RINGGO [location] [duration]"

    location_code = parts[0]
    duration = parts[1].lower()

    if not any(duration.endswith(u) for u in ("m", "h", "d", "w")):
        return "Duration needs unit: 30m, 1h, 2h, etc."

    cvv = get_cvv(parts[2] if len(parts) >= 3 else None)
    if not cvv:
        return "No CVV. Add to data.json or: RINGGO 26205 2h 123"

    ringgo_message = f"RingGo {location_code} {duration} {cvv}"
    log.info(f"RingGo park: location={location_code} duration={duration}")

    success, error = await send_ringgo_sms(ringgo_message)
    if success:
        # Save location for context
        save_state({
            "last_location": location_code,
            "last_duration": duration,
        })
        return f"Parking sent: {location_code} for {duration}"
    return f"Failed: {error}"
