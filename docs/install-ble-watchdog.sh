#!/bin/bash
#
# Installation script for BLE Reconnection Watchdog
# Run this on your Raspberry Pi running ancs4linux
#
# Usage: bash install-ble-watchdog.sh [OPTIONS]
#
# Options:
#   --iphone-mac MAC    Set specific iPhone MAC address to track
#   --bt-mac MAC        Set Pi's Bluetooth MAC (auto-detected if not set)
#   --ancs-name NAME    Set Bluetooth device name (default: ancs4linux)
#   --uninstall         Remove the watchdog service
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
IPHONE_MAC=""
BT_MAC=""
ANCS_NAME="ancs4linux"
UNINSTALL=false
SCRIPT_DIR="$HOME/notification-forwarder"
SERVICE_DIR="$HOME/.config/systemd/user"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --iphone-mac)
            IPHONE_MAC="$2"
            shift 2
            ;;
        --bt-mac)
            BT_MAC="$2"
            shift 2
            ;;
        --ancs-name)
            ANCS_NAME="$2"
            shift 2
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Function to uninstall
uninstall() {
    echo -e "${YELLOW}Uninstalling BLE Reconnection Watchdog...${NC}"

    systemctl --user stop ble-reconnect-watchdog.service 2>/dev/null || true
    systemctl --user disable ble-reconnect-watchdog.service 2>/dev/null || true
    rm -f "$SERVICE_DIR/ble-reconnect-watchdog.service"
    rm -f "$SCRIPT_DIR/ble-reconnect-watchdog.py"
    systemctl --user daemon-reload

    echo -e "${GREEN}Uninstallation complete.${NC}"
    exit 0
}

