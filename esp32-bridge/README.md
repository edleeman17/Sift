# ESP32 ANCS bridge

A £5 ESP32 that does the job of the Pi's `ancs4linux` + `ancs-bridge`: it pairs with the iPhone over Bluetooth LE, receives every new notification through Apple's ANCS, and POSTs it to `sift-processor`.

Why: the Pi Zero bridge needed an SD card, a Linux Bluetooth stack, three systemd services and a watchdog to keep it alive. This is one firmware that boots in under a second and doesn't mind power cuts.

## Hardware

Any **classic ESP32** board (ESP32-WROOM-32 / DevKitC style, 4 MB flash). Tested on an ESP32-D0WD-V3 with a CP2102 USB chip. The ESP32-C3/S3 would also work (BLE only is fine).

## Same contract as the Pi bridge

| | |
|---|---|
| Notification out | `POST PROCESSOR_URL` with `{"app", "title", "body", "timestamp"}`. Same app-name mapping, same ignored apps (Bark, ntfy) |
| `GET :8081/health` | `phone_connected`, `last_activity_ago`, `battery`; 503 when the phone isn't connected. Used by sift-processor's battery monitor and the SMS `PING` command |
| `GET :8081/logs` | Recent log lines (used by the Sift debug page) |
| `GET :8081/status` | Extra detail: advertising, bonds, WiFi RSSI, free heap |
| `POST :8081/reset` | Reboot. Replaces the SSH-based `RESET` command. `?bonds=1` also forgets the paired iPhone |
| `POST :8081/bletest?min=10` | Diagnostic: run Bluetooth with WiFi off for N minutes (board unreachable meanwhile; notifications are held and sent afterwards). Results in `/logs` |
| `POST :8081/forward?on=1` | Turn forwarding on or off (saved across reboots). **Off by default**, so a new board can run next to the old bridge without double-sending |
| Uptime Kuma | Push heartbeat every 60 s while the iPhone is connected |

Notification handling follows the Pi version exactly:

- Like ancs4linux, it forwards new notifications and modified ones. It ignores the ones iOS replays on every reconnect (flagged PreExisting).
- Like ancs-bridge, it skips any notification ID it has already handled in the last hour. That list is saved, so it survives reboots.

The Pi's three watchdogs are ported over:

| Pi | ESP32 |
|---|---|
| Restart the observer after 15 min of silence | Re-subscribe to ANCS |
| Refresh advertising every 5 min while disconnected | Same, at Apple's fast 20 ms rate for 30 s |
| Restart the Bluetooth stack after 30 min disconnected | Reboot |

It also reboots after 5 minutes without WiFi, or if the main loop stalls.

### iPhone link

With Bluetooth LE, only the iPhone can start a connection, so after a drop the bridge advertises and waits.

A classic ESP32 has **one radio shared between WiFi and Bluetooth**, and that, not range, power or AirPods, was behind the dropped links. In a 10-minute WiFi-off test the link held with 0 drops; with WiFi on it dropped every few seconds and iOS eventually gave up reconnecting. The Pi Zero's combo chip shares its radio the same way, which is likely why it dropped ~20 times an hour too. Three settings fix it:

- **WiFi max modem sleep.** WiFi wakes only every ~300 ms and leaves the radio to Bluetooth in between. This is the one that matters: 0 drops in 15 minutes with WiFi on, and `/health` still answers within about 1 s.
- **A 5 s link timeout (60 ms interval)**, requested as soon as the phone connects, so pairing and setup don't run on iOS's ~0.7 s default.
- **Fast re-advertising after a drop.** iOS usually reconnects within a few seconds.

After a long absence (you were out of the house), iOS can stop reconnecting by itself. In that case tap **Sift ANCS** in Settings → Bluetooth.

`/health` stays 200 (`"link": "reconnecting"`) through drops shorter than 2 minutes.

## Setup

1. Copy the config template and fill it in (it's gitignored):

   ```
   cp src/config.example.h src/config.h
   ```

2. Flash over USB with [PlatformIO](https://platformio.org/):

   ```
   pio run -e esp32dev -t upload
   ```

3. Set up WiFi. On first boot the board opens a hotspot (`SETUP_AP_NAME` / `SETUP_AP_PASSWORD`). Join it from a phone, pick your network and save. The board then uses the fixed IP from `config.h`.
4. Pair. iOS doesn't list Bluetooth LE devices in Settings until they've been paired once, so do the first pairing from a BLE app such as **nRF Connect** (free): **Scan → Sift ANCS → Connect**, then tap **Pair** and **Allow** notifications. After that it appears in Settings → Bluetooth and iOS reconnects to it by itself.
5. Test with forwarding off. Watch `curl http://<ip>:8081/logs` for `Dry run (forwarding off): ...` lines.
6. Cut over:
   - Stop the old bridge.
   - Run `curl -X POST 'http://<ip>:8081/forward?on=1'`.
   - Point `PI_HEALTH_URL` (sift-processor, sift-sms-assistant) and `BRIDGE_RESET_URL` (sift-sms-assistant) at the board.

## Updating

Over WiFi, no cable needed:

```
SIFT_ANCS_OTA_PASSWORD=<OTA_PASSWORD from config.h> pio run -e ota -t upload
```

## Troubleshooting

- **`/health` says "connected but ANCS not set up":** pairing didn't finish, or notification sharing is off for this device. Go to iPhone Settings → Bluetooth → (i) next to Sift ANCS → **Share System Notifications**.
- **Pairing is stuck or the iPhone was re-paired elsewhere:**
  1. Run `curl -X POST 'http://<ip>:8081/reset?bonds=1'`.
  2. On the iPhone, tap **Forget This Device**.
  3. Pair again.
- **Serial console:** `pio device monitor` (115200 baud).
