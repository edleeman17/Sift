"""Info commands: BIN, ICE, INSURANCE, BRIEFING."""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from commands import register_command

log = logging.getLogger(__name__)

DEFAULT_LOCATION = os.getenv("DEFAULT_LOCATION", "London,UK")
DEFAULT_LAT = os.getenv("DEFAULT_LAT", "51.5074")
DEFAULT_LON = os.getenv("DEFAULT_LON", "-0.1278")
OBSIDIAN_TODO = os.getenv("OBSIDIAN_TODO", os.path.expanduser("~/obsidian/_todo.md"))
DATA_FILE = Path(os.getenv("DATA_FILE", os.path.expanduser("~/.sms-assistant/data.json")))


def load_data() -> dict:
    """Load persistent data from JSON file."""
    import json
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE) as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load data: {e}")
    return {"insurance": {}}


@register_command("BIN")
async def handle_bin(args: str = "") -> str:
    """Return which bin to put out this week.

    Configure in ~/.sms-assistant/data.json:
    {
        "bin": {
            "day": "tuesday",
            "black_week": 9,  // Week number when black bin is collected
            "black": "Black general waste",
            "green": "Green recycling + food"
        }
    }
    """
    data = load_data()
    bin_config = data.get("bin", {})

    if not bin_config:
        return "No bin schedule configured"

    try:
        collection_day = bin_config.get("day", "tuesday").lower()
        black_week = bin_config.get("black_week", 9)
        black_label = bin_config.get("black", "Black bin")
        green_label = bin_config.get("green", "Green bin")

        day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                   "friday": 4, "saturday": 5, "sunday": 6}
        target_weekday = day_map.get(collection_day, 1)

        now = datetime.now()
        current_weekday = now.weekday()

        # Find days until collection day
        days_until = (target_weekday - current_weekday) % 7
        if days_until == 0 and now.hour >= 20:
            days_until = 7

        collection_date = now + timedelta(days=days_until)
        collection_week = collection_date.isocalendar()[1]

        # Determine which bin based on week parity
        weeks_diff = collection_week - black_week
        is_black_week = weeks_diff % 2 == 0

        bin_type = black_label if is_black_week else green_label

        # Format day string
        if days_until == 0:
            day_str = "Tonight"
        elif days_until == 1:
            day_str = "Tomorrow night"
        else:
            day_str = collection_date.strftime("%A")

        return f"{day_str}: {bin_type}"

    except Exception as e:
        log.error(f"Bin error: {e}")
        return f"Bin check failed: {str(e)[:50]}"


@register_command("ICE")
async def handle_ice(args: str = "") -> str:
    """Return all emergency/personal info (NHS, NI number, allergies, etc).

    Data is set manually in ~/.sms-assistant/data.json under "ice" key.
    """
    data = load_data()
    ice = data.get("ice", {})

    if not ice:
        return "No ICE info stored"

    lines = []
    for key, value in ice.items():
        lines.append(f"{key.upper()}: {value}")
    return "\n".join(lines)


@register_command("INSURANCE")
async def handle_insurance(args: str = "") -> str:
    """Return car insurance details.

    Data is set manually in ~/.sms-assistant/data.json under "insurance" key.
    """
    data = load_data()
    insurance = data.get("insurance", "")

    if not insurance:
        return "No insurance stored"

    return f"CAR INSURANCE:\n{insurance}"


@register_command("BRIEFING")
async def handle_briefing(args: str = "") -> str:
    """Morning briefing: weather, rain, calendar, todos."""
    # Import here to avoid circular imports
    from commands.weather import handle_rain

    parts = []

    # Date
    now = datetime.now()
    parts.append(now.strftime("%A %d %B"))

    # Weather
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"https://wttr.in/{DEFAULT_LOCATION}",
                params={"format": "%c %t, %o rain"},
                headers={"User-Agent": "curl"}
            )
            if resp.status_code == 200:
                parts.append(resp.text.strip())
    except Exception:
        pass

    # Rain check
    rain = await handle_rain("")
    if "No rain" not in rain:
        parts.append(rain)

    # TODOs
    todo_file = Path(OBSIDIAN_TODO)
    if todo_file.exists():
        try:
            content = todo_file.read_text()
            uncompleted = [line.strip() for line in content.split("\n")
                          if line.strip().startswith("- [ ]")]
            if uncompleted:
                count = len(uncompleted)
                preview = uncompleted[0][6:][:30]
                if count == 1:
                    parts.append(f"TODO: {preview}")
                else:
                    parts.append(f"{count} TODOs. First: {preview}")
        except Exception:
            pass

    # Bin day check
    if now.weekday() in (0, 1):  # Monday or Tuesday
        bin_info = await handle_bin("")
        if "No bin" not in bin_info:
            parts.append(f"BIN: {bin_info}")

    return "\n".join(parts) if parts else "Good morning!"
