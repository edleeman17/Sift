<h1 align="center">【 SIFT 】</h1>

<p align="center">
  <strong>The Dumbphone Companion</strong><br>
  <em>Escape your smartphone. Stay reachable for what matters.</em>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#features">Features</a> •
  <a href="#sms-assistant">SMS Assistant</a> •
  <a href="#configuration">Configuration</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License" />
  <img src="https://img.shields.io/badge/python-3.10+-green.svg" alt="Python" />
  <img src="https://img.shields.io/badge/docker-ready-blue.svg" alt="Docker" />
</p>

---

## The Problem

Smartphones are designed to capture attention. Every app wants to notify you, and the constant interruptions fragment focus and create anxiety.

But going completely offline isn't practical—you'd miss genuinely important messages.

## The Solution

**Leave your iPhone at home. Carry a dumbphone instead.**

Sift bridges the gap by capturing every notification from your iPhone via Bluetooth, applying intelligent filtering rules, and forwarding only the important ones to your dumbphone via SMS.

```
📱 iPhone (at home)
    ↓ Bluetooth
🍓 Raspberry Pi
    ↓ HTTP
💻 Processor (filters notifications)
    ↓
📟 Dumbphone (in your pocket)
```

**The result:** You're unreachable for noise (group chat banter, social media, marketing) but reachable for emergencies. You check your smartphone on your terms, not when it demands attention.

> [!NOTE]
> This is a personal project I'm sharing because others might find it useful. Bluetooth can be finicky and notifications aren't guaranteed. Test thoroughly before relying on it for anything important.

---

## Features

| Feature | Description |
|---------|-------------|
| **Rule-based filtering** | Whitelist contacts, keywords, apps with regex support |
| **AI classification** | Local LLM decides importance for ambiguous messages |
| **Sentiment detection** | Urgent messages bypass drop rules ("HELP call 999") |
| **Multiple sinks** | Bark, ntfy, Twilio SMS, iMessage, console |
| **Rate limiting** | Per-app cooldowns, deduplication, hourly limits |
| **Web dashboard** | Live view with feedback buttons to improve rules |
| **SMS commands** | Text commands to your iPhone from your dumbphone |

---

## Quick Start

```bash
git clone https://github.com/edleeman17/sift.git
cd sift
cp config.example.yaml config.yaml
cp docker-compose.example.yaml docker-compose.yaml

# Edit config.yaml with your rules and credentials

docker compose up -d
```

Dashboard: **http://localhost:8090**

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         YOUR HOME                                   │
│                                                                     │
│   ┌──────────┐    Bluetooth    ┌──────────────┐                    │
│   │  iPhone  │ ──────────────► │ Raspberry Pi │                    │
│   │ (drawer) │                 │ (ancs-bridge)│                    │
│   └──────────┘                 └──────┬───────┘                    │
│                                       │ HTTP                        │
│                                       ▼                             │
│   ┌──────────┐                 ┌──────────────┐     ┌────────────┐ │
│   │  Ollama  │◄───────────────►│  Processor   │────►│  iMessage  │ │
│   │(optional)│   AI classify   │  (filtering) │     │  Gateway   │ │
│   └──────────┘                 └──────────────┘     └─────┬──────┘ │
│                                                           │ SMS    │
└───────────────────────────────────────────────────────────┼────────┘
                                                            ▼
                                                     ┌────────────┐
                                                     │ Dumbphone  │
                                                     │(your pocket)│
                                                     └────────────┘
