"""Communication commands: CALL, CONTACT, MESSAGES."""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from commands import register_command

log = logging.getLogger(__name__)

CONTACTS_FILE = Path(os.getenv("CONTACTS_FILE", os.path.expanduser("~/docker-projects/notification-forwarder/contacts.json")))
MESSAGES_DB = Path(os.getenv("MESSAGES_DB", os.path.expanduser("~/Library/Messages/chat.db")))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")


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


@register_command("CALL")
async def handle_call(args: str = "") -> str:
    """Lookup phone number with fuzzy matching."""
    if not args:
        return "Usage: CALL [name]"

    contacts = load_contacts()
    if not contacts:
        return "No contacts file found"

    matches = fuzzy_match_contacts(args, contacts)

    if not matches:
        return f"No matches for '{args}'"

    # Perfect or near-perfect match - return single result
    if matches[0][2] >= 0.95:
        name, number, _ = matches[0]
        return f"{name}: {number}"

    # Multiple fuzzy matches - return top 5
    top = matches[:5]
    lines = [f"{name}: {number}" for name, number, _ in top]
    return "\n".join(lines)


@register_command("CONTACT")
async def handle_contact(args: str = "") -> str:
    """Lookup business/place contact details (phone, address, hours)."""
    if not args:
        return "Usage: CONTACT [place name]"

    log.info(f"CONTACT lookup: {args}")

    # Add location context if not specified
    search_query = args
    if "uk" not in args.lower():
        search_query = f"{args} UK"

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
                return f"No results for '{args}'"

            results = []
            for place in resp.json():
                name = place.get("name", place.get("display_name", "").split(",")[0])
                address = place.get("display_name", "")
                # Shorten address - take first 3 parts
                address_parts = address.split(",")[:3]
                short_address = ", ".join(p.strip() for p in address_parts)

                extra = place.get("extratags", {})
                phone = extra.get("phone", extra.get("contact:phone", ""))
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
                return f"No details found for '{args}'"

            return results[0] if len(results) == 1 else "\n---\n".join(results[:2])

    except Exception as e:
        log.error(f"CONTACT error: {e}")
        return f"Lookup failed: {str(e)[:80]}"


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


@register_command("MESSAGES")
async def handle_messages(args: str = "") -> str:
    """Summarize recent unread messages."""
    try:
        conn = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Get recent unread messages (is_read = 0, is_from_me = 0)
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
