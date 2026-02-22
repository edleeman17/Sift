#!/usr/bin/env python3
"""SMS Assistant - Process incoming SMS via Messages.app and respond with LLM."""

import asyncio
import json
import logging
import os
import random
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Tuple

import emoji
import httpx

# Active timers (in-memory, lost on restart)
ACTIVE_TIMERS: dict[str, asyncio.Task] = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# Configuration
DUMBPHONE_NUMBER = os.getenv("DUMBPHONE_NUMBER", "")  # e.g., "+441234567890"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
DEFAULT_LOCATION = os.getenv("DEFAULT_LOCATION", "London,UK")
PI_HOST = os.getenv("PI_HOST", "")  # e.g., "pi@192.168.1.100" for remote reset
OBSIDIAN_TODO = os.getenv("OBSIDIAN_TODO", os.path.expanduser("~/obsidian/_todo.md"))  # For TODO
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))  # seconds
MESSAGES_DB = Path(os.getenv("MESSAGES_DB", os.path.expanduser("~/Library/Messages/chat.db")))
STATE_FILE = Path(os.getenv("STATE_FILE", os.path.expanduser("~/.sms-assistant/state.json")))
HEARTBEAT_FILE = Path(os.getenv("HEARTBEAT_FILE", os.path.expanduser("~/.sms-assistant/heartbeat")))
SUPPORTS_EMOJI = os.getenv("SUPPORTS_EMOJI", "false").lower() in ("true", "1", "yes")

# Command types
COMMANDS = ["WEATHER", "SEARCH", "MESSAGES", "CHAT"]


@dataclass
class IncomingMessage:
    rowid: int
    text: str
    timestamp: datetime
    sender: str


def update_heartbeat():
    """Update heartbeat file to show service is running."""
    try:
        HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_FILE.write_text(datetime.now().isoformat())
    except Exception:
        pass  # Non-critical


def load_state() -> dict:
    """Load last processed message ID and recent replies."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            state = json.load(f)
            # Ensure recent_replies exists
            if "recent_replies" not in state:
                state["recent_replies"] = []
            return state
    return {"last_rowid": 0, "recent_replies": []}


def save_state(state: dict):
    """Save state to disk."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def is_own_reply(text: str, recent_replies: list) -> bool:
    """Check if incoming message is one of our own replies (for self-texting loop prevention)."""
    # Strip numbering prefix like "(1/2) " for comparison
    clean_text = text.strip()
    if clean_text.startswith("(") and ") " in clean_text[:8]:
        clean_text = clean_text.split(") ", 1)[-1]

    for reply in recent_replies:
        # Check if this message matches a recent reply (or chunk of one)
        if clean_text in reply or reply in clean_text:
            return True
        # Also check without numbering
        clean_reply = reply
        if clean_reply.startswith("(") and ") " in clean_reply[:8]:
            clean_reply = clean_reply.split(") ", 1)[-1]
        if clean_text == clean_reply:
            return True
    return False


def get_new_messages(since_rowid: int) -> list[IncomingMessage]:
    """Fetch new messages from dumbphone number."""
    if not DUMBPHONE_NUMBER:
        log.warning("DUMBPHONE_NUMBER not set")
        return []

    # Normalize phone number for matching
    number_variants = [
        DUMBPHONE_NUMBER,
        DUMBPHONE_NUMBER.replace("+", ""),
        DUMBPHONE_NUMBER.replace(" ", ""),
    ]

    messages = []
    try:
        conn = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Query for messages from the dumbphone number
        # is_from_me = 0 means incoming message
        query = """
            SELECT m.ROWID, m.text, m.date, h.id
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.ROWID > ?
              AND m.is_from_me = 0
              AND m.text IS NOT NULL
              AND m.text != ''
            ORDER BY m.ROWID ASC
        """

        cursor.execute(query, (since_rowid,))

        for row in cursor.fetchall():
            rowid, text, date_val, sender = row

            # Check if sender matches dumbphone
            sender_normalized = sender.replace("+", "").replace(" ", "").replace("-", "")
            matches = any(
                v.replace("+", "").replace(" ", "").replace("-", "") in sender_normalized
                or sender_normalized in v.replace("+", "").replace(" ", "").replace("-", "")
                for v in number_variants
            )

            if matches:
                # Convert Apple's timestamp (nanoseconds since 2001-01-01)
                timestamp = datetime(2001, 1, 1) + timedelta(seconds=date_val / 1e9)
                messages.append(IncomingMessage(
                    rowid=rowid,
                    text=text.strip(),
                    timestamp=timestamp,
                    sender=sender
                ))

        conn.close()
    except Exception as e:
        log.error(f"Failed to read messages: {e}")

    return messages


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


async def classify_command(text: str) -> str:
    """Classify the incoming message into a command type."""
    prompt = f"""Classify this SMS message into exactly ONE category.

Message: "{text}"

Categories:
- WEATHER: Asking about weather, temperature, forecast, rain, etc.
- SEARCH: Asking to look something up, search the web, find information
- MESSAGES: Asking about unread messages, message summary, who texted
- CHAT: General conversation, questions, anything else

Reply with ONLY the category name (WEATHER, SEARCH, MESSAGES, or CHAT)."""

    response = await ollama_generate(prompt)

    # Extract command from response
    for cmd in COMMANDS:
        if cmd in response.upper():
            return cmd

    return "CHAT"  # Default to chat