```

### Notification Flow

1. **Capture** — iPhone notification triggers Bluetooth event
2. **Forward** — Raspberry Pi sends to processor via HTTP
3. **Filter** — Rules engine evaluates: send, drop, or ask AI
4. **Deliver** — Approved notifications go to your configured sinks

### Two-Way Communication

**Outbound (notifications to you):**
```
iPhone → Pi (BLE) → Processor → iMessage Gateway → SMS → Dumbphone
```

**Inbound (commands from you):**
```
Dumbphone → SMS → Mac (iMessage) → SMS Assistant → Response → Dumbphone
```

---

## What You'll Need

### Hardware

| Component | Purpose | Recommendation |
|-----------|---------|----------------|
| Raspberry Pi | Bluetooth bridge | Zero 2 W, Pi 3/4/5 |
| iPhone | Notification source | Stays at home |
| Mac | SMS gateway | Sends iMessage/SMS |
| Dumbphone | Your daily carry | Nokia 8210 4G |

### Software

- Docker (for the processor)
- Ollama (optional, for AI features)

---

## Installation

### 1. Raspberry Pi — Bluetooth Bridge

Set up the Pi to capture notifications from your iPhone via Bluetooth.

→ **[docs/ancs-bridge-setup.md](docs/ancs-bridge-setup.md)**

### 2. Processor — Filtering Engine

```bash
docker compose up -d
```

### 3. iMessage Gateway — Send SMS from Mac

```bash
cd imessage-gateway
pip install -r requirements.txt
python server.py  # Port 8095
```

### 4. SMS Assistant — Command Handler (Optional)

```bash
cd sms-assistant
pip install -r requirements.txt
python assistant.py
```

---

## Configuration

### Example Rules

```yaml
apps:
  messages:
    default: drop
    rules:
      - sender_contains: "Mum"
        action: send
      - body_contains: "urgent"
        action: send

  discord:
    default: drop
    rules:
      - sender_contains: "SSH Login"
        action: send
        priority: critical
      - body_contains: "@yourname"
        action: send

global:
  rules:
    - body_regex: "(verification|security) code"
      action: send
    - sender_contains: "Dad"
      action: send
```

### Rule Matchers

| Matcher | Description |
|---------|-------------|
| `sender_contains` | Match text in sender/title |
| `body_contains` | Match text in message body |
| `contains` | Match anywhere |
| `sender_regex` / `body_regex` | Regex patterns |
| `*_not_contains` | Exclusion rules |

### Actions

| Action | Description |
|--------|-------------|
| `send` | Always forward |
| `drop` | Never forward (unless urgent) |
| `llm` | Let AI decide |

### Sinks

```yaml
sinks:
  console:
    enabled: true

  imessage:
    enabled: true
    gateway_url: "http://localhost:8095"
    recipient: "+441234567890"

  bark:
    enabled: true
    url: "http://bark.example.com"
    device_key: "your-key"

  ntfy:
    enabled: true
    url: "https://ntfy.sh/your-topic"

  twilio:
    enabled: true
    account_sid: "ACxxxxx"
    auth_token: "xxxxx"
    from_number: "+15551234567"
    to_number: "+15559876543"
```

---

## SMS Assistant

Turn your dumbphone into a remote control. Text commands to your iPhone number and get responses via SMS.

### Commands

| Command | Example | Response |
|---------|---------|----------|
| `PING` | `PING` | Pi + iPhone status, battery % |
| `WEATHER` | `WEATHER` | Current conditions + forecast |
| `WEATHER [place]` | `WEATHER paris` | Weather for any location |
| `RAIN` | `RAIN` | Precipitation next 3 hours |
| `TODO` | `TODO` | List your tasks |
| `TODO [task]` | `TODO buy milk` | Add a task |
| `DONE 1,2` | `DONE 1,2` | Complete tasks |
| `REMIND [time] [msg]` | `REMIND 3pm dentist` | Set reminder |
| `TIMER [mins]` | `TIMER 25` | Countdown timer |
| `CALL [name]` | `CALL dad` | Fuzzy contact search |
| `NAV [from] to [dest]` | `NAV home to london` | Driving directions |
| `LOCATE` | `LOCATE` | Sound alarm on iPhone |
| `BRIEFING` | `BRIEFING` | Morning summary |
| `SEARCH [query]` | `SEARCH capital france` | Quick answer |
| *(anything else)* | `what's 20% of 85?` | Chat with LLM |

