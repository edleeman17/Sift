"""Utility commands: NAV, TIMER, REMIND, SEARCH, BORED."""

import asyncio
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple

import httpx

from commands import register_command

log = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
DEFAULT_LAT = os.getenv("DEFAULT_LAT", "51.5074")
DEFAULT_LON = os.getenv("DEFAULT_LON", "-0.1278")
HOME_ADDRESS = os.getenv("HOME_ADDRESS", "")

# Active timers and reminders (in-memory, lost on restart)
ACTIVE_TIMERS: dict[str, asyncio.Task] = {}
ACTIVE_REMINDERS: dict[str, asyncio.Task] = {}

# Will be set by assistant.py on import
_send_sms_reply = None


def set_sms_sender(func):
    """Set the SMS reply function (called from assistant.py)."""
    global _send_sms_reply
    _send_sms_reply = func


async def ollama_generate(prompt: str, system: str = "") -> str:
    """Generate response using Ollama."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
            else:
                log.error(f"Ollama error: {resp.status_code} {resp.text}")
                return "Sorry, LLM unavailable"
    except Exception as e:
        log.error(f"Ollama request failed: {e}")
        return "Sorry, LLM unavailable"


@register_command("NAV")
async def handle_nav(args: str = "") -> str:
    """Get directions as prose using OSRM + LLM."""
    if not args or " to " not in args.lower():
        return "Usage: NAV [from] to [destination]"

    # Parse from/to
    idx = args.lower().index(" to ")
    from_place = args[:idx].strip()
    to_place = args[idx + 4:].strip()

    # Replace "home" with configured home address
    if from_place.lower() == "home" and HOME_ADDRESS:
        from_place = HOME_ADDRESS
    if to_place.lower() == "home" and HOME_ADDRESS:
        to_place = HOME_ADDRESS

    log.info(f"NAV from '{from_place}' to '{to_place}'")

    async with httpx.AsyncClient(timeout=15.0) as client:
        async def geocode(place: str) -> Optional[Tuple[float, float]]:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": place, "format": "json", "limit": 1},
                headers={"User-Agent": "sms-assistant/1.0"}
            )
            if resp.status_code == 200 and resp.json():
                data = resp.json()[0]
                return float(data["lon"]), float(data["lat"])
            return None

        try:
            from_coords = await geocode(from_place)
            to_coords = await geocode(to_place)

            if not from_coords:
                return f"Couldn't find: {from_place}"
            if not to_coords:
                return f"Couldn't find: {to_place}"

            # Get route from OSRM
            coords = f"{from_coords[0]},{from_coords[1]};{to_coords[0]},{to_coords[1]}"
            resp = await client.get(
                f"http://router.project-osrm.org/route/v1/driving/{coords}",
                params={"steps": "true", "overview": "false"}
            )

            if resp.status_code != 200:
                return "Route service unavailable"

            data = resp.json()
            if data.get("code") != "Ok":
                return "No route found"

            route = data["routes"][0]
            legs = route["legs"][0]
            steps = legs["steps"]

            # Extract turn-by-turn instructions
            instructions = []
            for step in steps:
                maneuver = step.get("maneuver", {})
                instruction = step.get("name", "")
                modifier = maneuver.get("modifier", "")
                maneuver_type = maneuver.get("type", "")
                distance = step.get("distance", 0)

                if instruction and maneuver_type not in ("arrive", "depart"):
                    step_miles = distance / 1609.34
                    step_dist = f"{step_miles:.1f}mi" if step_miles >= 0.1 else f"{int(distance * 3.281)}ft"
                    instructions.append(f"{maneuver_type} {modifier} onto {instruction} ({step_dist})")

            # Total distance and duration
            total_dist = route["distance"]
            total_time = route["duration"]
            miles = total_dist / 1609.34
            dist_str = f"{miles:.1f}mi" if miles >= 0.5 else f"{int(total_dist * 3.281)}ft"
            time_str = f"{int(total_time/60)}min"

            # Convert to prose with LLM
            raw_directions = "\n".join(instructions).replace("rotary", "roundabout")
            prompt = f"""Condense to key turns only. Use exact road names. Skip minor roads. No distances.
Example output: "R onto Main St, L onto High St, straight A1, exit M1"

{raw_directions}