async def handle_weather(args: str = "") -> str:
    """Get weather information using wttr.in (no API key needed).

    WEATHER - current conditions
    WEATHER week - 5 day forecast
    WEATHER [place] - weather for location
    """
    args = args.strip().lower()

    # Check for week forecast
    if args == "week":
        location = DEFAULT_LOCATION
        show_week = True
    elif args.startswith("week "):
        location = args[5:].strip()
        show_week = True
    elif args.endswith(" week"):
        location = args[:-5].strip()
        show_week = True
    else:
        location = args if args else DEFAULT_LOCATION
        show_week = False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if show_week:
                # 5 day forecast
                resp = await client.get(
                    f"https://wttr.in/{location}",
                    params={"format": "%l:\n%c%t|%c%t|%c%t|%c%t|%c%t\n(Mon-Fri style forecast)"},
                    headers={"User-Agent": "curl"}
                )
                # Better: use Open-Meteo for proper forecast
                meteo = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": DEFAULT_LAT,
                        "longitude": DEFAULT_LON,
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                        "timezone": "Europe/London",
                        "forecast_days": 5,
                    }
                )
                if meteo.status_code == 200:
                    data = meteo.json()
                    daily = data.get("daily", {})
                    dates = daily.get("time", [])
                    highs = daily.get("temperature_2m_max", [])
                    lows = daily.get("temperature_2m_min", [])
                    rain = daily.get("precipitation_probability_max", [])

                    lines = [f"{location.title()} 5-day:"]
                    for i in range(min(5, len(dates))):
                        day = datetime.fromisoformat(dates[i]).strftime("%a")
                        hi = int(highs[i]) if i < len(highs) else "?"
                        lo = int(lows[i]) if i < len(lows) else "?"
                        r = rain[i] if i < len(rain) else 0
                        rain_str = f" {r}%rain" if r > 20 else ""
                        lines.append(f"{day}: {lo}-{hi}°C{rain_str}")
                    return "\n".join(lines)

            # Current weather - use Open-Meteo for reliable data
            meteo = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": DEFAULT_LAT,
                    "longitude": DEFAULT_LON,
                    "current": "temperature_2m,apparent_temperature,precipitation_probability,weather_code",
                    "daily": "sunrise,sunset",
                    "timezone": "Europe/London",
                    "forecast_days": 1,
                }
            )
            if meteo.status_code == 200:
                data = meteo.json()
                current = data.get("current", {})
                daily = data.get("daily", {})

                temp = current.get("temperature_2m", "?")
                feels = current.get("apparent_temperature", "?")
                rain_prob = current.get("precipitation_probability", 0) or 0
                weather_code = current.get("weather_code", 0)

                # Convert WMO weather code to text
                weather_text = {
                    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
                    45: "Foggy", 48: "Icy fog", 51: "Light drizzle", 53: "Drizzle",
                    55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
                    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
                    80: "Light showers", 81: "Showers", 82: "Heavy showers",
                    85: "Light snow showers", 86: "Snow showers",
                    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Severe thunderstorm"
                }.get(weather_code, "Unknown")

                sunrise = daily.get("sunrise", [""])[0]
                sunset = daily.get("sunset", [""])[0]
                sun_rise = sunrise.split("T")[1][:5] if "T" in sunrise else "?"
                sun_set = sunset.split("T")[1][:5] if "T" in sunset else "?"

                rain_str = f" Rain: {rain_prob}%." if rain_prob > 0 else ""
                return f"{location.title()}: {weather_text}, {int(temp)}C (feels {int(feels)}C).{rain_str} Sun: {sun_rise}-{sun_set}"
            else:
                return f"Couldn't get weather for {location}"
    except Exception as e:
        log.error(f"Weather API error: {type(e).__name__}: {e!r}")
        return "Weather lookup failed"


async def handle_search(query: str) -> str:
    """Perform web search using DuckDuckGo Instant Answer API."""
    # Extract search terms
    search_prompt = f"""Extract the search query from this message. Remove words like "search for", "look up", "find".

Message: "{query}"

Reply with ONLY the search terms."""

    search_terms = await ollama_generate(search_prompt)
    if not search_terms:
        search_terms = query

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

                # Try Abstract first
                if data.get("AbstractText"):
                    answer = data["AbstractText"]
                # Then try Answer
                elif data.get("Answer"):
                    answer = data["Answer"]
                # Then try first RelatedTopic
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