### Example Session

```
You:  BRIEFING
Sift: Friday 20 February
      12°C, sunny, 0% rain
      3 TODOs. First: Call dentist
      BIN: Tuesday - Black waste

You:  REMIND 3pm call dentist
Sift: Reminder set for 15:00

You:  NAV home to kings cross
Sift: Home → Kings Cross (5.1km, ~15 min):
      1. Head north on A1
      2. Continue through Islington
      3. Arrive at Kings Cross

You:  TIMER 25
Sift: Timer set for 25 min
      ... 25 minutes later ...
Sift: TIMER: 25 min complete!
```

### Setup

```bash
cd sms-assistant
pip install -r requirements.txt

export DUMBPHONE_NUMBER="+441234567890"
export PI_HOST="pi@192.168.1.100"
export OLLAMA_MODEL="qwen2.5:7b"
export DEFAULT_LAT="51.5074"
export DEFAULT_LON="-0.1278"

python assistant.py
```

Or install as a launchd service:

```bash
cp com.notif-fwd.sms-assistant.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.notif-fwd.sms-assistant.plist
```

---

## Sentiment Detection

Even with strict drop rules, genuine emergencies get through.

When enabled, dropped messages get a final urgency check via LLM. Messages like "HELP call 999" or "dad's in hospital" override the drop.

```yaml
global:
  sentiment_detection:
    enabled: true
    batch_window_seconds: 60
    apps:
      - whatsapp
      - messages
      - signal
```

Messages are batched for efficiency—one LLM call handles multiple messages.

---

## Rate Limiting

Three layers of spam protection:

| Layer | Description | Default |
|-------|-------------|---------|
| Cooldown | Min time between messages | 30 seconds |
| Hourly limit | Max per app/sender | 50/hour |
| Deduplication | Block identical messages | 5 minutes |

```yaml
global:
  rate_limit:
    cooldown_seconds: 30
    max_per_hour: 50
    exempt_apps:
      - phone  # Never rate limit calls
    no_cooldown_apps:
      - signal  # Allow rapid messages
```

---

## Dashboard

Web UI at **http://localhost:8090**:

- **Connection Status** — iPhone Bluetooth state
- **Stats** — Sent / dropped / rate-limited counts
- **Recent Notifications** — Filterable list
- **Feedback** — Mark notifications as incorrect to improve rules
- **AI Analysis** — Get rule suggestions from Ollama

---

## Running Without LLM

Works fine without Ollama. Just disable AI features:

```yaml
global:
  sentiment_detection:
    enabled: false
```

Use explicit rules instead of `action: llm`.

---

## Adding Custom Sinks

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
        # Your implementation
        return True

    def is_enabled(self) -> bool:
        return self._enabled
```

Register in `sinks/__init__.py` and initialize in `main.py`.

---

## Commands

```bash
make build       # Build containers
make up          # Start services
make down        # Stop services
make logs        # Follow logs
make test        # Send test notification
make pull-model  # Pull Ollama model
```

---

## Contributing

Contributions welcome! This started as a personal project but I'd love to see it help others.

```bash
# Install git hooks (checks for PII/secrets before commit)
make setup-hooks
```

- **Bug reports** — Open an issue
- **Feature ideas** — Open a discussion
- **Pull requests** — Fork, branch, PR

---

## License

MIT

---

## Acknowledgments

- [Ben Vallack](https://github.com/benvallack) — Inspiration for the dumbphone experiment
- [ancs4linux](https://github.com/pzmarzly/ancs4linux) — ANCS Bluetooth implementation
- [Bark](https://github.com/Finb/Bark) — iOS push notifications
- [ntfy](https://ntfy.sh) — Push notification service
- [Ollama](https://ollama.ai) — Local LLM runtime

---

<p align="center">
  <em>Built for intentional living in a distracted world.</em>
</p>
