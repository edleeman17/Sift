"""Communication commands: CALL, CONTACT.

MESSAGES (unread-message summary) dropped - it read Messages.app's local
chat.db directly, which doesn't exist on Linux and has no equivalent here.
"""

import json
import logging
import os
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from commands import register_command

log = logging.getLogger(__name__)

CONTACTS_FILE = Path(os.path.expanduser(os.getenv("CONTACTS_FILE", "/app/contacts.json")))
DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "51.5074"))
DEFAULT_LON = float(os.getenv("DEFAULT_LON", "-0.1278"))


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

    # Get all high-confidence matches (score >= 0.9)
    high_matches = [(n, num, s) for n, num, s in matches if s >= 0.9]

    if len(high_matches) == 1:
        name, number, _ = high_matches[0]
        return f"{name}: {number}"

    if high_matches:
        top = high_matches[:5]
    else:
        top = matches[:5]

    lines = [f"{name}: {number}" for name, number, _ in top]
    return "\n".join(lines)


@register_command("CONTACT")
async def handle_contact(args: str = "") -> str:
    """Lookup business/place contact details (phone, address, hours)."""
    if not args:
        return "Usage: CONTACT [place name]"

    log.info(f"CONTACT lookup: {args}")

    # Create viewbox around default location (~50km radius)
    # viewbox format: west,north,east,south (lon,lat,lon,lat)
    viewbox_delta = 0.5  # ~50km at UK latitudes
    viewbox = f"{DEFAULT_LON - viewbox_delta},{DEFAULT_LAT + viewbox_delta},{DEFAULT_LON + viewbox_delta},{DEFAULT_LAT - viewbox_delta}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # First try with viewbox for local results
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": args,
                    "format": "json",
                    "limit": 3,
                    "addressdetails": 1,
                    "extratags": 1,
                    "viewbox": viewbox,
                    "bounded": 0,  # Prefer but don't restrict to viewbox
                },
                headers={"User-Agent": "sms-assistant/1.0"}
            )

            # If no results, try broader UK search
            if resp.status_code == 200 and not resp.json():
                log.info(f"CONTACT: no local results, trying UK-wide search")
                resp = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": f"{args} UK",
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