async def handle_messages_summary() -> str:
    """Summarize recent unread messages."""
    try:
        conn = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Get recent unread messages (is_read = 0, is_from_me = 0)
        # Last 24 hours
        day_ago = (datetime.now() - timedelta(days=1) - datetime(2001, 1, 1)).total_seconds() * 1e9

        query = """
            SELECT h.id, m.text, m.date
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.is_from_me = 0
              AND m.is_read = 0
              AND m.text IS NOT NULL
              AND m.date > ?
            ORDER BY m.date DESC
            LIMIT 20
        """

        cursor.execute(query, (day_ago,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No unread messages"

        # Format messages for summary
        messages_text = "\n".join([
            f"From {row[0]}: {row[1][:100]}"
            for row in rows
        ])

        summary_prompt = f"""Summarize these unread messages. List who messaged and key points.

{messages_text}

Be concise but include all important details."""

        return await ollama_generate(summary_prompt)

    except Exception as e:
        log.error(f"Messages summary error: {e}")
        return "Couldn't read messages"


async def handle_chat(query: str) -> str:
    """General chat/Q&A with LLM."""
    system = """You are a helpful SMS assistant. Be concise but thorough.
No markdown formatting. Plain text only."""

    return await ollama_generate(query, system)


BARK_URL = os.getenv("BARK_URL", "")  # e.g., "http://192.168.1.100:8089"
BARK_DEVICE_KEY = os.getenv("BARK_DEVICE_KEY", "")  # Your Bark device key
CONTACTS_FILE = Path(os.getenv("CONTACTS_FILE", os.path.expanduser("~/docker-projects/notification-forwarder/contacts.json")))
# Sensitive data stored outside project directory
DATA_FILE = Path(os.getenv("DATA_FILE", os.path.expanduser("~/.sms-assistant/data.json")))
DEFAULT_LAT = os.getenv("DEFAULT_LAT", "51.5074")  # Set via env var
DEFAULT_LON = os.getenv("DEFAULT_LON", "-0.1278")
HOME_ADDRESS = os.getenv("HOME_ADDRESS", "")


async def handle_locate() -> str:
    """Send loud alarm notification to iPhone via Bark."""
    log.info("Sending LOCATE alarm via Bark")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BARK_URL}/{BARK_DEVICE_KEY}/LOCATE/Finding your iPhone!",
                params={
                    "sound": "alarm",
                    "level": "critical",  # Bypasses silent mode and DND
                    "volume": "10",
                }
            )

            if resp.status_code == 200:
                return "Alarm sent to iPhone!"
            else:
                return f"Bark error: {resp.status_code}"

    except Exception as e:
        log.error(f"Locate error: {e}")
        return f"Locate failed: {str(e)[:80]}"


async def handle_done(numbers: str) -> str:
    """Mark TODO items as complete by their number."""
    todo_file = Path(OBSIDIAN_TODO)

    if not todo_file.exists():
        return "No TODOs to complete"

    # Parse numbers - accept "1,2,3" or "1 2 3" or just "1"
    try:
        nums = [int(n.strip()) for n in numbers.replace(",", " ").split()]
    except ValueError:
        return "Usage: DONE 1,2,3 or DONE 1 2 3"

    if not nums:
        return "Usage: DONE 1,2,3"

    try:
        content = todo_file.read_text()
        lines = content.split("\n")

        # Find uncompleted tasks and their line indices
        uncompleted = []
        for i, line in enumerate(lines):
            if line.strip().startswith("- [ ]"):
                uncompleted.append(i)

        completed_tasks = []
        for num in nums:
            if 1 <= num <= len(uncompleted):
                line_idx = uncompleted[num - 1]
                # Mark as done
                lines[line_idx] = lines[line_idx].replace("- [ ]", "- [x]", 1)
                task_text = lines[line_idx].replace("- [x]", "").strip()
                completed_tasks.append(task_text[:30])

        # Write back
        todo_file.write_text("\n".join(lines))

        if completed_tasks:
            return f"Done: {', '.join(completed_tasks)}"
        else:
            return f"Invalid numbers. You have {len(uncompleted)} TODOs."

    except Exception as e:
        log.error(f"DONE error: {e}")
        return f"Failed: {str(e)[:80]}"


async def handle_todo(task: str = "") -> str:
    """Add or read TODO items from Obsidian _todo.md file."""
    todo_file = Path(OBSIDIAN_TODO)

    # No task provided - read back TODOs
    if not task:
        try:
            if not todo_file.exists():
                return "No TODOs yet"

            content = todo_file.read_text()
            # Find uncompleted tasks (- [ ])
            uncompleted = [line.strip() for line in content.split("\n")
                          if line.strip().startswith("- [ ]")]

            if not uncompleted:
                return "All TODOs complete!"

            # Format for SMS - strip the "- [ ] " prefix, show all
            items = [item[6:] for item in uncompleted]
            result = "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

            return result

        except Exception as e:
            log.error(f"TODO read error: {e}")
            return f"Failed to read TODOs: {str(e)[:80]}"

    # Task provided - add it
    try:
        todo_line = f"- [ ] {task}\n"

        with open(todo_file, "a") as f:
            f.write(todo_line)

        log.info(f"Added TODO to {todo_file}: {task}")
        return f"Added: {task[:100]}"

    except Exception as e:
        log.error(f"TODO error: {e}")
        return f"Failed to add TODO: {str(e)[:80]}"


