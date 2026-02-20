#!/usr/bin/env python3
"""iMessage Gateway - HTTP server that sends SMS via Messages.app."""

import logging
import os
import subprocess
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

PORT = int(os.getenv("IMESSAGE_GATEWAY_PORT", "8095"))
DEFAULT_RECIPIENT = os.getenv("DEFAULT_RECIPIENT", "")  # e.g., "+441234567890"


def send_imessage(recipient: str, message: str) -> tuple[bool, str]:
    """Send SMS/iMessage via Messages.app using AppleScript."""
    # Escape special characters for AppleScript
    # Replace smart quotes and other problematic characters
    escaped_message = message.replace('\\', '\\\\')
    escaped_message = escaped_message.replace('"', '\\"')
    escaped_message = escaped_message.replace("'", "'")  # Smart single quote
    escaped_message = escaped_message.replace("'", "'")  # Smart single quote
    escaped_message = escaped_message.replace(""", '\\"')  # Smart double quote
    escaped_message = escaped_message.replace(""", '\\"')  # Smart double quote

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
            timeout=15
        )

        if result.returncode == 0:
            log.info(f"Sent to {recipient}: {message[:50]}...")
            return True, "sent"
        else:
            error = result.stderr.strip()
            log.error(f"AppleScript error: {error}")
            return False, error

    except subprocess.TimeoutExpired:
        log.error("AppleScript timeout")
        return False, "timeout"
    except Exception as e:
        log.error(f"Failed to send: {e}")
        return False, str(e)


async def health_handler(request):
    """Health check endpoint."""
    return web.json_response({"status": "healthy", "service": "imessage-gateway"})


async def send_handler(request):
    """
    POST /send
    Body: {"recipient": "+441234567890", "message": "Hello"}

    If recipient not provided, uses DEFAULT_RECIPIENT env var.
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    message = data.get("message", "").strip()
    if not message:
        return web.json_response({"error": "message required"}, status=400)

    recipient = data.get("recipient", "").strip() or DEFAULT_RECIPIENT
    if not recipient:
        return web.json_response({"error": "recipient required (or set DEFAULT_RECIPIENT)"}, status=400)

    success, detail = send_imessage(recipient, message)

    if success:
        return web.json_response({"status": "sent", "recipient": recipient})
    else:
        return web.json_response({"status": "failed", "error": detail}, status=500)


async def init_app():
    """Initialize the web application."""
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_post("/send", send_handler)
    return app


def main():
    log.info(f"iMessage Gateway starting on port {PORT}")
    if DEFAULT_RECIPIENT:
        log.info(f"Default recipient: {DEFAULT_RECIPIENT}")
    else:
        log.info("No default recipient set - must provide in each request")

    app = init_app()
    web.run_app(app, host="0.0.0.0", port=PORT, print=None)


if __name__ == "__main__":
    main()
