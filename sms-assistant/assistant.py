#!/usr/bin/env python3
"""SMS Assistant - Process incoming SMS via Messages.app and respond with LLM."""

import asyncio
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import emoji
import httpx

# Import commands module to trigger registration via decorators
import commands
from commands import get_command_handler
from commands.utility import set_sms_sender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# Configuration
DUMBPHONE_NUMBER = os.getenv("DUMBPHONE_NUMBER", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
MESSAGES_DB = Path(os.getenv("MESSAGES_DB", os.path.expanduser("~/Library/Messages/chat.db")))
STATE_FILE = Path(os.getenv("STATE_FILE", os.path.expanduser("~/.sms-assistant/state.json")))
HEARTBEAT_FILE = Path(os.getenv("HEARTBEAT_FILE", os.path.expanduser("~/.sms-assistant/heartbeat")))
SUPPORTS_EMOJI = os.getenv("SUPPORTS_EMOJI", "false").lower() in ("true", "1", "yes")

# Command types for LLM classification fallback
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


async def handle_chat(query: str) -> str:
    """General chat/Q&A with LLM."""
    system = """You are a helpful SMS assistant. Be concise but thorough.
No markdown formatting. Plain text only."""

    return await ollama_generate(query, system)


async def process_message(msg: IncomingMessage) -> str:
    """Process incoming message and return response."""
    text = msg.text.strip()
    text_upper = text.upper()

    log.info(f"Processing: {text}")

    # HELP is handled specially (not a registered command)
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

    # Parse command and args
    parts = text_upper.split(maxsplit=1)
    command_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    # Special handling for RAIN TOMORROW variant
    if text_upper in ("RAIN TOMORROW", "RAIN TOM"):
        command_name = "RAIN"
        args = "TOMORROW"

    # Look up handler in registry
    handler = get_command_handler(command_name)
    if handler:
        log.info(f"{command_name} command detected")
        # Commands that need recipient for async callbacks
        if command_name in ("TIMER", "REMIND"):
            return await handler(args, recipient=msg.sender)
        return await handler(args)

    # Classify via LLM for natural language queries
    command = await classify_command(text)
    log.info(f"Classified as: {command}")

    handler = get_command_handler(command)
    if handler:
        return await handler(text)

    # Fallback to chat
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

    # Set up SMS sender for commands that need async callbacks
    set_sms_sender(send_sms_reply)

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