Short version:"""

            prose = await ollama_generate(prompt)
            if prose and "unavailable" not in prose.lower():
                return f"{dist_str}, ~{time_str}:\n{prose}"
            else:
                # Fallback: compact raw directions
                compact = []
                for step in instructions[:6]:
                    step = step.replace("turn right", "turn R").replace("turn left", "turn L")
                    step = step.replace("merge slight right", "merge R")
                    step = step.replace("merge slight left", "merge L")
                    step = step.replace("straight onto", "->")
                    step = step.replace("slight right onto", "R")
                    step = step.replace("slight left onto", "L")
                    step = step.replace("rotary", "rbt").replace("exit rbt", "exit")
                    step = step.replace(" onto ", " ")
                    step = step.replace("(", "").replace(")", "")
                    compact.append(step)
                result = f"{dist_str} ~{time_str}\n" + "\n".join(compact)
                if len(instructions) > 6:
                    result += f"\n+{len(instructions) - 6} more"
                return result

        except Exception as e:
            log.error(f"NAV error: {e}")
            return f"Navigation failed: {str(e)[:80]}"


@register_command("TIMER")
async def handle_timer(args: str = "", recipient: str = "") -> str:
    """Set a timer that sends SMS when complete."""
    if not args:
        return "Usage: TIMER [minutes], e.g. TIMER 25"

    try:
        minutes = float(args)
        if minutes <= 0 or minutes > 180:
            return "Timer must be 1-180 minutes"
    except ValueError:
        return "Usage: TIMER [minutes], e.g. TIMER 25"

    timer_id = f"timer_{int(time.time())}"

    async def timer_callback():
        await asyncio.sleep(minutes * 60)
        log.info(f"Timer {timer_id} complete!")
        if _send_sms_reply and recipient:
            _send_sms_reply(recipient, f"TIMER: {minutes:.0f} min timer complete!")
        ACTIVE_TIMERS.pop(timer_id, None)

    task = asyncio.create_task(timer_callback())
    ACTIVE_TIMERS[timer_id] = task

    if minutes == int(minutes):
        return f"Timer set for {int(minutes)} min"
    else:
        return f"Timer set for {minutes} min"


@register_command("REMIND")
async def handle_remind(args: str = "", recipient: str = "") -> str:
    """Set a reminder that texts you at a specific time.

    Usage:
        REMIND 3pm call dentist
        REMIND 14:30 pick up prescription
        REMIND 2h check oven
        REMIND 30m laundry
    """
    if not args:
        return "Usage: REMIND [time] [message]\nExamples: REMIND 3pm call dentist, REMIND 2h check oven"

    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: REMIND [time] [message]"

    time_str, message = parts

    now = datetime.now()
    remind_time = None

    # Parse relative time (2h, 30m, 1h30m)
    relative_match = re.match(r'^(\d+)([hm])(?:(\d+)([m]))?$', time_str.lower())
    if relative_match:
        hours = 0
        minutes = 0
        if relative_match.group(2) == 'h':
            hours = int(relative_match.group(1))
            if relative_match.group(3):
                minutes = int(relative_match.group(3))
        else:
            minutes = int(relative_match.group(1))

        remind_time = now + timedelta(hours=hours, minutes=minutes)

    # Parse absolute time (3pm, 15:30, 3:30pm)
    if not remind_time:
        time_lower = time_str.lower()
        try:
            if 'am' in time_lower or 'pm' in time_lower:
                clean = time_lower.replace('am', ' am').replace('pm', ' pm')
                parsed = datetime.strptime(clean.strip(), "%I %p")
                remind_time = now.replace(hour=parsed.hour, minute=0, second=0, microsecond=0)
            elif ':' in time_str and ('am' in time_lower or 'pm' in time_lower):
                clean = time_lower.replace('am', ' am').replace('pm', ' pm')
                parsed = datetime.strptime(clean.strip(), "%I:%M %p")
                remind_time = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            elif ':' in time_str:
                parsed = datetime.strptime(time_str, "%H:%M")
                remind_time = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            elif time_str.isdigit():
                hour = int(time_str)
                if 0 <= hour <= 23:
                    remind_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        except ValueError:
            pass

    if not remind_time:
        return f"Couldn't parse time: {time_str}\nExamples: 3pm, 15:30, 2h, 30m"

    # If time is in the past, assume tomorrow
    if remind_time <= now:
        remind_time += timedelta(days=1)

    delay_seconds = (remind_time - now).total_seconds()
    if delay_seconds <= 0:
        return "Time must be in the future"

    reminder_id = f"remind_{int(time.time())}"

    async def reminder_callback():
        await asyncio.sleep(delay_seconds)
        log.info(f"Reminder {reminder_id} firing: {message}")
        if _send_sms_reply and recipient:
            _send_sms_reply(recipient, f"REMINDER: {message}")
        ACTIVE_REMINDERS.pop(reminder_id, None)

    task = asyncio.create_task(reminder_callback())
    ACTIVE_REMINDERS[reminder_id] = task

    time_display = remind_time.strftime("%H:%M")
    if remind_time.date() != now.date():
        time_display = remind_time.strftime("%a %H:%M")

    return f"Reminder set for {time_display}: {message}"


@register_command("SEARCH")
async def handle_search(args: str = "") -> str:
    """Perform web search using DuckDuckGo Instant Answer API."""
    if not args:
        return "Usage: SEARCH [query]"

    # Extract search terms
    search_prompt = f"""Extract the search query from this message. Remove words like "search for", "look up", "find".