async def handle_ping() -> str:
    """Check Pi and iPhone connection status."""
    log.info(f"Checking status on {PI_HOST}")

    try:
        # Check if Pi is reachable and get health status
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", PI_HOST, "curl -s http://localhost:8081/health"],
            capture_output=True,
            text=True,
            timeout=15
        )

        if result.returncode == 0:
            import json
            try:
                health = json.loads(result.stdout)
                status = health.get("status", "unknown")
                connected = health.get("phone_connected", False)
                last_activity = health.get("last_activity_ago")
                battery = health.get("battery")

                if connected:
                    parts = ["Pi OK. iPhone connected."]
                    if battery is not None:
                        parts.append(f"Battery {battery}%.")
                    if last_activity:
                        parts.append(f"Last notif {last_activity}s ago.")
                    return " ".join(parts)
                else:
                    return "Pi OK but iPhone NOT connected"
            except:
                return f"Pi reachable but health check failed"
        else:
            return "Pi unreachable or ancs-bridge not running"

    except subprocess.TimeoutExpired:
        return "Pi connection timed out"
    except Exception as e:
        return f"Status check failed: {str(e)[:80]}"


async def handle_reset() -> str:
    """Reset Bluetooth stack on Pi remotely."""
    log.info(f"Executing remote reset on {PI_HOST}")

    # Commands to restart the full Bluetooth stack
    reset_commands = """
        systemctl --user stop ancs-bridge
        systemctl --user stop ancs4linux-observer
        systemctl --user stop ancs4linux-advertising
        sudo systemctl restart bluetooth
        sleep 3
        sudo hciconfig hci0 down
        sleep 1
        sudo hciconfig hci0 up
        sleep 2
        systemctl --user start ancs4linux-advertising
        sleep 3
        /usr/local/bin/ancs4linux-ctl enable-advertising --hci-address B8:27:EB:D1:4B:FD --name ancs4linux
        sleep 2
        systemctl --user start ancs4linux-observer
        sleep 2
        systemctl --user start ancs-bridge
    """

    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=10", PI_HOST, reset_commands],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            log.info("Pi reset completed successfully")
            return "Pi reset complete. BT stack restarted."
        else:
            log.error(f"Pi reset failed: {result.stderr}")
            return f"Reset failed: {result.stderr[:100]}"

    except subprocess.TimeoutExpired:
        log.error("Pi reset timed out")
        return "Reset timed out - Pi may be unreachable"
    except Exception as e:
        log.error(f"Pi reset error: {e}")
        return f"Reset error: {str(e)[:100]}"


async def handle_timer(minutes_str: str, recipient: str) -> str:
    """Set a timer that sends SMS when complete."""
    try:
        minutes = float(minutes_str)
        if minutes <= 0 or minutes > 180:
            return "Timer must be 1-180 minutes"
    except ValueError:
        return "Usage: TIMER [minutes], e.g. TIMER 25"

    timer_id = f"timer_{int(time.time())}"

    async def timer_callback():
        await asyncio.sleep(minutes * 60)
        log.info(f"Timer {timer_id} complete!")
        send_sms_reply(recipient, f"TIMER: {minutes:.0f} min timer complete!")
        ACTIVE_TIMERS.pop(timer_id, None)

    task = asyncio.create_task(timer_callback())
    ACTIVE_TIMERS[timer_id] = task

    if minutes == int(minutes):
        return f"Timer set for {int(minutes)} min"
    else:
        return f"Timer set for {minutes} min"


def load_contacts() -> dict[str, str]:
    """Load contacts from JSON file."""
    if not CONTACTS_FILE.exists():
        return {}
    try:
        with open(CONTACTS_FILE) as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to load contacts: {e}")
        return {}


def fuzzy_match_contacts(query: str, contacts: dict[str, str], threshold: float = 0.5) -> list[tuple[str, str, float]]:
    """Fuzzy match contact names. Returns list of (name, number, score) sorted by score."""
    query_lower = query.lower()
    results = []

    for name, number in contacts.items():
        name_lower = name.lower()

        # Exact match
        if query_lower == name_lower:
            results.append((name, number, 1.0))
            continue

        # Starts with query
        if name_lower.startswith(query_lower):
            results.append((name, number, 0.95))
            continue

        # Word match (any word starts with query)
        words = name_lower.split()
        if any(w.startswith(query_lower) for w in words):
            results.append((name, number, 0.9))
            continue

        # Contains query
        if query_lower in name_lower:
            results.append((name, number, 0.8))
            continue

        # Fuzzy ratio
        ratio = SequenceMatcher(None, query_lower, name_lower).ratio()
        if ratio >= threshold:
            results.append((name, number, ratio))

    # Sort by score descending
    results.sort(key=lambda x: x[2], reverse=True)
    return results


async def handle_call(query: str) -> str:
    """Lookup phone number with fuzzy matching."""
    if not query:
        return "Usage: CALL [name]"

    contacts = load_contacts()
    if not contacts:
        return "No contacts file found"

    matches = fuzzy_match_contacts(query, contacts)

    if not matches:
        return f"No matches for '{query}'"

    # Perfect or near-perfect match - return single result
    if matches[0][2] >= 0.95:
        name, number, _ = matches[0]
        return f"{name}: {number}"

    # Multiple fuzzy matches - return top 5
    top = matches[:5]
    lines = [f"{name}: {number}" for name, number, _ in top]
    return "\n".join(lines)


