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
    "PROCESSOR_URL": os.getenv("PROCESSOR_URL", ""),  # e.g., "http://192.168.1.100:8090/notification"
    "HEALTH_CHECK_INTERVAL": int(os.getenv("HEALTH_CHECK_INTERVAL", "300")),  # 5 min
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
        self.last_health_check: float = 0
        self.reconnect_attempts: int = 0
        self.current_state: ConnectionState = ConnectionState.UNKNOWN
        self.alerted_power: bool = False
        self.alerted_ads: bool = False

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

    def send_alert(self, title: str, body: str, priority: str = "high"):
        """Send alert via notification processor."""
        import json
        import urllib.request

        payload = json.dumps({
            "app": "eink-monitor",
            "title": title,
            "body": body,
            "priority": priority,
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                CONFIG["PROCESSOR_URL"],
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=10)
            log.info(f"Alert sent: {title}")
        except Exception as e:
            log.error(f"Failed to send alert: {e}")

    def check_power_status(self) -> tuple[bool, str]:
        """Check for under-voltage/throttling. Returns (ok, message)."""
        success, output = self.run_cmd(["vcgencmd", "get_throttled"])
        if not success:
            return True, ""  # Can't check, assume OK

        try:
            # Format: throttled=0x0
            value = int(output.strip().split("=")[1], 16)
            if value == 0:
                return True, ""

            issues = []
            if value & 0x1:
                issues.append("under-voltage detected")
            if value & 0x2:
                issues.append("ARM frequency capped")
            if value & 0x4:
                issues.append("currently throttled")
            if value & 0x8:
                issues.append("soft temperature limit")
            if value & 0x10000:
                issues.append("under-voltage occurred")
            if value & 0x20000:
                issues.append("ARM frequency capping occurred")
            if value & 0x40000:
                issues.append("throttling occurred")
            if value & 0x80000:
                issues.append("soft temperature limit occurred")

            return False, ", ".join(issues)
        except Exception:
            return True, ""

    def check_advertising_count(self) -> tuple[int, int]:
        """Check advertising instances. Returns (current, max)."""
        success, output = self.run_cmd(["sudo", "btmgmt", "advinfo"])
        if not success:
            return 0, 5

        current = 0
        max_inst = 5

        for line in output.splitlines():
            if "Max instances:" in line:
                try:
                    max_inst = int(line.split(":")[1].strip())
                except Exception:
                    pass
            if "Instances list with" in line:
                try:
                    current = int(line.split("with")[1].split()[0])
                except Exception:
                    pass

        return current, max_inst

    def health_check(self):
        """Periodic health check for power and advertising."""
        if time.time() - self.last_health_check < CONFIG["HEALTH_CHECK_INTERVAL"]:
            return

        self.last_health_check = time.time()

        # Check power
        power_ok, power_msg = self.check_power_status()
        if not power_ok:
            if not self.alerted_power:
                self.send_alert(
                    "eink: Power Issue",
                    f"Raspberry Pi power problem: {power_msg}",
                    priority="critical"
                )
                self.alerted_power = True
            log.warning(f"Power issue: {power_msg}")
        else:
            self.alerted_power = False

        # Check advertising count
        ad_count, ad_max = self.check_advertising_count()
        if ad_count >= ad_max - 1:  # Alert at 4/5 or higher
            if not self.alerted_ads:
                self.send_alert(
                    "eink: Advertising Full",
                    f"BLE advertising slots {ad_count}/{ad_max} - may need restart",
                    priority="high"
                )
                self.alerted_ads = True
            log.warning(f"Advertising slots nearly full: {ad_count}/{ad_max}")
        else:
            self.alerted_ads = False

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
        log.info(f"Alerts via: {CONFIG['PROCESSOR_URL']}")

        self.get_bt_mac()
        self.last_advertising_refresh = time.time()
        self.last_health_check = time.time()

        while True:
            try:
                await self.check_cycle()
                self.health_check()
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

        if not self.check_advertising_active():
            log.warning("Advertising stopped, restarting...")
            self.restart_advertising()
            await asyncio.sleep(3)

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
