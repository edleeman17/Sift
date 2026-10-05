// Copy to config.h and fill in. config.h is gitignored.
#pragma once

// Where notifications go (sift-processor).
#define PROCESSOR_URL "http://192.168.1.95:8090/notification"

// Uptime Kuma push monitor, pinged every 60s while the iPhone is connected.
// Leave empty to disable.
#define KUMA_PUSH_URL "https://uptime.lan/api/push/CHANGEME"

// Fixed LAN address (consumers use http://<this>:8081/health).
#define STATIC_IP 192, 168, 1, 55
#define GATEWAY_IP 192, 168, 1, 1
#define SUBNET_MASK 255, 255, 255, 0
#define DNS_IP 192, 168, 1, 53

// First-boot WiFi setup hotspot (join it from a phone, pick your network).
#define SETUP_AP_NAME "Sift-ANCS-Setup"
#define SETUP_AP_PASSWORD "CHANGEME"  // 8+ chars

// Password for over-the-air firmware updates (pio run -e ota -t upload).
#define OTA_PASSWORD "CHANGEME"

// Bluetooth name the iPhone sees.
#define BLE_NAME "Sift ANCS"