async def handle_contact(query: str) -> str:
    """Lookup business/place contact details (phone, address, hours)."""
    log.info(f"CONTACT lookup: {query}")

    # Add location context if not specified
    search_query = query
    if "uk" not in query.lower():
        search_query = f"{query} UK"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": search_query,
                    "format": "json",
                    "limit": 3,
                    "addressdetails": 1,
                    "extratags": 1,
                },
                headers={"User-Agent": "sms-assistant/1.0"}
            )

            if resp.status_code != 200 or not resp.json():
                return f"No results for '{query}'"

            results = []
            for place in resp.json():
                name = place.get("name", place.get("display_name", "").split(",")[0])
                address = place.get("display_name", "")
                # Shorten address - take first 3 parts
                address_parts = address.split(",")[:3]
                short_address = ", ".join(p.strip() for p in address_parts)

                extra = place.get("extratags", {})
                phone = extra.get("phone", extra.get("contact:phone", ""))
                website = extra.get("website", extra.get("contact:website", ""))
                hours = extra.get("opening_hours", "")

                parts = [name]
                if phone:
                    parts.append(f"Tel: {phone}")
                if short_address and short_address != name:
                    parts.append(short_address)
                if hours:
                    # Simplify hours format
                    hours_short = hours.replace("Mo-Fr", "M-F").replace("Sa", "Sat").replace("Su", "Sun")
                    if len(hours_short) < 50:
                        parts.append(f"Hours: {hours_short}")

                results.append("\n".join(parts))

            if not results:
                return f"No details found for '{query}'"

            # Return first result, or multiple if close matches
            return results[0] if len(results) == 1 else "\n---\n".join(results[:2])

    except Exception as e:
        log.error(f"CONTACT error: {e}")
        return f"Lookup failed: {str(e)[:80]}"


async def handle_nav(from_place: str, to_place: str) -> str:
    """Get directions as prose using OSRM + LLM."""
    # Replace "home" with configured home address
    if from_place.lower() == "home" and HOME_ADDRESS:
        from_place = HOME_ADDRESS
    if to_place.lower() == "home" and HOME_ADDRESS:
        to_place = HOME_ADDRESS
    log.info(f"NAV from '{from_place}' to '{to_place}'")

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Geocode both places using Nominatim
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

            # Convert to prose with LLM - terse for SMS
            raw_directions = "\n".join(instructions).replace("rotary", "roundabout")
            prompt = f"""Condense to key turns only. Use exact road names. Skip minor roads. No distances.
Example output: "R onto Main St, L onto High St, straight A1, exit M1"

{raw_directions}

Short version:"""

            prose = await ollama_generate(prompt)
            if prose and "unavailable" not in prose.lower():
                return f"{dist_str}, ~{time_str}:\n{prose}"
            else:
                # Fallback: compact raw directions for small screens
                compact = []
                for step in instructions[:6]:
                    # Shorten: "turn right onto Main Road (1.2km)" -> "R Main Road 1.2km"
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
    """Get current weather code from Open-Meteo. Returns None on error."""
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


async def handle_bored() -> str:
    """Suggest an offline activity based on weather and time."""
    hour = datetime.now().hour
    weather_code = await get_current_weather_code()

    # Weather codes: 0-3 = clear/cloudy, 45-48 = fog, 51-67 = rain/drizzle, 71-77 = snow, 80-99 = showers/storms
    is_rainy = weather_code is not None and weather_code >= 51

    # Choose activity pool based on weather
    if is_rainy:
        pool = BORED_INDOOR
        prefix = "It's wet outside. "
    elif hour >= 21 or hour < 6:
        pool = BORED_INDOOR
        prefix = ""
    else:
        # Good weather - mix of both, prefer outdoor
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


def load_data() -> dict:
    """Load persistent data from JSON file."""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE) as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load data: {e}")
    return {"insurance": {}}


def save_data(data: dict):
    """Save persistent data to JSON file."""
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.error(f"Failed to save data: {e}")


async def handle_insurance() -> str:
    """Return car insurance details.

    Data is set manually in ~/.sms-assistant/data.json under "insurance" key.
    """
    data = load_data()
    insurance = data.get("insurance", "")

    if not insurance:
        return "No insurance stored"

    return f"CAR INSURANCE:\n{insurance}"


async def handle_ice() -> str:
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


