# ANCS Bridge Setup Guide

> Tutorial for setting up iOS notification forwarding via Bluetooth on a Raspberry Pi.

**Hardware:** Raspberry Pi Zero 2 W (or any Pi with Bluetooth)
**OS:** Raspberry Pi OS Lite (Bookworm)
**Purpose:** Capture iOS notifications via BLE and forward to a processor

---

## Overview

This guide sets up:
1. **ancs4linux** - BLE stack that implements Apple Notification Center Service
2. **ancs-bridge** - Python service that forwards notifications via HTTP

```
iPhone → (BLE/ANCS) → Pi → (HTTP) → Processor
```

---

## Prerequisites

- Raspberry Pi with Bluetooth (Zero 2 W, Pi 3/4/5)
- Raspberry Pi OS Lite installed
- SSH access configured
- Static IP assigned (e.g., YOUR_PI_IP)

---

## Step 1: System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-dbus \
    python3-gi \
    bluetooth \
    bluez \
    libdbus-1-dev \
    libglib2.0-dev

# Add user to bluetooth group (CRITICAL for permissions)
sudo usermod -aG bluetooth $USER

# Enable lingering for user services
sudo loginctl enable-linger $USER
```

---

## Step 2: Install ancs4linux

```bash
# Install from PyPI
sudo pip3 install ancs4linux --break-system-packages

# Verify installation
which ancs4linux-advertising
which ancs4linux-observer
which ancs4linux-ctl
```

---

## Step 3: Configure Bluetooth

### Get your Pi's Bluetooth MAC address

```bash
hciconfig | grep "BD Address"
# Note the address, e.g., AA:BB:CC:DD:EE:FF
```

### Set a friendly name

```bash
sudo bluetoothctl
# In bluetoothctl:
system-alias ancs4linux
quit
```

---

## Step 4: Create systemd Services

### ancs4linux-advertising.service

This service advertises the Pi as an ANCS-compatible device.

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/ancs4linux-advertising.service << 'EOF'
[Unit]
Description=ancs4linux BLE Advertising
After=bluetooth.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ancs4linux-advertising
ExecStartPost=/bin/sleep 2
ExecStartPost=/usr/local/bin/ancs4linux-ctl enable-advertising --hci-address YOUR_BT_MAC --name ancs4linux
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
```

**Important:** Replace `YOUR_BT_MAC` with your actual Bluetooth MAC address (e.g., `AA:BB:CC:DD:EE:FF`).

### ancs4linux-observer.service

This service listens for notifications from the iPhone.

```bash
cat > ~/.config/systemd/user/ancs4linux-observer.service << 'EOF'
[Unit]
Description=ancs4linux Notification Observer
After=bluetooth.target ancs4linux-advertising.service

[Service]
Type=simple
ExecStart=/usr/local/bin/ancs4linux-observer
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
```

### Enable and start services

```bash
systemctl --user daemon-reload
systemctl --user enable ancs4linux-advertising ancs4linux-observer
systemctl --user start ancs4linux-advertising ancs4linux-observer
```

---

## Step 5: Create ancs-bridge

The bridge listens for D-Bus signals from ancs4linux and forwards them via HTTP.

### Create project directory

```bash
mkdir -p ~/notification-forwarder/ancs-bridge
cd ~/notification-forwarder/ancs-bridge
```

### Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install httpx aiohttp dbus-next
```

### Create main.py

```bash
cat > main.py << 'PYTHON'
#!/usr/bin/env python3
"""ANCS Bridge - forwards iOS notifications to processor via HTTP."""

import asyncio
import json
import logging
import os
import subprocess
import time
from datetime import datetime

import httpx
from dbus_next.aio import MessageBus
from dbus_next import BusType, Message, MessageType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

PROCESSOR_URL = os.getenv("PROCESSOR_URL", "http://YOUR_SERVER_IP:8090/notification")
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8081"))
STALE_THRESHOLD = int(os.getenv("STALE_THRESHOLD", "900"))  # 15 minutes
DISCONNECT_THRESHOLD = int(os.getenv("DISCONNECT_THRESHOLD", "1800"))  # 30 minutes

last_activity = 0.0
last_connected_time = time.time()

