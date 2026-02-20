# Sift

*The Dumbphone Companion*

Forward iOS notifications to push services (Bark, ntfy, SMS, iMessage) with intelligent filtering.

## Why This Exists

**The problem:** Smartphones are designed to capture attention. Every app wants to notify you, and the constant interruptions fragment focus and create anxiety. But going completely offline isn't practical - you'd miss genuinely important messages.

**The dumbphone experiment:** Leave your iPhone at home (or in a drawer) and carry a simple phone instead. But stay reachable for what actually matters:

- Emergency messages from family
- Verification codes and 2FA
- Time-sensitive deliveries
- Genuine urgent requests

**This project bridges the gap.** It captures every notification from your iPhone via Bluetooth, applies intelligent filtering rules, and forwards only the important ones to your dumbphone via SMS, or to another device via push notifications.

The result: you're unreachable for noise (group chat banter, social media, marketing) but reachable for emergencies. You check your smartphone on your terms, not when it demands attention.

> **Heads up:** This is a personal project I'm sharing because others might find it useful. It works well for me, but Bluetooth can be finicky and notifications aren't guaranteed to arrive. Test thoroughly with your own setup before relying on it. Don't use this for anything life-critical without verifying it works reliably for you. I'm not responsible if you miss your nan's birthday message.

## Features

- **Rule-based filtering** - Whitelist contacts, keywords, apps with regex support
- **AI classification** - LLM decides importance for ambiguous notifications
- **Sentiment detection** - Urgent messages bypass drop rules automatically (batched for efficiency)
- **Multiple sinks** - Bark (iOS), ntfy, Twilio SMS, iMessage, console
- **Rate limiting** - Per-app cooldowns, deduplication, hourly limits
- **Web dashboard** - Live view of notifications with feedback buttons
- **Learning from feedback** - Rate notifications to improve rules

## Architecture

```
iPhone → (BLE) → Raspberry Pi → (HTTP) → Mac/Server → Sinks
                 (ancs-bridge)           (processor)    ├── Bark (iOS push)
                                              ↓         ├── ntfy
                                           Ollama       ├── Twilio SMS
                                         (optional)     ├── iMessage
                                                        └── Console
```

### Components

1. **Processor** (this repo) - FastAPI service that filters and forwards notifications
2. **ANCS Bridge** - Captures iOS notifications via Bluetooth on a Raspberry Pi
3. **Ollama** (optional) - Local LLM for sentiment detection and AI classification

## Installation

### How It Works

Your iPhone stays at home, connected via Bluetooth to a Raspberry Pi. When a notification arrives, the Pi forwards it to the processor which decides whether to send it to your dumbphone.

**Outbound (notifications to you):**
```
iPhone → Pi (Bluetooth) → Processor → iMessage Gateway → SMS to Dumbphone
```

**Inbound (commands from you):**
```
Dumbphone → SMS → iMessage → SMS Assistant → Response via iMessage → SMS to Dumbphone
```

The Mac acts as an SMS gateway using iMessage - no Twilio account needed if you have a Mac that can send/receive SMS.

### What You'll Need

**Hardware:**
- Raspberry Pi with Bluetooth (Zero 2 W, Pi 3/4/5)
- iPhone (stays at home, within Bluetooth range of Pi)
- Mac (for iMessage SMS gateway and SMS assistant)
- Dumbphone with SMS (Nokia 8210 4G works well)

**Software:**
- Docker (for the processor)
- Ollama (optional, for AI features)

### Setup Steps

#### 1. Raspberry Pi - Bluetooth Bridge

Set up the Pi to capture notifications from your iPhone via Bluetooth.

→ Follow [docs/ancs-bridge-setup.md](docs/ancs-bridge-setup.md)

This involves:
- Installing ancs4linux for BLE
- Pairing with your iPhone
- Running ancs-bridge to forward notifications to the processor

#### 2. Processor - Filtering Engine

Run the processor to filter notifications and decide what to forward.

