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
🍓 Raspberry Pi  or  🔌 ESP32 (the bridge)
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

# Interactive setup - configures everything
./setup.sh

# Start the processor
make up
```

The setup script will:
- Ask for your dumbphone number, location, and preferences
- Configure notification sinks (iMessage, Bark, ntfy)
- Set up AI features (optional, requires Ollama)
- Install macOS services (SMS Assistant, iMessage Gateway)
- Create all config files

> [!NOTE]
> `setup.sh` currently automates the original Mac-based gateway path. If
> you don't have a Mac, skip the macOS-services step it offers and follow
> [`smtp-gateway/README.md`](smtp-gateway/README.md) instead - see
> [Delivery Gateway](#3-delivery-gateway--send-sms-to-your-dumbphone) below.

Dashboard: **http://localhost:8090**

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         YOUR HOME                                   │
│                                                                     │
│   ┌──────────┐    Bluetooth    ┌──────────────┐                    │
│   │  iPhone  │ ──────────────► │ Pi or ESP32  │                    │
│   │ (drawer) │                 │ (ANCS bridge)│                    │
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
2. **Forward** — the bridge (Pi or ESP32) sends it to the processor via HTTP
3. **Filter** — Rules engine evaluates: send, drop, or ask AI
4. **Deliver** — Approved notifications go to your configured sinks

### Two-Way Communication

**Outbound (notifications to you):**
```
iPhone → Pi or ESP32 (BLE) → Processor → Delivery Gateway → SMS → Dumbphone
```

**Inbound (commands from you):**
```
Dumbphone → SMS → iPhone → Shortcuts automation → SMS Assistant → Response → Dumbphone
```

Both directions used to require a Mac running 24/7 (AppleScript against
Messages.app, and a poller against its local `chat.db`). As of v2, neither
does - see [Delivery Gateway](#3-delivery-gateway--send-sms-to-your-dumbphone)
below. The iPhone itself, via two Shortcuts Personal Automations, is now
the only thing that has to stay reachable.

---

## What You'll Need

### Hardware

| Component | Purpose | Recommendation |
|-----------|---------|----------------|
| Bluetooth bridge | Listens for iPhone notifications | **Either** a Raspberry Pi (Zero 2 W, Pi 3/4/5) **or** a classic ESP32 dev board (ESP32-WROOM-32, ~£5) - see below |
| iPhone | Notification source | Stays at home |
| Dumbphone | Your daily carry | Nokia 8210 4G |

A **Mac** is optional as of v2 - only needed if you choose the original
`imessage-gateway/` (AppleScript-driven) delivery path instead of the
Mac-free `smtp-gateway/` one. See [Delivery Gateway](#3-delivery-gateway--send-sms-to-your-dumbphone).

### Pi or ESP32?

Both bridges do the same job and send the processor exactly the same thing, so the rest of Sift doesn't care which one you pick.

| | Raspberry Pi (`docs/ancs-bridge-setup.md`) | ESP32 (`esp32-bridge/`) |
|---|---|---|
| Cost | Pi + SD card + PSU | ~£5 board + any USB charger |
| Software | Linux, BlueZ, ancs4linux, 3 services + watchdog | One firmware, updates over WiFi |
| Power cuts | Can corrupt the SD card | Doesn't care, boots in under a second |
| First pairing | Settings → Bluetooth | Once via the nRF Connect app (BLE-only devices don't show in Settings until paired) |
| `RESET` | Restarts the Bluetooth stack over SSH | Reboots the board over HTTP |
| Also runs other stuff | Yes - it's a Linux box | No - it does this one job |

Pick the **ESP32** if all you need is the bridge. Pick the **Pi** if you already have one, or want the same box to do other things too.

### Software

- Docker (for the processor)
- Ollama (optional, for AI features)

---

## Installation

### 1. Bluetooth Bridge — Pi or ESP32

Set up **one** of these to capture notifications from your iPhone via Bluetooth:

- **ESP32** → **[esp32-bridge/README.md](esp32-bridge/README.md)** - flash, join WiFi via its setup hotspot, pair once with nRF Connect
- **Raspberry Pi** → **[docs/ancs-bridge-setup.md](docs/ancs-bridge-setup.md)**

Swapping from the Pi to an ESP32 later? The ESP32 starts with forwarding off, so you can run both side by side and check its `/logs` before turning the Pi off.

### 2. Processor — Filtering Engine

```bash
docker compose up -d
```

### 3. Delivery Gateway — Send SMS to your dumbphone

Two options - both speak the same `POST /send` contract, so pick one:

**SMTP Gateway (recommended, no Mac needed)** - emails your iPhone, a
Shortcuts automation there sends the text.

```bash
cd smtp-gateway
cp .env.example .env   # fill in your SMTP details
./run.sh                # Port 8095
```

Full walkthrough, including the Shortcut: [`smtp-gateway/README.md`](smtp-gateway/README.md).

**iMessage Gateway (legacy, requires a Mac running 24/7)** - drives
Messages.app directly via AppleScript.

```bash
cd imessage-gateway
pip install -r requirements.txt
python server.py  # Port 8095
```

### 4. SMS Assistant — Command Handler (Optional)

Text commands from your dumbphone back to yourself - see [SMS Assistant](#sms-assistant)
below. Runs as a plain HTTP service now (a Shortcuts automation POSTs
incoming texts to it directly), no Mac or chat.db polling involved.

```bash
cd sms-assistant
pip install -r requirements.txt
python assistant.py  # Port 8091
```

Or with Docker: `docker build -t sms-assistant . && docker run -p 8091:8091 --env-file .env sms-assistant`.

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
    # Point at whichever gateway you're running - smtp-gateway/ or
    # imessage-gateway/, both listen on :8095 by default and speak the
    # same contract.
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

As of v2 this runs as a plain HTTP service (`POST /incoming`), fed by a
second Shortcuts Personal Automation (trigger: Message received from your
dumbphone, Run Immediately) instead of polling a Mac's local `chat.db`.
Replies go back out through whichever delivery gateway you set up above.
There's no LLM fallback for unmatched text anymore - see the note in
[`sms-assistant/commands/README.md`](sms-assistant/commands/README.md) if
you want that back.

### Commands

| Command | Example | Response |
|---------|---------|----------|
| `PING` | `PING` | Bridge + iPhone status, battery % |
| `RESET` | `RESET` | Restart the bridge (reboots the ESP32, or restarts the Pi's Bluetooth stack over SSH) |
| `EMERGENCY` | `EMERGENCY ON` | Toggle emergency mode |
| `WEATHER` | `WEATHER` | Current conditions + forecast |
| `WEATHER [place]` | `WEATHER paris` | Weather for any location |
| `RAIN` | `RAIN` | Precipitation next 3 hours |
| `TODO` | `TODO` | List open todos |
| `TODO [task]` | `TODO buy milk` | Add a todo |
| `DONE [n or text]` | `DONE 2` | Complete a todo, by list position or fuzzy text match |
| `REMIND [time] [msg]` | `REMIND 3pm dentist` | Set reminder |
| `TIMER [mins]` | `TIMER 25` | Countdown timer |
| `CALL [name]` | `CALL dad` | Fuzzy contact search |
| `NAV [from] to [dest]` | `NAV home to london` | Directions |
| `BRIEFING` | `BRIEFING` | Morning summary |
| `BIN` | `BIN` | Which bin this week |
| `ICE` / `INSURANCE` | `ICE` | Emergency / insurance info |
| `BORED` | `BORED` | Offline activity suggestion |
| `RINGGO` | `RINGGO START` | Parking session control |
| `HELP` | `HELP` or `HELP WEATHER` | List commands, or detail on one |
| *(anything else)* | `asdf` | `Unknown command: ASDF. Text HELP for a list.` |

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

export GATEWAY_URL="http://localhost:8095"       # your delivery gateway from step 3
export PI_HEALTH_URL="http://192.168.1.100:8081/health"  # your bridge (Pi or ESP32), for PING
# RESET - ESP32 bridge:
export BRIDGE_RESET_URL="http://192.168.1.100:8081/reset"
# RESET - Pi bridge (leave BRIDGE_RESET_URL unset):
export PI_HOST="pi@192.168.1.100"
export SSH_KEY_PATH="/path/to/key"
export INGEST_URL=""                             # optional: a REST todo backend for TODO/DONE
export DEFAULT_LAT="51.5074"
export DEFAULT_LON="-0.1278"

python assistant.py   # Port 8091
```