Message: "{args}"

Reply with ONLY the search terms."""

    search_terms = await ollama_generate(search_prompt)
    if not search_terms:
        search_terms = args

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": search_terms,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1
                }
            )

            if resp.status_code == 200:
                data = resp.json()

                if data.get("AbstractText"):
                    answer = data["AbstractText"]
                elif data.get("Answer"):
                    answer = data["Answer"]
                elif data.get("RelatedTopics") and len(data["RelatedTopics"]) > 0:
                    first = data["RelatedTopics"][0]
                    if isinstance(first, dict) and first.get("Text"):
                        answer = first["Text"]
                    else:
                        answer = f"Search '{search_terms}' - no instant answer"
                else:
                    answer = f"No results for '{search_terms}'"

                return answer
    except Exception as e:
        log.error(f"Search error: {e}")

    return f"Search failed for '{search_terms}'"


# Offline activity suggestions for BORED command
BORED_INDOOR = [
    "Call someone you haven't spoken to in months",
    "Write a handwritten letter or postcard",
    "Cook something new without a recipe",
    "Declutter one drawer or shelf",
    "Do 20 pushups right now",
    "Read a physical book for 30 minutes",
    "Sketch something in front of you",
    "Learn 5 words in a new language",
    "Clean something that's been bugging you",
    "Stretch for 10 minutes",
    "Make a cup of tea and just drink it. Nothing else.",
    "Write down 3 things you're grateful for",
    "Organize your wallet/bag",
    "Do a crossword or sudoku on paper",
    "Plan your next adventure on a paper map",
    "Tidy your desk/workspace",
    "Listen to a full album, start to finish",
    "Meditate for 5 minutes - just breathe",
    "Fix something small that's been broken",
    "Bake something simple",
    "Do a jigsaw puzzle",
    "Play cards or a board game",
]

BORED_OUTDOOR = [
    "Go for a walk - no destination, just wander",
    "Sit outside for 10 minutes, no phone",
    "Take a different route somewhere familiar",
    "Strike up a conversation with a stranger",
    "Go to a charity shop and browse",
    "Sit in a cafe and people-watch",
    "Visit somewhere local you've never been",
    "Walk to the nearest park",
    "Find a bench and just sit for 15 minutes",
    "Take photos of interesting things (mental photos count)",
    "Walk to the sea and watch the waves",
    "Explore a side street you've never been down",
    "Buy a coffee and drink it outside",
    "Go to a bookshop and browse",
    "Visit a local church or historic building",
    "Water your plants and check on them",
]


async def get_current_weather_code() -> Optional[int]:
    """Get current weather code from Open-Meteo."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": DEFAULT_LAT,
                    "longitude": DEFAULT_LON,
                    "current": "weather_code,precipitation",
                    "timezone": "Europe/London",
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("current", {}).get("weather_code", 0)
    except Exception:
        pass
    return None


@register_command("BORED")
async def handle_bored(args: str = "") -> str:
    """Suggest an offline activity based on weather and time."""
    hour = datetime.now().hour
    weather_code = await get_current_weather_code()

    # Weather codes: 0-3 = clear/cloudy, 45-48 = fog, 51-67 = rain/drizzle, 71-77 = snow, 80-99 = showers/storms
    is_rainy = weather_code is not None and weather_code >= 51

    if is_rainy:
        pool = BORED_INDOOR
        prefix = "It's wet outside. "
    elif hour >= 21 or hour < 6:
        pool = BORED_INDOOR
        prefix = ""
    else:
        pool = BORED_OUTDOOR + random.sample(BORED_INDOOR, 5)
        prefix = ""

    activity = random.choice(pool)

    # Time-specific additions
    if 6 <= hour < 9:
        extras = ["Watch the sunrise", "Morning yoga", "Make a proper breakfast"]
        activity = random.choice([activity] + extras)
    elif 21 <= hour or hour < 6:
        extras = ["Stargaze for 10 minutes", "Write in a journal", "Plan tomorrow on paper"]
        activity = random.choice([activity] + extras)

    return f"{prefix}{activity}"
