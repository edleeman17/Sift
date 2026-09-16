# SMS Assistant Commands

Commands are SMS keywords that trigger specific actions. Send a command via SMS to the dumbphone and receive a response.

## Available Commands

| Command | Args | Description |
|---------|------|-------------|
| `PING` | - | Check Pi + iPhone status (connected, battery %) |
| `RESET` | - | Remote restart of the Pi's BLE stack over SSH (~30s) |
| `EMERGENCY` | `ON`/`OFF` | Toggle emergency mode (shared state with the processor) |
| `TODO` | `[task]` | List open todos, or add a new one, via a REST todo backend |
| `DONE` | `<number>` or `<text>` | Mark a todo complete, by list position or fuzzy text match |
| `WEATHER` | `[place]` or `week` | Current weather or 5-day forecast |
| `RAIN` | `[TOMORROW]` | Precipitation forecast (next 3h or tomorrow) |
| `BIN` | - | Which bin to put out this week |
| `BRIEFING` | - | Morning summary (weather, rain, todos, bin) |
| `REMIND` | `<time> <msg>` | Set a reminder (e.g., "REMIND 3pm call dentist") |
| `TIMER` | `<mins>` | Set countdown timer |
| `CALL` | `<name>` | Fuzzy search contacts, returns phone number(s) |
| `CONTACT` | `<place>` | Business lookup - phone, address, hours (OSM) |
| `NAV` | `<from> to <dest>` | Directions via OSRM |
| `BORED` | - | Weather-aware offline activity suggestion |
| `INSURANCE` | - | Car insurance details |
| `ICE` | - | Emergency info (NHS, NI, blood type, allergies) |
| `RINGGO` | `START`/`EXTEND` | Parking session control (see note in `parking.py`) |
| *(anything else)* | - | `Unknown command: X. Text HELP for a list.` |

There's no LLM fallback - unmatched text doesn't get interpreted, it just
points at `HELP`. `MESSAGES`, `LOCATE` and `SEARCH` from earlier versions
were dropped: `MESSAGES` needed macOS's local `chat.db`, `LOCATE` needed a
Bark instance that isn't part of this setup, and `SEARCH` was Ollama-only.
Add them back in your own fork if you have the dependencies they need.

## Adding a New Command

1. Create a handler function in the appropriate category file (or create a new one)
2. Register it with the `@register_command` decorator
3. Add any required data to `~/.sms-assistant/data.json` if needed

### Example: Adding a QUOTE command

```python
# In commands/utility.py (or create commands/quotes.py)

from commands import register_command
import random

QUOTES = [
    "The only way to do great work is to love what you do. - Steve Jobs",
    "Be the change you wish to see in the world. - Gandhi",
    # ... more quotes
]

@register_command("QUOTE")
async def handle_quote(args: str = "") -> str:
    """Return a random inspirational quote."""
    return random.choice(QUOTES)
```

### Handler Function Signature

```python
@register_command("MYCOMMAND")
async def handle_mycommand(args: str = "") -> str:
    """
    Process MYCOMMAND and return response.

    Args:
        args: Everything after the command keyword (e.g., "MYCOMMAND foo bar" -> args="foo bar")

    Returns:
        String response to send via SMS (will be auto-split if >160 chars)
    """
    # Process args
    result = do_something(args)
    return result
```

### Guidelines

- **Keep responses concise** - SMS has 160 char limit per message
- **Handle errors gracefully** - Return user-friendly error messages
- **Use async** - All handlers should be async for non-blocking I/O
- **No emojis** - Unless `SUPPORTS_EMOJI=true` is set (dumbphones may not display them)
- **Test thoroughly** - Send test SMS to verify formatting

### Accessing Shared Resources

There's no shared `core/` helper module for state or LLM access anymore -
each command file reads what it needs directly from env vars and does
plain HTTP calls:

```python
import os
import httpx
from commands import register_command

DATA_FILE = os.getenv("DATA_FILE", "/app/data/data.json")

@register_command("MYCOMMAND")
async def handle_mycommand(args: str = "") -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get("https://api.example.com/data")
    return resp.text
```

To send an extra SMS outside your return value (e.g. a delayed reminder),
import `send_sms_reply` from `assistant.py` - see how `utility.py`'s
`TIMER`/`REMIND` handlers use it via `commands/utility.py`'s
`set_sms_sender`.

### Data Storage

User-specific data (bin schedules, insurance, ICE info) is stored in the
JSON file pointed at by the `DATA_FILE` env var (`/app/data/data.json` by
default):

```json
{
  "bin": {
    "day": "tuesday",
    "black_week": 9,
    "black": "Black general waste",
    "green": "Green recycling"
  },
  "insurance": "Policy: XXX\nProvider: Admiral\nPhone: 0800...",
  "ice": {
    "nhs": "123 456 7890",
    "ni": "AB 12 34 56 C",
    "blood": "O+",
    "allergies": "None"
  }
}
```

## Command Categories

Commands are organized by function:

- **system.py** - Device management (PING, RESET, EMERGENCY)
- **weather.py** - Weather forecasts (WEATHER, RAIN)
- **todo.py** - Task management (TODO, DONE)
- **info.py** - Personal info (BIN, ICE, INSURANCE, BRIEFING)
- **comms.py** - Communication (CALL, CONTACT)
- **utility.py** - Misc utilities (NAV, TIMER, REMIND, BORED)
- **parking.py** - Parking sessions (RINGGO)

## Testing

There's no local chat.db or Messages.app to poll anymore - commands are
dispatched over HTTP. Either hit the running server directly:

```bash
curl -X POST http://localhost:8091/incoming \
  -H 'Content-Type: application/json' \
  -d '{"text": "WEATHER"}'
```

or call the dispatcher directly for a faster inner loop while writing a
new command:

```bash
cd sms-assistant
python3 -c "
import asyncio
from assistant import process_message
print(asyncio.run(process_message('WEATHER', sender='dumbphone')))
"
```
