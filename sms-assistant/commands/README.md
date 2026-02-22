# SMS Assistant Commands

Commands are SMS keywords that trigger specific actions. Send a command via SMS to the dumbphone and receive a response.

## Available Commands

| Command | Args | Description |
|---------|------|-------------|
| `PING` | - | Check Pi + iPhone status (connected, battery %, last notification) |
| `RESET` | - | Remote restart of BLE stack on Pi (~30s) |
| `LOCATE` | - | Send loud alarm to iPhone via Bark (critical priority) |
| `TODO` | `[task]` | List tasks, or add a new task |
| `DONE` | `1,2,3` | Mark tasks complete by number |
| `WEATHER` | `[place]` or `week` | Current weather or 5-day forecast |
| `RAIN` | `[TOMORROW]` | Precipitation forecast (next 3h or tomorrow) |
| `BIN` | - | Which bin to put out this week |
| `BRIEFING` | - | Morning summary (weather, rain, todos, bin) |
| `REMIND` | `<time> <msg>` | Set a reminder (e.g., "REMIND 3pm call dentist") |
| `TIMER` | `<mins>` | Set countdown timer |
| `CALL` | `<name>` | Fuzzy search contacts, returns phone number(s) |
| `CONTACT` | `<place>` | Business lookup - phone, address, hours (OSM) |
| `NAV` | `<from> to <dest>` | Prose directions via OSRM + LLM |
| `BORED` | - | Weather-aware offline activity suggestion |
| `INSURANCE` | - | Car insurance details |
| `ICE` | - | Emergency info (NHS, NI, blood type, allergies) |
| `SEARCH` | `<query>` | DuckDuckGo instant answer |
| `MESSAGES` | - | Summarize unread messages (last 24h) |
| *(anything else)* | - | Chat with LLM |

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

```python
from core.llm import ollama_generate  # LLM queries
from core.state import load_data, save_data  # User data
from core.messages import send_sms_reply  # Send additional SMS

# For HTTP requests
import httpx
async with httpx.AsyncClient() as client:
    resp = await client.get("https://api.example.com/data")
```

### Data Storage

User-specific data (bin schedules, insurance, ICE info) is stored in `~/.sms-assistant/data.json`:

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

- **system.py** - Device management (PING, RESET, LOCATE)
- **weather.py** - Weather forecasts (WEATHER, RAIN)
- **todo.py** - Task management (TODO, DONE)
- **info.py** - Personal info (BIN, ICE, INSURANCE, BRIEFING)
- **comms.py** - Communication (CALL, CONTACT, MESSAGES)
- **utility.py** - Misc utilities (NAV, TIMER, REMIND, SEARCH, BORED)

## Testing

```bash
# Manually trigger a command (via the processing function)
cd sms-assistant
python3 -c "
import asyncio
from assistant import process_message
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Msg:
    rowid: int = 1
    text: str = 'WEATHER'
    timestamp: datetime = datetime.now()
    sender: str = '+441234567890'

print(asyncio.run(process_message(Msg())))
"
```