async def handle_rain(tomorrow: bool = False) -> str:
    """Check if rain is expected. RAIN = next 3 hours, RAIN TOMORROW = tomorrow's forecast."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": DEFAULT_LAT,
                    "longitude": DEFAULT_LON,
                    "hourly": "precipitation_probability,precipitation",
                    "daily": "precipitation_probability_max,precipitation_sum",
                    "timezone": "Europe/London",
                    "forecast_days": 2,
                }
            )

            if resp.status_code != 200:
                return "Couldn't check rain forecast"

            data = resp.json()

            if tomorrow:
                # Tomorrow's daily forecast
                daily = data.get("daily", {})
                dates = daily.get("time", [])
                probs = daily.get("precipitation_probability_max", [])
                precip = daily.get("precipitation_sum", [])

                if len(dates) < 2:
                    return "No tomorrow forecast available"

                prob = probs[1] if len(probs) > 1 else 0
                mm = precip[1] if len(precip) > 1 else 0

                if prob < 20:
                    return "Tomorrow: No rain expected"
                elif prob < 50:
                    return f"Tomorrow: Low chance of rain ({prob}%)"
                elif prob < 70:
                    return f"Tomorrow: Rain possible ({prob}%)"
                else:
                    if mm > 0:
                        return f"Tomorrow: Rain likely ({prob}%), ~{mm:.1f}mm"
                    return f"Tomorrow: Rain likely ({prob}%)"

            # Today - next 3 hours
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            probs = hourly.get("precipitation_probability", [])
            precip = hourly.get("precipitation", [])

            now = datetime.now()
            current_hour = now.strftime("%Y-%m-%dT%H:00")

            # Find next 3 hours
            upcoming = []
            found_current = False
            for i, t in enumerate(times):
                if t >= current_hour:
                    found_current = True
                if found_current and len(upcoming) < 3:
                    hour_str = datetime.fromisoformat(t).strftime("%H:%M")
                    prob = probs[i] if i < len(probs) else 0
                    mm = precip[i] if i < len(precip) else 0
                    upcoming.append((hour_str, prob, mm))

            if not upcoming:
                return "No forecast data available"

            # Summarize
            max_prob = max(p[1] for p in upcoming)
            total_mm = sum(p[2] for p in upcoming)

            if max_prob < 10:
                return "No rain expected next 3 hours"
            elif max_prob < 30:
                return f"Low chance of rain ({max_prob}% max)"
            elif max_prob < 60:
                details = ", ".join(f"{h}: {p}%" for h, p, _ in upcoming if p >= 20)
                return f"Maybe rain. {details}"
            else:
                details = ", ".join(f"{h}: {p}%" for h, p, _ in upcoming)
                if total_mm > 0:
                    return f"Rain likely! {details}. ~{total_mm:.1f}mm expected"
                return f"Rain likely! {details}"

    except Exception as e:
        log.error(f"Rain check error: {e}")
        return f"Rain check failed: {str(e)[:50]}"


# Active reminders (in-memory, lost on restart)
ACTIVE_REMINDERS: dict[str, asyncio.Task] = {}


async def handle_bin() -> str:
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
        black_week = bin_config.get("black_week", 9)  # Default: week 9 is black
        black_label = bin_config.get("black", "Black bin")
        green_label = bin_config.get("green", "Green bin")

        # Day name to weekday number (monday=0, tuesday=1, etc)
        day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                   "friday": 4, "saturday": 5, "sunday": 6}
        target_weekday = day_map.get(collection_day, 1)  # Default tuesday

        now = datetime.now()
        current_weekday = now.weekday()

        # Find days until collection day
        days_until = (target_weekday - current_weekday) % 7
        # If it's collection day but past evening, show next week
        if days_until == 0 and now.hour >= 20:
            days_until = 7

        collection_date = now + timedelta(days=days_until)
        collection_week = collection_date.isocalendar()[1]

        # Determine which bin based on week parity relative to black_week
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


async def handle_briefing() -> str:
    """Morning briefing: weather, rain, calendar, todos."""
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
    rain = await handle_rain(tomorrow=False)
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
                preview = uncompleted[0][6:][:30]  # First task, 30 chars
                if count == 1:
                    parts.append(f"TODO: {preview}")
                else:
                    parts.append(f"{count} TODOs. First: {preview}")
        except Exception:
            pass

    # Bin day check (if Tuesday - put out night before or on the day)
    if now.weekday() in (0, 1):  # Monday or Tuesday
        bin_info = await handle_bin()
        if "No bin" not in bin_info:
            parts.append(f"BIN: {bin_info}")

    return "\n".join(parts) if parts else "Good morning!"


async def handle_remind(args: str, recipient: str) -> str:
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
            # Try 3pm format
            if 'am' in time_lower or 'pm' in time_lower:
                clean = time_lower.replace('am', ' am').replace('pm', ' pm')
                parsed = datetime.strptime(clean.strip(), "%I %p")
                remind_time = now.replace(hour=parsed.hour, minute=0, second=0, microsecond=0)
            # Try 3:30pm format
            elif ':' in time_str and ('am' in time_lower or 'pm' in time_lower):
                clean = time_lower.replace('am', ' am').replace('pm', ' pm')
                parsed = datetime.strptime(clean.strip(), "%I:%M %p")
                remind_time = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            # Try 24h format (15:30)
            elif ':' in time_str:
                parsed = datetime.strptime(time_str, "%H:%M")
                remind_time = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            # Try just hour (15)
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

    # Calculate delay
    delay_seconds = (remind_time - now).total_seconds()
    if delay_seconds <= 0:
        return "Time must be in the future"

    reminder_id = f"remind_{int(time.time())}"

    async def reminder_callback():
        await asyncio.sleep(delay_seconds)
        log.info(f"Reminder {reminder_id} firing: {message}")
        send_sms_reply(recipient, f"REMINDER: {message}")
        ACTIVE_REMINDERS.pop(reminder_id, None)

    task = asyncio.create_task(reminder_callback())
    ACTIVE_REMINDERS[reminder_id] = task

    time_display = remind_time.strftime("%H:%M")
    if remind_time.date() != now.date():
        time_display = remind_time.strftime("%a %H:%M")

    return f"Reminder set for {time_display}: {message}"


async def process_message(msg: IncomingMessage) -> str:
    """Process incoming message and return response."""
    text = msg.text.strip()

    log.info(f"Processing: {text}")

    # Check for special commands first (exact match, case-insensitive)
    text_upper = text.upper()
    if text_upper == "HELP":
        return """BRIEFING - Morning summary
