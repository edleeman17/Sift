#!/usr/bin/env python3
"""SMS Assistant - reverse channel for the dumbphone: text a command, get a reply.

Rewritten from the original macOS version, which polled Messages.app's
local chat.db every 10s and replied via AppleScript - neither is possible
on Linux. This version is event-driven instead: a Shortcuts "Message"
Personal Automation on the iPhone (trigger: Message from the dumbphone's
number, Run Immediately) POSTs the text straight to /incoming here, no
polling needed. Replies go out via sift-sms-gateway's existing /send
(the same email->Shortcuts->Send Message path already proven for outgoing
notifications), not AppleScript.

Command dispatch (commands/*.py, COMMAND_REGISTRY) is mostly unchanged
from the original - most commands were already portable API calls, not
Mac-specific. Ollama-dependent natural-language fallback has been dropped
entirely (no Ollama deployed for this yet) - unmatched text just gets a
"try HELP" reply instead of falling through to chat.
"""
import logging
import os
import sys

import emoji
import httpx
from fastapi import FastAPI
from pydantic import BaseModel

import commands
from commands import get_command_handler
from commands.utility import set_sms_sender

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://sift-sms-gateway.service.consul:8095")
SUPPORTS_EMOJI = os.getenv("SUPPORTS_EMOJI", "false").lower() in ("true", "1", "yes")

app = FastAPI(title="sift-sms-assistant")


class IncomingRequest(BaseModel):
    text: str


def format_for_sms(message: str) -> str:
    """Dumbphone-friendly formatting: strip markdown-ish list prefixes, join with ' | '."""
    lines = message.split("\n")
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("- "):
            line = line[2:]
        if line.startswith("[ ] "):
            line = line[4:]
        formatted_lines.append(line)
    return " | ".join(formatted_lines)


def split_message(message: str, max_len: int = 160) -> list[str]:
    """Split a long message into SMS-sized chunks, preferring newline breaks."""
    if "\n" in message:
        lines = [line.strip() for line in message.split("\n") if line.strip()]
        if all(len(line) <= max_len for line in lines):
            return lines

    if len(message) <= max_len:
        return [message]

    effective_max = max_len - 7
    chunks = []
    while message:
        if len(message) <= effective_max:
            chunks.append(message)
            break
        split_at = message.rfind("\n", 0, effective_max)
        if split_at == -1:
            split_at = message.rfind(" ", 0, effective_max)
        if split_at == -1:
            split_at = effective_max
        chunks.append(message[:split_at].strip())
        message = message[split_at:].strip()

    total = len(chunks)
    if total > 1:
        chunks = [f"({i + 1}/{total}) {chunk}" for i, chunk in enumerate(chunks)]
    return chunks


def send_sms_reply(recipient: str, message: str):
    """Send a reply via sift-sms-gateway (email -> Shortcuts -> Send Message),
    not AppleScript. `recipient` is accepted for API-compatibility with the
    command handlers (TIMER/REMIND pass msg.sender) but isn't otherwise used -
    same as the gateway's own /send contract, the dumbphone number is fixed
    on the phone side."""
    if not SUPPORTS_EMOJI:
        message = emoji.demojize(message)
    message = format_for_sms(message)
    chunks = split_message(message)

    for i, chunk in enumerate(chunks):
        try:
            resp = httpx.post(
                f"{GATEWAY_URL}/send",
                json={"recipient": recipient, "message": chunk},
                timeout=15.0,
            )
            if resp.status_code == 200:
                log.info(f"Sent reply {i + 1}/{len(chunks)}: {chunk[:40]}...")
            else:
                log.error(f"Gateway error sending reply: {resp.status_code} {resp.text}")
        except Exception as e:
            log.error(f"Failed to send reply chunk: {e}")


set_sms_sender(send_sms_reply)


async def process_message(text: str, sender: str) -> str:
    """Parse and dispatch a command. Unmatched text gets a HELP pointer -
    no LLM fallback (see module docstring)."""
    text = text.strip()
    text_upper = text.upper()
    log.info(f"Processing: {text}")

    parts = text_upper.split(maxsplit=1)
    command_name = parts[0] if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    if text_upper in ("RAIN TOMORROW", "RAIN TOM"):
        command_name, args = "RAIN", "TOMORROW"

    handler = get_command_handler(command_name)
    if handler:
        log.info(f"{command_name} command detected")
        if command_name in ("TIMER", "REMIND"):
            return await handler(args, recipient=sender)
        return await handler(args)

    return f"Unknown command: {command_name}. Text HELP for a list."


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/incoming")
async def incoming(req: IncomingRequest):
    """Hit by the iPhone's Shortcuts 'Message' automation with the dumbphone's
    text content. Dispatches the command and sends the reply via the gateway -
    doesn't wait on the reply's own delivery to respond to the caller."""
    reply = await process_message(req.text, sender="dumbphone")
    send_sms_reply("dumbphone", reply)
    return {"status": "ok", "reply": reply}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8091))
    uvicorn.run(app, host="0.0.0.0", port=port)