Or with Docker: `docker build -t sms-assistant . && docker run -p 8091:8091 --env-file .env sms-assistant`.

Then point a Shortcuts Personal Automation (trigger: Message received,
filtered to your dumbphone's number, Run Immediately, Ask Before Running
off) at `POST http://<host>:8091/incoming` with body
`{"text": "<Shortcut Input>"}`.

With a Pi bridge, `RESET` needs `ssh` on the container - if you're building
your own image instead of using the provided `Dockerfile`, make sure your
base image has an SSH client installed. With an ESP32 bridge it's a plain
HTTP POST.

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

## Versions

Released as git tags, not by rewriting these docs in place - check out an
older tag if you want the docs as they were for that version.

- **v2.1.1** — ESP32 bridge link fix. The iPhone link kept dropping and iOS
  eventually stopped reconnecting, because a classic ESP32 shares one radio
  between WiFi and Bluetooth. WiFi now runs in max modem sleep (0 drops in a
  15-minute test, down from one every few seconds). Also: the 5 s link timeout
  is requested on connect, the dashboard shows the iPhone's Bluetooth signal
  next to "iPhone Connected", and there's a `POST /bletest` WiFi-off diagnostic.
- **v2.1.0** — No Pi required. Added `esp32-bridge/`: firmware that turns a
  ~£5 classic ESP32 into the Bluetooth bridge, as an alternative to the
  Pi. Same HTTP contract, same notification rules and watchdogs as
  ancs4linux + ancs-bridge. `RESET` can reboot it over HTTP
  (`BRIDGE_RESET_URL`). Also a redesigned, minimal dashboard; the AI
  analysis feature was removed.
- **v2.0.0** — No Mac required. Added `smtp-gateway/` as a Mac-free
  alternative to `imessage-gateway/` (email + an iOS Shortcut instead of
  AppleScript). Rewrote `sms-assistant/` to be event-driven over HTTP
  instead of polling a Mac's local `chat.db` - runs anywhere a container
  can, not just macOS. Dropped `MESSAGES`, `LOCATE`, and `SEARCH`
  (macOS-chat.db-only, Bark-only, and Ollama-only respectively - not
  portable, bring them back in your own fork if you have the
  dependencies).
- **v1.0.0** — Original release. macOS required for both delivery
  directions (AppleScript via Messages.app).

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
- [ancs4linux](https://github.com/pzmarzly/ancs4linux) — ANCS Bluetooth implementation (Pi bridge)
- [NimBLE-Arduino](https://github.com/h2zero/NimBLE-Arduino) — Bluetooth LE stack (ESP32 bridge)
- [Bark](https://github.com/Finb/Bark) — iOS push notifications
- [ntfy](https://ntfy.sh) — Push notification service
- [Ollama](https://ollama.ai) — Local LLM runtime

---

<p align="center">
  <em>Built for intentional living in a distracted world.</em>
</p>