if [ "$UNINSTALL" = true ]; then
    uninstall
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}BLE Reconnection Watchdog Installation${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v bluetoothctl &> /dev/null; then
    echo -e "${RED}Error: bluetoothctl not found. Install bluez package.${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found.${NC}"
    exit 1
fi

if ! command -v ancs4linux-ctl &> /dev/null; then
    echo -e "${RED}Error: ancs4linux-ctl not found. Install ancs4linux first.${NC}"
    exit 1
fi

echo -e "${GREEN}All prerequisites met.${NC}"
echo ""

# Auto-detect Bluetooth MAC if not provided
if [ -z "$BT_MAC" ]; then
    BT_MAC=$(hciconfig | grep -oP 'BD Address: \K[A-F0-9:]+' | head -1)
    if [ -n "$BT_MAC" ]; then
        echo -e "${GREEN}Auto-detected Bluetooth MAC: $BT_MAC${NC}"
    else
        echo -e "${YELLOW}Warning: Could not auto-detect Bluetooth MAC${NC}"
    fi
fi

# List paired iPhones if no MAC specified
if [ -z "$IPHONE_MAC" ]; then
    echo -e "${YELLOW}Scanning for paired iPhones...${NC}"
    IPHONES=$(bluetoothctl devices | grep -i iphone || true)
    if [ -n "$IPHONES" ]; then
        echo -e "Found paired iPhones:"
        echo "$IPHONES"
        echo ""
        echo -e "${YELLOW}Tip: Use --iphone-mac to track a specific iPhone${NC}"
    else
        echo -e "${YELLOW}No paired iPhones found. Pair your iPhone first.${NC}"
    fi
fi

# Create directories
echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p "$SCRIPT_DIR"
mkdir -p "$SERVICE_DIR"

# Install the watchdog script
echo -e "${YELLOW}Installing watchdog script...${NC}"
cat > "$SCRIPT_DIR/ble-reconnect-watchdog.py" << 'WATCHDOG_SCRIPT'
#!/usr/bin/env python3
"""
BLE Reconnection Watchdog for ancs4linux

This service monitors the Bluetooth connection state and ensures reliable
auto-reconnection between iPhone and Raspberry Pi running ancs4linux.

Key Features:
- Monitors connection state via bluetoothctl
- Restarts BLE advertising when iPhone disconnects
- Periodically refreshes advertising to prevent staleness
- Actively attempts reconnection from the Pi side
- Handles edge cases: boot before iPhone in range, airplane mode, etc.

Based on research of BlueZ BLE peripheral behavior:
- BLE peripherals stop advertising when connected
- iOS devices don't advertise when locked
- Reconnection can be initiated from the Pi side using BlueZ Connect()
- Advertising must be restarted after disconnection

Author: Claude Code
License: MIT
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

# Configuration via environment variables
CONFIG = {
    "CHECK_INTERVAL": int(os.getenv("CHECK_INTERVAL", "10")),  # Seconds between connection checks
    "ADVERTISING_REFRESH_INTERVAL": int(os.getenv("ADVERTISING_REFRESH_INTERVAL", "300")),  # Refresh advertising every 5 min
    "RECONNECT_DELAY": int(os.getenv("RECONNECT_DELAY", "5")),  # Seconds before attempting reconnect
    "MAX_RECONNECT_ATTEMPTS": int(os.getenv("MAX_RECONNECT_ATTEMPTS", "3")),  # Per cycle
    "STACK_RESTART_THRESHOLD": int(os.getenv("STACK_RESTART_THRESHOLD", "600")),  # Restart stack after 10 min disconnected
    "IPHONE_MAC": os.getenv("IPHONE_MAC", ""),  # Specific iPhone to track (auto-detect if empty)
    "BT_MAC": os.getenv("BT_MAC", ""),  # Pi's Bluetooth MAC address
    "ANCS_NAME": os.getenv("ANCS_NAME", "ancs4linux"),  # Bluetooth device name
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
}

# Logging setup
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
    paired: bool
    trusted: bool


class BLEWatchdog:
    """Monitors and maintains BLE connection to iPhone for ancs4linux."""

    def __init__(self):
        self.iphone_mac: Optional[str] = CONFIG["IPHONE_MAC"] or None
        self.bt_mac: Optional[str] = CONFIG["BT_MAC"] or None
        self.last_connected_time: float = 0
        self.last_advertising_refresh: float = 0
        self.reconnect_attempts: int = 0
        self.current_state: ConnectionState = ConnectionState.UNKNOWN
        self.startup_time: float = time.time()

    def run_cmd(self, cmd: list[str], timeout: int = 10) -> tuple[bool, str]:
        """Run a shell command and return (success, output)."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            log.warning(f"Command timed out: {' '.join(cmd)}")
            return False, "timeout"
        except Exception as e:
            log.error(f"Command failed: {' '.join(cmd)} - {e}")
            return False, str(e)

    def run_bluetoothctl(self, commands: list[str], timeout: int = 10) -> tuple[bool, str]:
        """Run bluetoothctl with a sequence of commands."""
        cmd_input = "\n".join(commands) + "\nquit\n"
        try:
            result = subprocess.run(
                ["bluetoothctl"],
                input=cmd_input,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            log.warning("bluetoothctl timed out")
            return False, "timeout"
        except Exception as e:
            log.error(f"bluetoothctl failed: {e}")
            return False, str(e)

    def get_bt_mac(self) -> Optional[str]:
        """Get the Pi's Bluetooth MAC address."""
        if self.bt_mac:
            return self.bt_mac

        success, output = self.run_cmd(["hciconfig"])
        if not success:
            return None

        for line in output.splitlines():
            if "BD Address:" in line:
                parts = line.split("BD Address:")
                if len(parts) > 1:
                    mac = parts[1].strip().split()[0]
                    self.bt_mac = mac
                    log.info(f"Detected Pi Bluetooth MAC: {mac}")
                    return mac
        return None

    def find_paired_iphones(self) -> list[DeviceInfo]:
        """Find all paired iPhone devices."""
        devices = []
        success, output = self.run_cmd(["bluetoothctl", "devices", "Paired"])
        if not success:
            # Fallback to listing all devices
            success, output = self.run_cmd(["bluetoothctl", "devices"])
            if not success:
                return devices

        for line in output.splitlines():
            if "Device" in line and "iPhone" in line:
                parts = line.split()
                if len(parts) >= 3:
                    mac = parts[1]
                    name = " ".join(parts[2:])
                    # Get detailed info
                    _, info_output = self.run_cmd(["bluetoothctl", "info", mac])
                    connected = "Connected: yes" in info_output
                    paired = "Paired: yes" in info_output
                    trusted = "Trusted: yes" in info_output
                    devices.append(DeviceInfo(mac, name, connected, paired, trusted))

        return devices

    def get_connection_state(self) -> tuple[ConnectionState, Optional[str]]:
        """Check if any paired iPhone is connected. Returns (state, mac)."""
        iphones = self.find_paired_iphones()

        if not iphones:
            log.debug("No paired iPhones found")
            return ConnectionState.DISCONNECTED, None

        # If specific iPhone configured, check only that one
        if self.iphone_mac:
            for iphone in iphones:
                if iphone.mac.upper() == self.iphone_mac.upper():
                    if iphone.connected:
                        return ConnectionState.CONNECTED, iphone.mac
                    else:
                        return ConnectionState.DISCONNECTED, iphone.mac
            log.warning(f"Configured iPhone {self.iphone_mac} not found in paired devices")
            return ConnectionState.DISCONNECTED, None

        # Otherwise, check any iPhone
        for iphone in iphones:
            if iphone.connected:
                # Auto-detect and lock to this iPhone
                if not self.iphone_mac:
                    self.iphone_mac = iphone.mac
                    log.info(f"Auto-detected iPhone: {iphone.mac} ({iphone.name})")
                return ConnectionState.CONNECTED, iphone.mac

        # Return first paired iPhone MAC for reconnection attempts
        return ConnectionState.DISCONNECTED, iphones[0].mac if iphones else None

    def check_advertising_active(self) -> bool:
        """Check if BLE advertising is active."""
        success, output = self.run_cmd(["sudo", "btmgmt", "advinfo"])
        if not success:
            return False

        # Look for "Instances list with 1 item" or similar
        return "Instances list with 1" in output or "Instance: 1" in output

    def restart_advertising(self) -> bool:
        """Restart the ancs4linux advertising service."""
        log.info("Restarting BLE advertising...")

        # First, try to restart just the advertising service
        success, output = self.run_cmd([
            "systemctl", "--user", "restart", "ancs4linux-advertising"
        ])

        if not success:
            log.error(f"Failed to restart advertising service: {output}")
            return False

        # Wait for service to start
        time.sleep(2)

        # Re-enable advertising via ancs4linux-ctl
        bt_mac = self.get_bt_mac()
        if bt_mac:
            success, output = self.run_cmd([
                "ancs4linux-ctl", "enable-advertising",
                "--hci-address", bt_mac,
                "--name", CONFIG["ANCS_NAME"]
            ])
            if not success:
                log.warning(f"ancs4linux-ctl enable-advertising failed: {output}")

        # Verify advertising is active
        time.sleep(1)
        if self.check_advertising_active():
            log.info("BLE advertising restarted successfully")
            self.last_advertising_refresh = time.time()
            return True
        else:
            log.warning("Advertising may not be active after restart")
            return False

    def attempt_reconnect(self, mac: str) -> bool:
        """Attempt to reconnect to iPhone from Pi side."""
        log.info(f"Attempting to reconnect to iPhone {mac}...")

        # Use bluetoothctl to initiate connection
        success, output = self.run_bluetoothctl([f"connect {mac}"], timeout=15)

        if "Connection successful" in output:
            log.info(f"Successfully reconnected to {mac}")
            return True
        elif "Connected: yes" in output:
            log.info(f"Device {mac} is already connected")
            return True
        else:
            log.debug(f"Reconnect attempt failed: {output[:200]}")
            return False

    def ensure_device_connectable(self, mac: str) -> None:
        """Ensure the iPhone is trusted and set up for reconnection."""
        log.debug(f"Ensuring device {mac} is connectable...")

        self.run_bluetoothctl([
            f"trust {mac}",
            f"pair {mac}",  # This is a no-op if already paired
        ], timeout=10)

    def restart_bluetooth_stack(self) -> bool:
        """Full restart of the Bluetooth stack as last resort."""
        log.warning("Performing full Bluetooth stack restart...")

        # Stop all ancs4linux services
        self.run_cmd(["systemctl", "--user", "stop", "ancs4linux-observer"])
        self.run_cmd(["systemctl", "--user", "stop", "ancs4linux-advertising"])
        time.sleep(1)

        # Restart system Bluetooth service (requires sudo without password)
        success, output = self.run_cmd(["sudo", "systemctl", "restart", "bluetooth"])
        if not success:
            log.error(f"Failed to restart bluetooth service: {output}")

        time.sleep(3)

        # Restart hci0 interface
        self.run_cmd(["sudo", "hciconfig", "hci0", "down"])
        time.sleep(1)
        self.run_cmd(["sudo", "hciconfig", "hci0", "up"])
        time.sleep(2)

        # Start ancs4linux services
        self.run_cmd(["systemctl", "--user", "start", "ancs4linux-advertising"])
        time.sleep(3)
        self.run_cmd(["systemctl", "--user", "start", "ancs4linux-observer"])
        time.sleep(2)

        # Re-enable advertising
        bt_mac = self.get_bt_mac()
        if bt_mac:
            self.run_cmd([
                "ancs4linux-ctl", "enable-advertising",
                "--hci-address", bt_mac,
                "--name", CONFIG["ANCS_NAME"]
            ])

        log.info("Bluetooth stack restart completed")
        return True

    def refresh_advertising_if_needed(self) -> None:
        """Periodically refresh advertising even when connected to prevent staleness."""
        if time.time() - self.last_advertising_refresh > CONFIG["ADVERTISING_REFRESH_INTERVAL"]:
            log.info("Periodic advertising refresh...")
            bt_mac = self.get_bt_mac()
            if bt_mac:
                # Just re-run the enable-advertising command without full restart
                self.run_cmd([
                    "ancs4linux-ctl", "enable-advertising",
                    "--hci-address", bt_mac,
                    "--name", CONFIG["ANCS_NAME"]
                ])
            self.last_advertising_refresh = time.time()

    async def run(self) -> None:
        """Main watchdog loop."""
        log.info("BLE Reconnection Watchdog starting...")
        log.info(f"Configuration: CHECK_INTERVAL={CONFIG['CHECK_INTERVAL']}s, "
                f"ADVERTISING_REFRESH={CONFIG['ADVERTISING_REFRESH_INTERVAL']}s, "
                f"STACK_RESTART_THRESHOLD={CONFIG['STACK_RESTART_THRESHOLD']}s")

        # Initial setup
        self.get_bt_mac()
        self.last_advertising_refresh = time.time()

        # Ensure advertising is active on startup
        if not self.check_advertising_active():
            log.info("Advertising not active on startup, starting it...")
            self.restart_advertising()

        while True:
            try:
                await self.check_cycle()
            except Exception as e:
                log.error(f"Error in check cycle: {e}")

            await asyncio.sleep(CONFIG["CHECK_INTERVAL"])

    async def check_cycle(self) -> None:
        """Single check cycle."""
        state, mac = self.get_connection_state()

        # State transition logging
        if state != self.current_state:
            log.info(f"Connection state changed: {self.current_state.value} -> {state.value}")
            self.current_state = state

            if state == ConnectionState.CONNECTED:
                self.last_connected_time = time.time()
                self.reconnect_attempts = 0
                log.info(f"iPhone connected: {mac}")
            elif state == ConnectionState.DISCONNECTED:
                log.info(f"iPhone disconnected, will attempt reconnection...")
                # Give iOS a moment to potentially reconnect on its own
                await asyncio.sleep(CONFIG["RECONNECT_DELAY"])

        if state == ConnectionState.CONNECTED:
            # Periodic advertising refresh while connected
            self.refresh_advertising_if_needed()
            return

        # Handle disconnected state
        disconnected_duration = time.time() - self.last_connected_time if self.last_connected_time > 0 else 0

        # Check if advertising is still active
        if not self.check_advertising_active():
            log.warning("Advertising stopped, restarting...")
            self.restart_advertising()
            await asyncio.sleep(3)

        # Attempt reconnection from Pi side
        if mac and self.reconnect_attempts < CONFIG["MAX_RECONNECT_ATTEMPTS"]:
            self.reconnect_attempts += 1
            log.info(f"Reconnect attempt {self.reconnect_attempts}/{CONFIG['MAX_RECONNECT_ATTEMPTS']}")

            self.ensure_device_connectable(mac)
            if self.attempt_reconnect(mac):
                self.current_state = ConnectionState.CONNECTED
                self.last_connected_time = time.time()
                self.reconnect_attempts = 0
                return

        # Reset reconnect counter periodically to allow more attempts
        if self.reconnect_attempts >= CONFIG["MAX_RECONNECT_ATTEMPTS"]:
            log.debug("Max reconnect attempts reached, will retry in next cycle")
            self.reconnect_attempts = 0

        # Full stack restart if disconnected too long
        if disconnected_duration > CONFIG["STACK_RESTART_THRESHOLD"] and self.last_connected_time > 0:
            log.warning(f"Disconnected for {int(disconnected_duration)}s, restarting Bluetooth stack...")
            self.restart_bluetooth_stack()
            self.last_connected_time = time.time()  # Reset to prevent immediate re-restart


def main():
    """Entry point."""
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
WATCHDOG_SCRIPT

chmod +x "$SCRIPT_DIR/ble-reconnect-watchdog.py"
echo -e "${GREEN}Watchdog script installed to $SCRIPT_DIR/ble-reconnect-watchdog.py${NC}"

# Create systemd service file
echo -e "${YELLOW}Creating systemd service...${NC}"

cat > "$SERVICE_DIR/ble-reconnect-watchdog.service" << EOF
[Unit]
Description=BLE Reconnection Watchdog for ancs4linux
Documentation=https://github.com/pzmarzly/ancs4linux
After=bluetooth.target ancs4linux-advertising.service ancs4linux-observer.service
Wants=ancs4linux-advertising.service ancs4linux-observer.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 $SCRIPT_DIR/ble-reconnect-watchdog.py
Restart=always
RestartSec=10

# Environment configuration
Environment="CHECK_INTERVAL=10"
Environment="ADVERTISING_REFRESH_INTERVAL=300"
Environment="RECONNECT_DELAY=5"
Environment="MAX_RECONNECT_ATTEMPTS=3"
Environment="STACK_RESTART_THRESHOLD=600"
Environment="ANCS_NAME=$ANCS_NAME"
Environment="LOG_LEVEL=INFO"
EOF

# Add optional environment variables if provided
if [ -n "$IPHONE_MAC" ]; then
    echo "Environment=\"IPHONE_MAC=$IPHONE_MAC\"" >> "$SERVICE_DIR/ble-reconnect-watchdog.service"
    echo -e "${GREEN}Configured to track iPhone: $IPHONE_MAC${NC}"
fi

if [ -n "$BT_MAC" ]; then
    echo "Environment=\"BT_MAC=$BT_MAC\"" >> "$SERVICE_DIR/ble-reconnect-watchdog.service"
fi

# Complete the service file
cat >> "$SERVICE_DIR/ble-reconnect-watchdog.service" << EOF

[Install]
WantedBy=default.target
EOF

echo -e "${GREEN}Service file created at $SERVICE_DIR/ble-reconnect-watchdog.service${NC}"

# Configure sudoers for passwordless commands
echo -e "${YELLOW}Configuring sudo permissions...${NC}"
SUDOERS_FILE="/etc/sudoers.d/ble-watchdog"
SUDO_CONTENT="$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart bluetooth, /usr/bin/btmgmt, /usr/sbin/hciconfig"

if [ -f "$SUDOERS_FILE" ]; then
    echo -e "${YELLOW}Sudoers file already exists, skipping...${NC}"
else
    echo -e "${YELLOW}Creating sudoers file (requires sudo password)...${NC}"
    echo "$SUDO_CONTENT" | sudo tee "$SUDOERS_FILE" > /dev/null
    sudo chmod 440 "$SUDOERS_FILE"
    echo -e "${GREEN}Sudoers configured for passwordless Bluetooth commands${NC}"
fi

# Reload and enable service
echo -e "${YELLOW}Enabling and starting service...${NC}"
systemctl --user daemon-reload
systemctl --user enable ble-reconnect-watchdog.service
systemctl --user start ble-reconnect-watchdog.service

# Verify
sleep 2
if systemctl --user is-active --quiet ble-reconnect-watchdog.service; then
    echo -e "${GREEN}Service started successfully!${NC}"
else
    echo -e "${RED}Service failed to start. Check logs with:${NC}"
    echo "  journalctl --user -u ble-reconnect-watchdog.service -f"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Useful commands:"
echo "  View logs:      journalctl --user -u ble-reconnect-watchdog.service -f"
echo "  Check status:   systemctl --user status ble-reconnect-watchdog.service"
echo "  Restart:        systemctl --user restart ble-reconnect-watchdog.service"
echo "  Stop:           systemctl --user stop ble-reconnect-watchdog.service"
echo "  Uninstall:      bash install-ble-watchdog.sh --uninstall"
echo ""
echo "Configuration (edit service file to change):"
echo "  CHECK_INTERVAL=10              # Seconds between connection checks"
echo "  ADVERTISING_REFRESH_INTERVAL=300  # Refresh advertising every 5 min"
echo "  STACK_RESTART_THRESHOLD=600    # Full restart after 10 min disconnected"
echo ""
echo "To edit configuration:"
echo "  systemctl --user edit ble-reconnect-watchdog.service"
echo ""