→ See [Quick Start](#quick-start) below

#### 3. iMessage Gateway - Send SMS from Mac

Run the gateway so the processor can send SMS via your Mac's iMessage.

```bash
cd imessage-gateway
pip install -r requirements.txt
python server.py  # Runs on port 8095
```

Configure as a sink in `config.yaml`:
```yaml
sinks:
  imessage:
    enabled: true
    gateway_url: "http://localhost:8095"
    recipient: "+44YOUR_DUMBPHONE_NUMBER"
```

#### 4. SMS Assistant - Respond to Commands (Optional)

Run the assistant to process commands you text from your dumbphone.

→ See [SMS Assistant](#sms-assistant) below

### The Full Picture

Once set up, you can:
- Leave your iPhone at home and carry your dumbphone
- Receive important notifications as SMS (filtered by your rules)
- Text commands like `WEATHER`, `TODO`, `PING` to your iPhone number
- Get responses via SMS on your dumbphone

## Quick Start

```bash
# Clone and configure
git clone https://github.com/edleeman17/sift.git
cd sift
cp config.example.yaml config.yaml
cp docker-compose.example.yaml docker-compose.yaml

# Edit config.yaml with your rules and sink credentials

# Start services
docker compose up -d

# Pull the LLM model (optional, for AI features)
make pull-model  # pulls qwen2.5:7b
```

Dashboard: http://localhost:8090

## Configuration

### Apps and Rules

Each app can have a default action and specific rules:

```yaml
apps:
  messages:
    default: drop          # Default: drop all messages
    rules:
      - sender_contains: "Mum"
        action: send       # But send messages from Mum
      - body_contains: "urgent"
        action: send       # Or messages containing "urgent"

  discord:
    default: drop
    rules:
      - sender_contains: "SSH Login"
        action: send
        priority: critical  # High priority push notification
      - body_contains: "@yourname"
        action: send
```

### Rule Matchers

| Matcher | Description |
|---------|-------------|
| `sender_contains` | Match text in sender/title |
| `sender_not_contains` | Exclude if text in sender |
| `body_contains` | Match text in message body |
| `body_not_contains` | Exclude if text in body |
| `contains` | Match text anywhere (sender or body) |
| `sender_regex` | Regex pattern on sender/title |
| `body_regex` | Regex pattern on body |
| `regex` | Regex pattern anywhere |

### Actions

| Action | Description |
|--------|-------------|
| `send` | Always forward to sinks |
| `drop` | Never forward (but may be overridden by sentiment detection) |
| `llm` | Let AI decide (requires Ollama) |

### Global Settings

```yaml
global:
  unknown_apps: drop       # What to do with unlisted apps

  rate_limit:
    max_per_hour: 50       # Max notifications per hour per app/sender
    cooldown_seconds: 30   # Min seconds between notifications from same sender
    app_dedup_hours:       # Per-app duplicate detection window
      reminders: 24        # Reminders dedupe for 24 hours
    no_cooldown_apps:      # Skip cooldown but keep deduplication
      - signal             # Allow rapid Signal messages
    exempt_apps:           # Skip all rate limiting entirely
      - phone              # Never rate limit phone calls

  sentiment_detection:
    enabled: true
    batch_window_seconds: 60  # Collect dropped messages for 60s before LLM call
    max_batch_size: 30        # Or process immediately at 30 messages
    apps:                     # Only check these apps for urgency
      - whatsapp
      - messages
      - signal

  rules:                   # Global rules apply to ALL apps first
    - body_regex: "(verification|security) code"
      action: send
    - sender_contains: "Mum"
      action: send
    - sender_contains: "Dad"
      action: send
```

Global rules are evaluated **before** app-specific rules, useful for:
- Verification codes from any app
- VIP contacts across all messaging apps
- Security alerts

### Sinks

```yaml
sinks:
  console:
    enabled: true

  bark:
    enabled: true
    url: "http://bark.example.com"
    device_key: "your-device-key"

  ntfy:
    enabled: true
    url: "https://ntfy.sh/your-topic"

  twilio:
    enabled: true
    account_sid: "ACxxxxx"
    auth_token: "xxxxx"
    from_number: "+15551234567"
    to_number: "+15559876543"

  imessage:
    enabled: true
    gateway_url: "http://host.docker.internal:8095"
    recipient: "+15559876543"
```

## Sentiment Detection

When enabled, messages that would be dropped get a final check for genuine urgency. This catches emergencies like "HELP call 999" even from apps/contacts you've set to drop.

### How it works

1. Message matches a drop rule or app default
2. If sender is not a group chat (no `~`, `Group`, or `,` in title)
3. Message is queued for sentiment analysis
4. After batch window (default 60s), all queued messages are sent to LLM in one call
5. Messages classified as URGENT are sent; others are dropped

### Batching

Multiple rapid messages are processed together efficiently:

```
[0s]  Message 1 arrives → queued
[5s]  Message 2 arrives → queued
[30s] Message 3 arrives → queued
[60s] Batch window expires → single LLM call for all 3
      → Message 2 is URGENT → sent
      → Messages 1 & 3 are NORMAL → dropped
```

This reduces LLM calls from 3 to 1, saving time and resources.

### Group Chat Handling

Group chats are automatically excluded from sentiment detection:
- WhatsApp groups have `~` prefix in title
- Other groups often have `Group` or commas in title

Group messages are dropped immediately without LLM calls.

## Rate Limiting

Three layers of protection against notification spam:

| Feature | Description | Config |
|---------|-------------|--------|
| **Cooldown** | Min time between messages from same app/sender | `cooldown_seconds: 30` |
| **Hourly limit** | Max messages per app/sender per hour | `max_per_hour: 50` |
| **Deduplication** | Block identical messages within window | `app_dedup_hours` or 5 min default |

### Exemptions

```yaml
rate_limit:
  no_cooldown_apps:    # Skip cooldown, keep deduplication
    - signal           # Rapid consecutive messages OK, duplicates blocked
  exempt_apps:         # Skip all rate limiting
    - phone            # Never block phone calls
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PI_HEALTH_URL` | (empty) | URL to Pi's ancs-bridge health endpoint |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama API URL |

## Dashboard

Web dashboard at `http://localhost:8090`:

- **Connection Status** - iPhone Bluetooth connection state
- **Stats** - Total/sent/dropped/rate-limited counts
- **Recent Notifications** - Filterable list with feedback buttons
- **AI Analysis** - Click "Analyze with AI" for rule suggestions

### Feedback Loop

Mark notifications as incorrect to improve rules:

| Scenario | Action | Result |
|----------|--------|--------|
| Sent but shouldn't be | Click thumbs down | Suggests drop rule |
| Dropped but should send | Click thumbs down | Suggests send rule |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard |
| `/rules` | GET | Rules management page |
| `/health` | GET | Health check |
| `/notification` | POST | Receive notification |
| `/api/rules` | GET/POST/DELETE | Manage rules |
| `/api/insights/ai` | GET | AI-powered analysis |
| `/feedback/{id}` | POST | Set notification feedback |

## Makefile Commands

```bash
make build      # Build containers
make up         # Start services
make down       # Stop services
make logs       # Follow processor logs
make restart    # Restart processor
make rebuild    # Rebuild and restart processor
make pull-model # Pull qwen2.5:7b for Ollama
make test       # Send test notification
make health     # Check health endpoint
```

## Running Without LLM

The system works without Ollama - disable AI features:

```yaml
global:
  sentiment_detection:
    enabled: false
```

Use explicit rules instead of `action: llm`.

## Adding Custom Sinks

Create a new sink by implementing the `NotificationSink` interface:

```python
# processor/sinks/my_sink.py
from models import Message
from .base import NotificationSink

class MySink(NotificationSink):
    def __init__(self, api_key: str, enabled: bool = True):
        self._api_key = api_key
        self._enabled = enabled

    @property
    def name(self) -> str:
        return "my_sink"

    async def send(self, msg: Message) -> bool:
        # Send notification, return True on success
        pass

    def is_enabled(self) -> bool:
        return self._enabled
```

Then register in `sinks/__init__.py` and initialize in `main.py` lifespan.

## Raspberry Pi Setup

See [ancs-bridge documentation](docs/ancs-bridge-setup.md) for Bluetooth setup.

## SMS Assistant

A companion service that runs on macOS, monitoring incoming SMS from your dumbphone and responding to commands. This turns your dumbphone into a remote control for your smart home setup.

### Commands

| Command | Description |
|---------|-------------|
| `PING` | Check Pi + iPhone status (connected, battery %, last notification) |
| `RESET` | Remote restart of BLE stack on Pi (~30s) |
| `LOCATE` | Send loud alarm to iPhone via Bark (critical priority, bypasses silent mode) |
| `TODO` | List uncompleted tasks from Obsidian |
| `TODO [task]` | Add new task |
| `DONE 1,2,3` | Mark tasks complete by number |
| `WEATHER` | Current weather + sunrise/sunset |
| `WEATHER week` | 5-day forecast |
| `WEATHER [place]` | Weather for any location |
| `RAIN` | Precipitation next 3 hours |
| `RAIN TOMORROW` | Tomorrow's rain forecast |
| `BIN` | Which bin to put out this week |
| `BRIEFING` | Morning summary (weather, rain, todos, bin) |
| `REMIND [time] [msg]` | "REMIND 3pm call dentist" - texts at that time |
| `TIMER [mins]` | Set countdown timer, texts when done |
| `CALL [name]` | Fuzzy search your contacts, returns phone number(s) |
| `CONTACT [place]` | Business lookup - phone, address, hours |
| `NAV [from] to [dest]` | Prose driving directions |
| `BORED` | Weather-aware offline activity suggestion |
| `INSURANCE` | Car insurance details |
| `ICE` | Emergency info (NHS, NI, blood type, allergies) |
| `SEARCH [query]` | DuckDuckGo instant answer |
| `MESSAGES` | Summarize unread messages (last 24h) |
| *(anything else)* | Chat with local LLM |

### Setup

```bash
cd sms-assistant
pip install -r requirements.txt

# Set environment variables
export DUMBPHONE_NUMBER="+441234567890"
export PI_HOST="pi@192.168.1.100"
export OLLAMA_MODEL="qwen2.5:7b"
export DEFAULT_LAT="51.5074"  # For rain/weather
export DEFAULT_LON="-0.1278"
export CONTACTS_FILE="~/sift/contacts.json"

# Run
python assistant.py

# Or install as launchd service
cp com.notif-fwd.sms-assistant.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.notif-fwd.sms-assistant.plist
```

### Data File

Personal data stored in `~/.sms-assistant/data.json`:

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

### How It Works

1. Polls macOS Messages.app SQLite database every 10 seconds
2. Filters for messages from your dumbphone number
3. Parses command or sends to LLM for general chat
4. Replies via AppleScript through Messages.app SMS
5. Long messages are split into 160-char SMS chunks

### Example Session

```
You: BRIEFING
Bot: Friday 20 February
     ☀️ 12°C, 0% rain
     3 TODOs. First: Call dentist
     BIN: Tuesday: Black general waste

You: RAIN TOMORROW
Bot: Tomorrow: Low chance of rain (25%)

You: REMIND 3pm call dentist
Bot: Reminder set for 15:00: call dentist

You: BORED
Bot: It's sunny. Walk to the sea and watch the waves

You: BIN
Bot: Tuesday: Black general waste

You: CALL dad
Bot: Dad: +44123456789

You: NAV home to kings cross
Bot: Getting directions...
Bot: Home to Kings Cross (5.1km, ~15 min):
     1. Head north on A1
     2. Continue through Islington
     3. Arrive at Kings Cross
     ...

You: TIMER 25
Bot: Timer set for 25 min
... 25 minutes later ...
Bot: TIMER: 25 min timer complete!
```

## iMessage Gateway

Separate HTTP service for sending SMS via macOS Messages.app:

```bash
cd imessage-gateway
pip install -r requirements.txt
python server.py  # Runs on port 8095
```

Endpoints:
- `POST /send` - Send SMS (`{"recipient": "+44...", "message": "..."}`)
- `GET /health` - Health check

## License

MIT

## Acknowledgments

- [Ben Vallack](https://github.com/benvallack) - Inspiration for the dumbphone experiment and ideas around intentional tech use
- [ancs4linux](https://github.com/pzmarzly/ancs4linux) - ANCS Bluetooth implementation
- [Bark](https://github.com/Finb/Bark) - iOS push notification service
- [ntfy](https://ntfy.sh) - Push notification service
- [Ollama](https://ollama.ai) - Local LLM runtime