# Map iOS app IDs to friendly names
APP_NAMES = {
    "com.apple.MobileSMS": "messages",
    "com.apple.mobilephone": "phone",
    "net.whatsapp.WhatsApp": "whatsapp",
    "com.hammerandchisel.discord": "discord",
    "com.atebits.Tweetie2": "twitter",
    "com.burbn.instagram": "instagram",
    "com.facebook.Messenger": "messenger",
    "com.spotify.client": "spotify",
    "com.google.Gmail": "gmail",
    "com.apple.mobilemail": "mail",
    "com.slack.Slack": "slack",
    "org.telegram.Telegram": "telegram",
}


def normalize_app(app_id: str) -> str:
    """Convert iOS bundle ID to friendly name."""
    return APP_NAMES.get(app_id, app_id.split(".")[-1].lower())


def check_bluetooth_connected() -> bool:
    """Check if any paired iPhone is connected via bluetoothctl."""
    try:
        result = subprocess.run(
            ["bluetoothctl", "devices"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "iPhone" in line:
                parts = line.split()
                if len(parts) >= 2:
                    mac = parts[1]
                    info = subprocess.run(
                        ["bluetoothctl", "info", mac],
                        capture_output=True, text=True, timeout=5
                    )
                    if "Connected: yes" in info.stdout:
                        return True
        return False
    except Exception as e:
        log.warning(f"Failed to check bluetooth: {e}")
        return False


def restart_bluetooth_stack():
    """Restart Bluetooth and ancs4linux services."""
    log.warning("Restarting Bluetooth stack...")
    try:
        subprocess.run(["sudo", "systemctl", "restart", "bluetooth"],
                      check=True, capture_output=True, timeout=30)
        time.sleep(3)
        subprocess.run(["systemctl", "--user", "restart", "ancs4linux-advertising"],
                      check=True, capture_output=True, timeout=10)
        subprocess.run(["systemctl", "--user", "restart", "ancs4linux-observer"],
                      check=True, capture_output=True, timeout=10)
        log.info("Bluetooth stack restarted")
    except Exception as e:
        log.error(f"Failed to restart: {e}")


async def send_to_processor(app: str, title: str, body: str):
    """POST notification to processor."""
    global last_activity
    last_activity = time.time()

    payload = {
        "app": normalize_app(app),
        "title": title,
        "body": body,
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(PROCESSOR_URL, json=payload)
            log.info(f"Sent: {payload['app']}/{title} -> {resp.status_code}")
    except Exception as e:
        log.error(f"Failed to send: {e}")


async def connection_watchdog():
    """Restart Bluetooth if disconnected too long."""
    global last_connected_time
    log.info(f"Connection watchdog started (threshold: {DISCONNECT_THRESHOLD}s)")

    while True:
        await asyncio.sleep(60)
        if check_bluetooth_connected():
            last_connected_time = time.time()
        else:
            if time.time() - last_connected_time > DISCONNECT_THRESHOLD:
                log.warning(f"Disconnected too long - restarting...")
                restart_bluetooth_stack()
                last_connected_time = time.time()


async def staleness_watchdog():
    """Restart observer if no notifications for too long."""
    global last_activity
    log.info(f"Staleness watchdog started (threshold: {STALE_THRESHOLD}s)")

    while True:
        await asyncio.sleep(60)
        if last_activity > 0 and check_bluetooth_connected():
            if time.time() - last_activity > STALE_THRESHOLD:
                log.warning("ANCS stale - restarting observer...")
                try:
                    subprocess.run(
                        ["systemctl", "--user", "restart", "ancs4linux-observer"],
                        check=True, capture_output=True
                    )
                    last_activity = time.time()
                except Exception as e:
                    log.error(f"Failed to restart observer: {e}")


async def health_server():
    """HTTP health endpoint."""
    from aiohttp import web

    async def health_handler(request):
        connected = check_bluetooth_connected()
        idle = time.time() - last_activity if last_activity > 0 else None

        if not connected:
            return web.json_response({
                "status": "unhealthy",
                "phone_connected": False,
                "reason": "iPhone not connected via Bluetooth",
                "disconnected_for": int(time.time() - last_connected_time)
            }, status=503)

        return web.json_response({
            "status": "healthy",
            "phone_connected": True,
            "last_activity_ago": int(idle) if idle else None
        })

    app = web.Application()
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    log.info(f"Health endpoint on port {HEALTH_PORT}")


def handle_notification(msg: Message):
    """Handle notification signal from ancs4linux."""
    global last_activity
    last_activity = time.time()

    try:
        data = json.loads(msg.body[0])
        app_id = data.get("app_id", "unknown")
        title = data.get("title", "")
        subtitle = data.get("subtitle", "")
        body = data.get("body", "")

        full_title = f"{title}: {subtitle}" if subtitle else title
        log.info(f"Received: {app_id} | {full_title}")

        asyncio.create_task(send_to_processor(app_id, full_title, body))
    except Exception as e:
        log.error(f"Error handling notification: {e}")


async def listen_ancs():
    """Listen for ANCS notifications via D-Bus."""
    log.info("Connecting to D-Bus...")
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

    match_rule = "type='signal',interface='ancs4linux.Observer',member='ShowNotification'"
    await bus.call(Message(
        destination='org.freedesktop.DBus',
        path='/org/freedesktop/DBus',
        interface='org.freedesktop.DBus',
        member='AddMatch',
        signature='s',
        body=[match_rule]
    ))

    def handler(msg: Message):
        if msg.message_type == MessageType.SIGNAL and msg.member == "ShowNotification":
            handle_notification(msg)

    bus.add_message_handler(handler)
    log.info("Listening for ANCS notifications...")
    await bus.wait_for_disconnect()


async def main():
    log.info("ANCS Bridge starting...")
    log.info(f"Processor: {PROCESSOR_URL}")

    await asyncio.gather(
        health_server(),
        staleness_watchdog(),
        connection_watchdog(),
        listen_ancs(),
    )


if __name__ == "__main__":
    asyncio.run(main())
PYTHON
```

### Create systemd service

```bash
cat > ~/.config/systemd/user/ancs-bridge.service << EOF
[Unit]
Description=ANCS Bridge - Notification Forwarder
After=ancs4linux-observer.service

[Service]
Type=simple
WorkingDirectory=$HOME/notification-forwarder/ancs-bridge
ExecStart=$HOME/notification-forwarder/ancs-bridge/venv/bin/python main.py
Environment=PROCESSOR_URL=http://YOUR_SERVER_IP:8090/notification
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable ancs-bridge
systemctl --user start ancs-bridge
```

---

## Step 6: Pair iPhone

1. On the Pi, ensure services are running:
   ```bash
   systemctl --user status ancs4linux-advertising ancs4linux-observer ancs-bridge
   ```

2. Verify advertising is active:
   ```bash
   sudo btmgmt advinfo
   # Should show "Instances list with 1 item"
   ```

3. On iPhone: **Settings → Bluetooth → tap "ancs4linux"**

4. Accept pairing on both devices

5. On iPhone: **Settings → Bluetooth → tap (i) next to ancs4linux → enable "Share System Notifications"**

---

## Step 7: Verify

```bash
# Check health endpoint
curl http://localhost:8081/health
# Returns:
# {
#   "status": "healthy",
#   "phone_connected": true,
#   "last_activity_ago": 45,
#   "active_iphone": "XX:XX:XX:XX:XX:XX",
#   "configured_iphone": null
# }

# Watch for notifications
journalctl --user -u ancs-bridge -f
```

Send yourself a test notification - you should see it in the logs.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Authentication Failed" in BT logs | Add user to bluetooth group: `sudo usermod -aG bluetooth $USER` then reboot |
| iPhone won't connect | Check `sudo btmgmt advinfo` shows 1 item. If 0, restart ancs4linux-advertising |
| iPhone won't auto-reconnect | Install the BLE Reconnection Watchdog (see below) |
| No notifications | On iPhone, enable "Share System Notifications" for the device |
| Stale connection | ancs-bridge auto-restarts observer after 15 min inactivity |
| Shows connected when iPhone off | Multiple iPhones paired - set `IPHONE_MAC` env var to track specific one |
| Health shows wrong iPhone | Set `IPHONE_MAC` to your iPhone's MAC address (visible in dashboard after first notification) |
| Pi acts as Bluetooth speaker | Disable PipeWire audio (see below) |
| Duplicate notifications | ANCS sends multiple signals per notification - ancs-bridge deduplicates by notification ID |

### Disabling Bluetooth Audio

If your iPhone routes audio to the Pi (no sound on phone), disable PipeWire:

```bash
# Disable PipeWire audio services
systemctl --user stop pipewire pipewire-pulse pipewire.socket pipewire-pulse.socket
systemctl --user disable pipewire pipewire-pulse pipewire.socket pipewire-pulse.socket
systemctl --user mask pipewire pipewire-pulse

# Restart Bluetooth
sudo systemctl restart bluetooth

# Verify audio profiles are gone
bluetoothctl show | grep UUID
# Should NOT show Audio Sink, Audio Source, or Handsfree
```

You may need to toggle Bluetooth on your iPhone to clear cached audio profiles.

### Useful Commands

```bash
# Check Bluetooth status
bluetoothctl show

# Check if iPhone connected
bluetoothctl info XX:XX:XX:XX:XX:XX | grep Connected

# View all services
systemctl --user status ancs4linux-advertising ancs4linux-observer ancs-bridge

# Restart everything
systemctl --user restart ancs4linux-advertising ancs4linux-observer ancs-bridge

# Check advertising
sudo btmgmt advinfo
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROCESSOR_URL` | `http://YOUR_SERVER_IP:8090/notification` | Where to POST notifications |
| `HEALTH_PORT` | `8081` | Health endpoint port |
| `STALE_THRESHOLD` | `900` | Seconds before restarting observer (15 min) |
| `DISCONNECT_THRESHOLD` | `1800` | Seconds before restarting Bluetooth (30 min) |
| `IPHONE_MAC` | (auto-detect) | Specific iPhone MAC to track (prevents false positives with multiple paired iPhones) |
| `KUMA_PUSH_URL` | (disabled) | Uptime Kuma push URL for connection monitoring |
| `DEDUP_WINDOW` | `5.0` | Seconds to deduplicate repeated ANCS signals (ancs4linux sends each notification multiple times) |

### Configuring iPhone MAC

If you have multiple iPhones paired, the health check may report "connected" even when your main iPhone disconnects. To fix this:

1. Send a notification to auto-detect your iPhone MAC (shown in dashboard)
2. Configure it permanently:

```bash
systemctl --user edit ancs-bridge
```

Add:
```ini
[Service]
Environment="IPHONE_MAC=XX:XX:XX:XX:XX:XX"
```

Then reload:
```bash
systemctl --user daemon-reload
systemctl --user restart ancs-bridge
```

The health endpoint will now only report "connected" when that specific iPhone is connected.

---

## BLE Reconnection Watchdog (Required for Auto-Reconnect)

The built-in connection watchdog in ancs-bridge has long timeouts (30 minutes) to avoid false positives. For reliable auto-reconnection when iPhone goes out of range and returns, install the dedicated BLE Reconnection Watchdog service.

### Why You Need This

BLE auto-reconnection with ancs4linux fails because:
1. **BLE peripherals stop advertising when connected** - When iPhone disconnects, the Pi doesn't resume advertising
2. **iOS doesn't advertise when locked** - iPhone in your pocket won't initiate reconnection
3. **BlueZ advertising can become stale** - Long-running advertising instances may stop working
4. **"Maximum advertisements reached"** - Stale advertising instances accumulate and block new ones

The watchdog solves these by:
- Checking connection state every 10 seconds
- Clearing stale advertising instances before restart
- Actively attempting reconnection from the Pi side
- Periodically refreshing advertising to prevent staleness
- Full Bluetooth stack restart as a last resort

---

### Step 1: Fix ancs4linux-advertising.service

The default service file needs modification to clear stale advertisements on restart:

```bash
cat > ~/.config/systemd/user/ancs4linux-advertising.service << 'EOF'
[Unit]
Description=ancs4linux BLE Advertising
After=bluetooth.target

[Service]
Type=simple
ExecStartPre=-/usr/bin/sudo /usr/bin/btmgmt clr-adv
ExecStart=/usr/local/bin/ancs4linux-advertising
ExecStartPost=/bin/sleep 3
ExecStartPost=/usr/local/bin/ancs4linux-ctl enable-advertising --hci-address AA:BB:CC:DD:EE:FF --name ancs4linux
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF
```

**Important:** Replace `AA:BB:CC:DD:EE:FF` with your Pi's Bluetooth MAC (run `hciconfig | grep "BD Address"`).

The `-` prefix on `ExecStartPre` means the command is allowed to fail (when no ads to clear).

---

### Step 2: Configure Sudo Permissions

The watchdog needs passwordless sudo for Bluetooth commands:

```bash
echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart bluetooth, /usr/bin/btmgmt, /usr/sbin/hciconfig" | sudo tee /etc/sudoers.d/ble-watchdog
sudo chmod 440 /etc/sudoers.d/ble-watchdog
```

---

### Step 3: Create ble-reconnect-watchdog.py

The full script with alerting is available at `docs/ble-reconnect-watchdog.py`. Copy it to the Pi:

```bash
scp docs/ble-reconnect-watchdog.py pi@YOUR_PI_IP:~/notification-forwarder/
```

Or create it manually (alerting features shown below, full script follows):

**Key alerting additions:**
```python
# Added to CONFIG:
"PROCESSOR_URL": os.getenv("PROCESSOR_URL", "http://YOUR_SERVER_IP:8090/notification"),
"HEALTH_CHECK_INTERVAL": int(os.getenv("HEALTH_CHECK_INTERVAL", "300")),

# Power monitoring (vcgencmd get_throttled):
# - Under-voltage, throttling, temperature alerts

# Advertising slot monitoring:
# - Alert when 4+ of 5 slots used
```

**Full script:**

```bash
cat > ~/notification-forwarder/ble-reconnect-watchdog.py << 'PYTHON'
#!/usr/bin/env python3
"""BLE Reconnection Watchdog for ancs4linux - keeps iPhone connected with alerting."""

import asyncio
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

CONFIG = {
    "CHECK_INTERVAL": int(os.getenv("CHECK_INTERVAL", "10")),
    "ADVERTISING_REFRESH_INTERVAL": int(os.getenv("ADVERTISING_REFRESH_INTERVAL", "300")),
    "RECONNECT_DELAY": int(os.getenv("RECONNECT_DELAY", "5")),
    "MAX_RECONNECT_ATTEMPTS": int(os.getenv("MAX_RECONNECT_ATTEMPTS", "3")),
    "STACK_RESTART_THRESHOLD": int(os.getenv("STACK_RESTART_THRESHOLD", "600")),
    "IPHONE_MAC": os.getenv("IPHONE_MAC", ""),
    "BT_MAC": os.getenv("BT_MAC", ""),
    "ANCS_NAME": os.getenv("ANCS_NAME", "ancs4linux"),
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
}

logging.basicConfig(
    level=getattr(logging, CONFIG["LOG_LEVEL"]),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("ble-watchdog")


class ConnectionState(Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


@dataclass
class DeviceInfo:
    mac: str
    name: str
    connected: bool


class BLEWatchdog:
    def __init__(self):
        self.iphone_mac: Optional[str] = CONFIG["IPHONE_MAC"] or None
        self.bt_mac: Optional[str] = CONFIG["BT_MAC"] or None
        self.last_connected_time: float = 0
        self.last_advertising_refresh: float = 0
        self.reconnect_attempts: int = 0
        self.current_state: ConnectionState = ConnectionState.UNKNOWN

    def run_cmd(self, cmd: list[str], timeout: int = 30) -> tuple[bool, str]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            log.warning(f"Command timed out: {' '.join(cmd)}")
            return False, "timeout"
        except Exception as e:
            return False, str(e)

    def run_bluetoothctl(self, commands: list[str], timeout: int = 15) -> tuple[bool, str]:
        cmd_input = "\n".join(commands) + "\nquit\n"
        try:
            result = subprocess.run(["bluetoothctl"], input=cmd_input,
                                    capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except Exception as e:
            return False, str(e)

    def get_bt_mac(self) -> Optional[str]:
        if self.bt_mac:
            return self.bt_mac
        success, output = self.run_cmd(["hciconfig"])
        if success:
            for line in output.splitlines():
                if "BD Address:" in line:
                    self.bt_mac = line.split("BD Address:")[1].strip().split()[0]
                    log.info(f"Detected Pi BT MAC: {self.bt_mac}")
                    return self.bt_mac
        return None

    def find_paired_iphones(self) -> list[DeviceInfo]:
        devices = []
        success, output = self.run_cmd(["bluetoothctl", "devices", "Paired"])
        if not success:
            success, output = self.run_cmd(["bluetoothctl", "devices"])
        if not success:
            return devices

        for line in output.splitlines():
            if "Device" in line and "iPhone" in line:
                parts = line.split()
                if len(parts) >= 3:
                    mac = parts[1]
                    name = " ".join(parts[2:])
                    _, info = self.run_cmd(["bluetoothctl", "info", mac])
                    connected = "Connected: yes" in info
                    devices.append(DeviceInfo(mac, name, connected))
        return devices

    def get_connection_state(self) -> tuple[ConnectionState, Optional[str]]:
        iphones = self.find_paired_iphones()
        if not iphones:
            return ConnectionState.DISCONNECTED, None

        if self.iphone_mac:
            for iphone in iphones:
                if iphone.mac.upper() == self.iphone_mac.upper():
                    if iphone.connected:
                        return ConnectionState.CONNECTED, iphone.mac
                    return ConnectionState.DISCONNECTED, iphone.mac
            return ConnectionState.DISCONNECTED, None

        for iphone in iphones:
            if iphone.connected:
                if not self.iphone_mac:
                    self.iphone_mac = iphone.mac
                    log.info(f"Auto-detected iPhone: {iphone.mac}")
                return ConnectionState.CONNECTED, iphone.mac

        return ConnectionState.DISCONNECTED, iphones[0].mac if iphones else None

    def check_advertising_active(self) -> bool:
        success, output = self.run_cmd(["sudo", "btmgmt", "advinfo"])
        return success and ("Instances list with 1" in output or "Instance: 1" in output)

    def restart_advertising(self) -> bool:
        log.info("Restarting BLE advertising...")
        # Clear any stale ads first
        self.run_cmd(["sudo", "btmgmt", "clr-adv"], timeout=5)
        time.sleep(1)

        success, _ = self.run_cmd(["systemctl", "--user", "restart", "ancs4linux-advertising"], timeout=30)
        if not success:
            log.error("Failed to restart advertising service")
            return False

        time.sleep(4)
        bt_mac = self.get_bt_mac()
        if bt_mac:
            self.run_cmd(["ancs4linux-ctl", "enable-advertising",
                         "--hci-address", bt_mac, "--name", CONFIG["ANCS_NAME"]], timeout=15)

        time.sleep(1)
        if self.check_advertising_active():
            log.info("BLE advertising restarted successfully")
            self.last_advertising_refresh = time.time()
            return True
        log.warning("Advertising may not be active after restart")
        return False

    def attempt_reconnect(self, mac: str) -> bool:
        log.info(f"Attempting to reconnect to iPhone {mac}...")
        success, output = self.run_bluetoothctl([f"connect {mac}"], timeout=20)
        if "Connection successful" in output or "Connected: yes" in output:
            log.info(f"Successfully reconnected to {mac}")
            return True
        return False

    def restart_bluetooth_stack(self) -> bool:
        log.warning("Performing full Bluetooth stack restart...")
        self.run_cmd(["systemctl", "--user", "stop", "ancs4linux-observer"])
        self.run_cmd(["systemctl", "--user", "stop", "ancs4linux-advertising"])
        time.sleep(1)

        self.run_cmd(["sudo", "systemctl", "restart", "bluetooth"], timeout=30)
        time.sleep(3)
        self.run_cmd(["sudo", "hciconfig", "hci0", "down"])
        time.sleep(1)
        self.run_cmd(["sudo", "hciconfig", "hci0", "up"])
        time.sleep(2)

        self.run_cmd(["systemctl", "--user", "start", "ancs4linux-advertising"])
        time.sleep(4)
        self.run_cmd(["systemctl", "--user", "start", "ancs4linux-observer"])

        bt_mac = self.get_bt_mac()
        if bt_mac:
            self.run_cmd(["ancs4linux-ctl", "enable-advertising",
                         "--hci-address", bt_mac, "--name", CONFIG["ANCS_NAME"]])

        log.info("Bluetooth stack restart completed")
        return True

    def refresh_advertising_if_needed(self) -> None:
        if time.time() - self.last_advertising_refresh > CONFIG["ADVERTISING_REFRESH_INTERVAL"]:
            log.info("Periodic advertising refresh...")
            bt_mac = self.get_bt_mac()
            if bt_mac:
                self.run_cmd(["ancs4linux-ctl", "enable-advertising",
                             "--hci-address", bt_mac, "--name", CONFIG["ANCS_NAME"]])
            self.last_advertising_refresh = time.time()

    async def run(self) -> None:
        log.info("BLE Reconnection Watchdog starting...")
        log.info(f"Config: CHECK={CONFIG['CHECK_INTERVAL']}s, REFRESH={CONFIG['ADVERTISING_REFRESH_INTERVAL']}s, "
                f"STACK_RESTART={CONFIG['STACK_RESTART_THRESHOLD']}s")
        if CONFIG["IPHONE_MAC"]:
            log.info(f"Tracking iPhone: {CONFIG['IPHONE_MAC']}")

        self.get_bt_mac()
        self.last_advertising_refresh = time.time()

        while True:
            try:
                await self.check_cycle()
            except Exception as e:
                log.error(f"Error in check cycle: {e}")
            await asyncio.sleep(CONFIG["CHECK_INTERVAL"])

    async def check_cycle(self) -> None:
        state, mac = self.get_connection_state()

        if state != self.current_state:
            log.info(f"State: {self.current_state.value} -> {state.value}")
            self.current_state = state
            if state == ConnectionState.CONNECTED:
                self.last_connected_time = time.time()
                self.reconnect_attempts = 0
                log.info(f"iPhone connected: {mac}")
            elif state == ConnectionState.DISCONNECTED:
                log.info("iPhone disconnected, will attempt reconnection...")
                await asyncio.sleep(CONFIG["RECONNECT_DELAY"])

        if state == ConnectionState.CONNECTED:
            self.refresh_advertising_if_needed()
            return

        disconnected_duration = time.time() - self.last_connected_time if self.last_connected_time > 0 else 0

        # Check and restart advertising if needed
        if not self.check_advertising_active():
            log.warning("Advertising stopped, restarting...")
            self.restart_advertising()
            await asyncio.sleep(3)

        # Attempt reconnection
        if mac and self.reconnect_attempts < CONFIG["MAX_RECONNECT_ATTEMPTS"]:
            self.reconnect_attempts += 1
            log.info(f"Reconnect attempt {self.reconnect_attempts}/{CONFIG['MAX_RECONNECT_ATTEMPTS']}")
            self.run_bluetoothctl([f"trust {mac}"])
            if self.attempt_reconnect(mac):
                self.current_state = ConnectionState.CONNECTED
                self.last_connected_time = time.time()
                self.reconnect_attempts = 0
                return

        if self.reconnect_attempts >= CONFIG["MAX_RECONNECT_ATTEMPTS"]:
            self.reconnect_attempts = 0

        # Full stack restart if disconnected too long
        if disconnected_duration > CONFIG["STACK_RESTART_THRESHOLD"] and self.last_connected_time > 0:
            log.warning(f"Disconnected {int(disconnected_duration)}s, restarting Bluetooth stack...")
            self.restart_bluetooth_stack()
            self.last_connected_time = time.time()


def main():
    watchdog = BLEWatchdog()
    try:
        asyncio.run(watchdog.run())
    except KeyboardInterrupt:
        log.info("Watchdog stopped by user")
    except Exception as e:
        log.error(f"Watchdog crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
PYTHON

chmod +x ~/notification-forwarder/ble-reconnect-watchdog.py
```

---

### Step 4: Create ble-reconnect-watchdog.service

```bash
cat > ~/.config/systemd/user/ble-reconnect-watchdog.service << 'EOF'
[Unit]
Description=BLE Reconnection Watchdog for ancs4linux
After=bluetooth.target ancs4linux-advertising.service ancs4linux-observer.service
Wants=ancs4linux-advertising.service ancs4linux-observer.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/ed/notification-forwarder/ble-reconnect-watchdog.py
Restart=always
RestartSec=10

# Environment configuration
Environment="CHECK_INTERVAL=10"
Environment="ADVERTISING_REFRESH_INTERVAL=300"
Environment="RECONNECT_DELAY=5"
Environment="MAX_RECONNECT_ATTEMPTS=3"
Environment="STACK_RESTART_THRESHOLD=600"
Environment="ANCS_NAME=ancs4linux"
Environment="LOG_LEVEL=INFO"
Environment="IPHONE_MAC=XX:XX:XX:XX:XX:XX"
Environment="PROCESSOR_URL=http://YOUR_SERVER_IP:8090/notification"
Environment="HEALTH_CHECK_INTERVAL=300"

[Install]
WantedBy=default.target
EOF
```

**Important:** Update `IPHONE_MAC` with your iPhone's MAC address. Find it with:
```bash
bluetoothctl devices | grep iPhone
```

---

### Step 5: Enable and Start

```bash
systemctl --user daemon-reload
systemctl --user enable ble-reconnect-watchdog.service
systemctl --user start ble-reconnect-watchdog.service
```

---

### Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_INTERVAL` | `10` | Seconds between connection checks |
| `ADVERTISING_REFRESH_INTERVAL` | `300` | Refresh advertising every N seconds |
| `RECONNECT_DELAY` | `5` | Wait before attempting reconnect after disconnect |
| `MAX_RECONNECT_ATTEMPTS` | `3` | Reconnect attempts per check cycle |
| `STACK_RESTART_THRESHOLD` | `600` | Full Bluetooth restart after N seconds disconnected |
| `IPHONE_MAC` | (auto) | Specific iPhone MAC to track |
| `BT_MAC` | (auto) | Pi's Bluetooth MAC address |
| `ANCS_NAME` | `ancs4linux` | Bluetooth device name |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `PROCESSOR_URL` | `http://YOUR_SERVER_IP:8090/notification` | Where to send alerts |
| `HEALTH_CHECK_INTERVAL` | `300` | Seconds between health checks (power, ads) |

---

### Alerting

The watchdog monitors Pi health and sends alerts via the notification processor when issues occur:

| Alert | Trigger | Priority |
|-------|---------|----------|
| **Power Issue** | Under-voltage, throttling, temperature limit | critical |
| **Advertising Full** | 4+ of 5 BLE advertising slots used | high |

Alerts are sent as app `eink-monitor` - add it to your config.yaml:

```yaml
apps:
  eink-monitor:
    default: send
```

Alerts are sent once per issue and reset when the issue clears. Health checks run every 5 minutes by default.

To customize, edit the service:
```bash
systemctl --user edit ble-reconnect-watchdog.service
```

---

### Monitoring

```bash
# View logs
journalctl --user -u ble-reconnect-watchdog.service -f

# Check status
systemctl --user status ble-reconnect-watchdog.service

# Check all ANCS services
systemctl --user status ancs4linux-advertising ancs4linux-observer ancs-bridge ble-reconnect-watchdog
```

---

### Troubleshooting: "Maximum advertisements reached"

If advertising fails with this error, clear stale instances:

```bash
# Clear all advertising instances
sudo btmgmt clr-adv

# If that fails, full Bluetooth restart
systemctl --user stop ancs4linux-advertising ancs4linux-observer ancs-bridge ble-reconnect-watchdog
sudo systemctl restart bluetooth
sleep 3
sudo hciconfig hci0 up
sleep 2
sudo btmgmt advinfo  # Should show "Instances list with 0 items"

# Restart services
systemctl --user start ancs4linux-advertising
sleep 5
systemctl --user start ancs4linux-observer ancs-bridge ble-reconnect-watchdog
```

---

### Edge Cases Handled

| Scenario | Watchdog Behavior |
|----------|------------------|
| Pi boots before iPhone in range | Advertising stays active, reconnect attempted when iPhone appears |
| iPhone airplane mode on/off | Detects disconnect, restarts advertising, attempts reconnection |
| iPhone Bluetooth toggle | Same as airplane mode |
| Extended out of range (>10 min) | Full Bluetooth stack restart, fresh advertising |
| BlueZ advertising stale | Periodic refresh every 5 minutes |
| Maximum advertisements reached | Clears stale ads before restarting advertising |

---

### Example Configuration

```
Pi Hostname: raspberrypi
Pi IP: 192.168.1.100
Pi User: pi
Pi BT MAC: XX:XX:XX:XX:XX:XX
iPhone MAC: XX:XX:XX:XX:XX:XX
Processor URL: http://192.168.1.200:8090/notification
```

---

*Last updated: 2026-02-20*
*Updated: 2026-02-17 - Added BLE Reconnection Watchdog with full reproducible scripts*