WEATHER/WEATHER week/RAIN
BIN - Bin day
TODO/DONE 1,2
TIMER 25/REMIND 3pm [msg]
CALL [name]/CONTACT [place]
NAV [from] to [dest]
PING/RESET/LOCATE
INSURANCE/ICE/BORED
Or just ask anything"""
    if text_upper == "RESET":
        log.info("RESET command detected")
        return await handle_reset()
    if text_upper == "PING":
        log.info("PING command detected")
        return await handle_ping()
    if text_upper == "LOCATE":
        log.info("LOCATE command detected")
        return await handle_locate()
    if text_upper == "TODO":
        log.info("TODO read command detected")
        return await handle_todo()
    if text_upper.startswith("TODO "):
        task = text[5:].strip()  # Get everything after "TODO "
        log.info(f"TODO add command detected: {task}")
        return await handle_todo(task)
    if text_upper.startswith("DONE "):
        numbers = text[5:].strip()
        log.info(f"DONE command detected: {numbers}")
        return await handle_done(numbers)
    if text_upper == "WEATHER":
        log.info("WEATHER command detected (default location)")
        return await handle_weather("")
    if text_upper.startswith("WEATHER "):
        location = text[8:].strip()
        log.info(f"WEATHER command detected: {location}")
        return await handle_weather(location)
    if text_upper.startswith("TIMER "):
        minutes = text[6:].strip()
        log.info(f"TIMER command detected: {minutes}")
        return await handle_timer(minutes, msg.sender)
    if text_upper.startswith("CALL "):
        name = text[5:].strip()
        log.info(f"CALL command detected: {name}")
        return await handle_call(name)
    if text_upper.startswith("CONTACT "):
        query = text[8:].strip()
        log.info(f"CONTACT command detected: {query}")
        return await handle_contact(query)
    if text_upper.startswith("NAV "):
        # Parse "NAV from to" - expect "from" and "to" separated by " to "
        parts = text[4:].strip()
        if " to " in parts.lower():
            # Split on " to " (case insensitive)
            idx = parts.lower().index(" to ")
            from_place = parts[:idx].strip()
            to_place = parts[idx + 4:].strip()
            log.info(f"NAV command detected: {from_place} -> {to_place}")
            return await handle_nav(from_place, to_place)
        else:
            return "Usage: NAV [from] to [destination]"
    if text_upper == "BORED":
        log.info("BORED command detected")
        return await handle_bored()
    if text_upper == "RAIN":
        log.info("RAIN command detected")
        return await handle_rain(tomorrow=False)
    if text_upper in ("RAIN TOMORROW", "RAIN TOM"):
        log.info("RAIN TOMORROW command detected")
        return await handle_rain(tomorrow=True)
    if text_upper == "BIN":
        log.info("BIN command detected")
        return await handle_bin()
    if text_upper == "BRIEFING":
        log.info("BRIEFING command detected")
        return await handle_briefing()
    if text_upper.startswith("REMIND "):
        args = text[7:].strip()
        log.info(f"REMIND command detected")
        return await handle_remind(args, msg.sender)
    if text_upper == "INSURANCE":
        log.info("INSURANCE command detected")
        return await handle_insurance()
    if text_upper == "ICE":
        log.info("ICE command detected")
        return await handle_ice()

    # Classify the command via LLM
    command = await classify_command(text)
    log.info(f"Classified as: {command}")

    # Route to handler
    if command == "WEATHER":
        return await handle_weather(text)
    elif command == "SEARCH":
        return await handle_search(text)
    elif command == "MESSAGES":
        return await handle_messages_summary()
    else:  # CHAT
        return await handle_chat(text)


def format_for_sms(message: str) -> str:
    """Format message for dumbphone SMS display.

    - Replaces newlines with ' | ' separators
    - Cleans up list formatting
    - Makes output more compact
    """
    lines = message.split('\n')
    formatted_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Clean up bullet points: "- item" -> "item"
        if line.startswith('- '):
            line = line[2:]
        # Clean up checkbox style: "- [ ] item" -> "item"
        if line.startswith('[ ] '):
            line = line[4:]
        formatted_lines.append(line)

    # Join with separator
    return ' | '.join(formatted_lines)


def split_message(message: str, max_len: int = 160) -> list[str]:
    """Split a long message into SMS-sized chunks, breaking at word boundaries."""
    if len(message) <= max_len:
        return [message]

    # Reserve space for numbering like "(1/3) "
    effective_max = max_len - 7

    chunks = []
    while message:
        if len(message) <= effective_max:
            chunks.append(message)
            break

        # Find last space within limit
        split_at = message.rfind(' ', 0, effective_max)
        if split_at == -1:
            # No space found, hard split
            split_at = effective_max

        chunks.append(message[:split_at].strip())
        message = message[split_at:].strip()

    # Add numbering
    total = len(chunks)
    if total > 1:
        chunks = [f"({i+1}/{total}) {chunk}" for i, chunk in enumerate(chunks)]

    return chunks


def send_sms_reply(recipient: str, message: str):
    """Send SMS reply via Messages.app using AppleScript. Splits long messages."""
    # Convert emojis to text codes if phone doesn't support them
    if not SUPPORTS_EMOJI:
        message = emoji.demojize(message)
    # Format for dumbphone display (newlines -> separators)
    message = format_for_sms(message)
    chunks = split_message(message)
    success = True

    for i, chunk in enumerate(chunks):
        # Escape for AppleScript - handle quotes and backslashes
        escaped_message = chunk.replace('\\', '\\\\')
        escaped_message = escaped_message.replace('"', '\\"')
        escaped_message = escaped_message.replace("'", "'")  # Smart quote
        escaped_message = escaped_message.replace("'", "'")  # Smart quote
        escaped_message = escaped_message.replace(""", '\\"')  # Smart quote
        escaped_message = escaped_message.replace(""", '\\"')  # Smart quote

        applescript = f'''
        tell application "Messages"
            set targetService to 1st account whose service type = SMS
            set targetBuddy to participant "{recipient}" of targetService
            send "{escaped_message}" to targetBuddy
        end tell
        '''

        try:
            result = subprocess.run(
                ["osascript", "-e", applescript],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                log.info(f"Sent SMS {i+1}/{len(chunks)} to {recipient}: {chunk[:40]}...")
            else:
                log.error(f"AppleScript error: {result.stderr}")
                success = False
        except Exception as e:
            log.error(f"Failed to send reply: {e}")
            success = False

        # Delay between chunks to help preserve order
        if i < len(chunks) - 1:
            time.sleep(1.5)

    return success


def get_ack_message(text: str) -> Optional[str]:
    """Return acknowledgement message for long-running commands, or None for quick ones."""
    text_upper = text.strip().upper()

    # Quick commands that don't need acks
    quick_commands = {"HELP", "PING", "TODO", "LOCATE", "WEATHER", "TIMER"}
    if text_upper in quick_commands:
        return None
    if text_upper.startswith("TODO "):
        return None
    if text_upper.startswith("DONE "):
        return None
    if text_upper.startswith("WEATHER "):
        return None
    if text_upper.startswith("TIMER "):
        return None
    if text_upper.startswith("CALL "):
        return None  # Fast local lookup
    if text_upper.startswith("CONTACT "):
        return None  # Fast API lookup
    if text_upper == "BORED":
        return None
    if text_upper == "RAIN" or text_upper.startswith("RAIN "):
        return None
    if text_upper == "BIN":
        return None
    if text_upper == "BRIEFING":
        return "Getting your briefing..."
    if text_upper.startswith("REMIND "):
        return None
    if text_upper == "INSURANCE":
        return None
    if text_upper == "ICE":
        return None

    # Long-running commands get acks
    if text_upper == "RESET":
        return "Resetting Pi Bluetooth..."
    if text_upper == "MESSAGES":
        return "Checking messages..."
    if text_upper.startswith("NAV "):
        return "Getting directions..."

    # Everything else goes to LLM classification/processing
    # Determine likely command for better ack
    text_lower = text.lower()
    if any(word in text_lower for word in ["search", "look up", "find", "what is", "who is"]):
        return "Searching..."
    if any(word in text_lower for word in ["weather", "rain", "temperature", "forecast"]):
        return "Checking weather..."

    # Generic LLM query
    return "Thinking..."


async def preload_model():
    """Preload the Ollama model into memory."""
    log.info(f"Preloading Ollama model: {OLLAMA_MODEL}...")
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Send a simple request to load the model
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": "hi", "stream": False}
            )
            if resp.status_code == 200:
                log.info("Model preloaded successfully")
            else:
                log.warning(f"Model preload failed: {resp.status_code}")
    except Exception as e:
        log.warning(f"Model preload failed: {e}")


async def main():
    """Main polling loop."""
    if not DUMBPHONE_NUMBER:
        log.error("DUMBPHONE_NUMBER environment variable not set")
        log.error("Set it to your dumbphone's phone number, e.g., +441234567890")
        return

    log.info(f"SMS Assistant starting...")
    log.info(f"Monitoring for messages from: {DUMBPHONE_NUMBER}")
    log.info(f"Using Ollama model: {OLLAMA_MODEL}")
    log.info(f"Poll interval: {POLL_INTERVAL}s")

    # Preload model at startup
    await preload_model()

    state = load_state()
    log.info(f"Starting from message ROWID: {state['last_rowid']}")

    while True:
        try:
            update_heartbeat()  # Show we're alive
            messages = get_new_messages(state["last_rowid"])

            for msg in messages:
                log.info(f"New message from {msg.sender}: {msg.text[:50]}...")

                # Send acknowledgement for long-running commands
                ack = get_ack_message(msg.text)
                if ack:
                    log.info(f"Sending ack: {ack}")
                    send_sms_reply(msg.sender, ack)
                    # Track this reply to avoid loop
                    state["recent_replies"] = state.get("recent_replies", [])[-9:] + [ack]

                # Process and get response
                response = await process_message(msg)
                log.info(f"Response: {response}")

                # Send reply
                send_sms_reply(msg.sender, response)

                # Update state
                state["last_rowid"] = msg.rowid
                save_state(state)

            await asyncio.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log.info("Shutting down...")
            break
        except Exception as e:
            log.error(f"Error in main loop: {e}")
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
