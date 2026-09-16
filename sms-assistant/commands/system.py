"""System commands: PING, RESET, EMERGENCY.

LOCATE (Bark-based alarm) dropped - no Bark instance confirmed running.
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from commands import register_command

log = logging.getLogger(__name__)

PI_HOST = os.getenv("PI_HOST", "ed@eink.lan")
PI_HEALTH_URL = os.getenv("PI_HEALTH_URL", "http://eink.lan:8081/health")
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", "/app/secrets/eink_ssh_key")

# Emergency mode state file - shared with sift-processor via volume mount
# (see routes/notification.py's EMERGENCY_FILE, same path)
EMERGENCY_FILE = Path("/app/sms-assistant-state/emergency.json")


@register_command("PING")
async def handle_ping(args: str = "") -> str:
    """Check Pi and iPhone connection status."""
    log.info(f"Checking status via {PI_HEALTH_URL}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(PI_HEALTH_URL)
            if resp.status_code != 200:
                return "Pi unreachable or ancs-bridge not running"

            health = resp.json()
            connected = health.get("phone_connected", False)
            last_activity = health.get("last_activity_ago")
            battery = health.get("battery")

            if connected:
                parts = ["Pi OK. iPhone connected."]
                if battery is not None:
                    parts.append(f"Battery {battery}%.")
                if last_activity:
                    parts.append(f"Last notif {last_activity}s ago.")
                return " ".join(parts)
            else:
                return "Pi OK but iPhone NOT connected"

    except Exception as e:
        return f"Status check failed: {str(e)[:80]}"


@register_command("RESET")
async def handle_reset(args: str = "") -> str:
    """Reset Bluetooth stack on the Pi remotely."""
    log.info(f"Executing remote reset on {PI_HOST}")

    reset_commands = """
        systemctl --user stop ancs-bridge
        systemctl --user stop ancs4linux-observer
        systemctl --user stop ancs4linux-advertising
        sudo systemctl restart bluetooth
        sleep 3
        sudo hciconfig hci0 down
        sleep 1
        sudo hciconfig hci0 up
        sleep 2
        systemctl --user start ancs4linux-advertising
        sleep 3
        /usr/local/bin/ancs4linux-ctl enable-advertising --hci-address B8:27:EB:D1:4B:FD --name ancs4linux
        sleep 2
        systemctl --user start ancs4linux-observer
        sleep 2
        systemctl --user start ancs-bridge
    """

    try:
        result = subprocess.run(
            [
                "ssh",
                "-i", SSH_KEY_PATH,
                "-o", "ConnectTimeout=10",
                # No interactive host-key prompt possible in a container -
                # accept-new trusts it on first contact, same trust model
                # as a human running this by hand for the first time.
                "-o", "StrictHostKeyChecking=accept-new",
                PI_HOST, reset_commands,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            log.info("Pi reset completed successfully")
            return "Pi reset complete. BT stack restarted."
        else:
            log.error(f"Pi reset failed: {result.stderr}")
            return f"Reset failed: {result.stderr[:100]}"

    except subprocess.TimeoutExpired:
        log.error("Pi reset timed out")
        return "Reset timed out - Pi may be unreachable"
    except Exception as e:
        log.error(f"Pi reset error: {e}")
        return f"Reset error: {str(e)[:100]}"


@register_command("EMERGENCY")
async def handle_emergency(args: str = "") -> str:
    """Toggle emergency mode - bypasses all notification drop rules."""
    args = args.strip().upper()

    if args == "ON":
        state = {
            "active": True,
            "enabled_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=2)).isoformat(),
        }
        EMERGENCY_FILE.parent.mkdir(parents=True, exist_ok=True)
        EMERGENCY_FILE.write_text(json.dumps(state))
        log.info("Emergency mode enabled for 2 hours")
        return "EMERGENCY MODE ON - All notifications forwarded for 2 hours"

    elif args == "OFF":
        EMERGENCY_FILE.unlink(missing_ok=True)
        log.info("Emergency mode disabled")
        return "Emergency mode disabled"

    else:  # STATUS (no args or anything else)
        if EMERGENCY_FILE.exists():
            try:
                state = json.loads(EMERGENCY_FILE.read_text())
                if state.get("active"):
                    expires = datetime.fromisoformat(state["expires_at"])
                    if datetime.now() > expires:
                        EMERGENCY_FILE.unlink()
                        return "Emergency mode OFF (expired)"
                    remaining = int((expires - datetime.now()).total_seconds() / 60)
                    return f"Emergency mode ACTIVE - {remaining} min remaining"
            except Exception:
                pass
        return "Emergency mode OFF"
