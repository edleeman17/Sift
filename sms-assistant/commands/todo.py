"""Task commands: TODO, DONE.

Rewritten to hit ingest.lan (a general life-inbox app already running on
the cluster - see GET /openapi.json there for the full API) instead of an
Obsidian _todo.md file, which no longer exists on this setup. TODO reads
across every item with status "todo" regardless of its `source` (dictation,
raycast, ios-text, ...) - this is meant to be your one general todo list,
not a phone-only one. New items added here are tagged source=sms-assistant
so they're identifiable in ingest's own UI later.
"""

import logging
import os
from difflib import SequenceMatcher

import httpx

from commands import register_command

log = logging.getLogger(__name__)

INGEST_URL = os.getenv("INGEST_URL", "https://ingest.lan")


@register_command("TODO")
async def handle_todo(args: str = "") -> str:
    """List open todos, or add a new one.

    TODO            List open todos (most recent first)
    TODO [task]      Add a new todo
    """
    if not args:
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                resp = await client.get(f"{INGEST_URL}/api/items", params={"status": "todo", "limit": 20})
                if resp.status_code != 200:
                    return f"Todo list unavailable: HTTP {resp.status_code}"
                items = resp.json().get("items", [])
        except Exception as e:
            log.error(f"TODO list error: {e}")
            return f"Todo list unavailable: {str(e)[:60]}"

        if not items:
            return "No open TODOs"

        lines = []
        for i, item in enumerate(items):
            text = item.get("summary") or item.get("raw_text") or ""
            lines.append(f"{i + 1}. {text[:60]}")
        return "\n".join(lines)

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            resp = await client.post(
                f"{INGEST_URL}/ingest",
                json={"source": "sms-assistant", "raw_text": args},
            )
            if resp.status_code != 200:
                return f"Failed to add: HTTP {resp.status_code}"
            log.info(f"Added TODO via ingest.lan: {args}")
            return f"Added: {args[:100]}"
    except Exception as e:
        log.error(f"TODO add error: {e}")
        return f"Failed to add TODO: {str(e)[:80]}"


@register_command("DONE")
async def handle_done(args: str = "") -> str:
    """Mark a todo as complete by number (from the last TODO list) or by
    matching text.

    DONE 2          Mark item #2 from the last TODO list as done
    DONE muji       Mark the todo matching "muji" as done
    """
    if not args:
        return "Usage: DONE [number from TODO list] or DONE [matching text]"

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            resp = await client.get(f"{INGEST_URL}/api/items", params={"status": "todo", "limit": 20})
            if resp.status_code != 200:
                return f"Todo list unavailable: HTTP {resp.status_code}"
            items = resp.json().get("items", [])
    except Exception as e:
        log.error(f"DONE lookup error: {e}")
        return f"Todo list unavailable: {str(e)[:60]}"

    if not items:
        return "No open TODOs"

    target = None

    # Numeric - index into the same ordering TODO would have shown
    if args.strip().isdigit():
        idx = int(args.strip()) - 1
        if 0 <= idx < len(items):
            target = items[idx]
        else:
            return f"Invalid number. You have {len(items)} open TODOs."
    else:
        # Fuzzy match against summary/raw_text
        query = args.strip().lower()
        best_score = 0.0
        for item in items:
            text = (item.get("summary") or item.get("raw_text") or "").lower()
            if query in text:
                score = 0.9
            else:
                score = SequenceMatcher(None, query, text).ratio()
            if score > best_score:
                best_score = score
                target = item
        if best_score < 0.3:
            target = None

    if not target:
        return f"No matching TODO for '{args}'"

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            resp = await client.patch(
                f"{INGEST_URL}/api/items/{target['id']}",
                json={"status": "done"},
            )
            if resp.status_code != 200:
                return f"Failed to complete: HTTP {resp.status_code}"
    except Exception as e:
        log.error(f"DONE patch error: {e}")
        return f"Failed: {str(e)[:80]}"

    text = (target.get("summary") or target.get("raw_text") or "")[:40]
    return f"Done: {text}"
