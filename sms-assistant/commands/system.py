"""System commands: PING, RESET, LOCATE."""

import json
import logging
import os
import subprocess

import httpx

from commands import register_command

log = logging.getLogger(__name__)

PI_HOST = os.getenv("PI_HOST", "")
BARK_URL = os.getenv("BARK_URL", "")
BARK_DEVICE_KEY = os.getenv("BARK_DEVICE_KEY", "")


@register_command("PING")
async def handle_ping(args: str = "") -> str:
    """Check Pi and iPhone connection status."""
    log.info(f"Checking status on {PI_HOST}")

    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", PI_HOST, "curl -s http://localhost:8081/health"],
            capture_output=True,
            text=True,
            timeout=15
        )

        if result.returncode == 0:
            try:
                health = json.loads(result.stdout)
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
            except Exception:
                return "Pi reachable but health check failed"
        else:
            return "Pi unreachable or ancs-bridge not running"

    except subprocess.TimeoutExpired:
        return "Pi connection timed out"
    except Exception as e:
        return f"Status check failed: {str(e)[:80]}"


@register_command("RESET")
async def handle_reset(args: str = "") -> str:
    """Reset Bluetooth stack on Pi remotely."""
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
            ["ssh", "-o", "ConnectTimeout=10", PI_HOST, reset_commands],
            capture_output=True,
            text=True,
            timeout=60
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


@register_command("LOCATE")
async def handle_locate(args: str = "") -> str:
    """Send loud alarm notification to iPhone via Bark."""
    log.info("Sending LOCATE alarm via Bark")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BARK_URL}/{BARK_DEVICE_KEY}/LOCATE/Finding your iPhone!",
                params={
                    "sound": "alarm",
                    "level": "critical",
                    "volume": "10",
                }
            )

            if resp.status_code == 200:
                return "Alarm sent to iPhone!"
            else:
                return f"Bark error: {resp.status_code}"

    except Exception as e:
        log.error(f"Locate error: {e}")
        return f"Locate failed: {str(e)[:80]}"
