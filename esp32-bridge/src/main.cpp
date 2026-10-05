// Sift ANCS bridge - ESP32 replacement for the Pi's ancs4linux + ancs-bridge.
//
// Same contract as ancs-bridge/main.py on the Pi:
//   - each new iPhone notification -> POST PROCESSOR_URL
//     {"app", "title", "body", "timestamp"}
//   - GET  :8081/health  phone_connected / last_activity_ago / battery (503 if
//     the phone isn't connected) - read by sift-processor + SMS PING
//   - GET  :8081/logs    recent log lines - read by the Sift debug page
//   - GET  :8081/status  extra detail for debugging
// Plus:
//   - POST :8081/reset           reboot (replaces the SSH-based RESET command)
//   - POST :8081/reset?bonds=1   also forget the paired iPhone
//   - POST :8081/forward?on=1|0  turn forwarding on/off (persisted). Off by
//     default so a fresh board can be tested next to the Pi without
//     double-sending every notification.

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ArduinoOTA.h>
#include <HTTPClient.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WiFiManager.h>
#include <esp_coexist.h>
#include <time.h>

#include <algorithm>
#include <deque>
#include <vector>

#include "config.h"

#define FW_VERSION "1.1.0"

// --- Tunables (same values as the Pi bridge) ---------------------------------
static const uint32_t STALE_THRESHOLD_S = 900;        // "degraded" after 15 min of silence
static const uint32_t DISCONNECT_REBOOT_S = 1800;     // reboot after 30 min without the phone
static const uint32_t WIFI_DOWN_REBOOT_S = 300;       // reboot after 5 min without WiFi
static const uint32_t KUMA_INTERVAL_MS = 60000;
static const uint32_t ATTR_TIMEOUT_MS = 5000;         // wait for ANCS attribute response
static const uint32_t REPLAY_WINDOW_MS = 3000;        // iOS replays existing notifications on (re)connect
static const uint32_t LOOP_STALL_REBOOT_MS = 120000;  // software watchdog
static const size_t LOG_LINES = 150;

// --- ANCS UUIDs and protocol constants ---------------------------------------
static const NimBLEUUID ANCS_SERVICE("7905F431-B5CE-4E99-A40F-4B1E122D00D0");
static const NimBLEUUID ANCS_NOTIFICATION_SOURCE("9FBF120D-6301-42D9-8C58-25E699A21DBD");
static const NimBLEUUID ANCS_CONTROL_POINT("69D1D8F3-45E1-49A8-9821-9BBDFDAAD9D9");
static const NimBLEUUID ANCS_DATA_SOURCE("22EAC6E9-24D6-4BB5-BE44-B36ACE7C7BFB");
static const NimBLEUUID BATTERY_SERVICE((uint16_t)0x180F);
static const NimBLEUUID BATTERY_LEVEL((uint16_t)0x2A19);

enum : uint8_t { EVENT_ADDED = 0, EVENT_MODIFIED = 1, EVENT_REMOVED = 2 };
enum : uint8_t { FLAG_SILENT = 1, FLAG_IMPORTANT = 2, FLAG_PRE_EXISTING = 4 };
enum : uint8_t { ATTR_APP_ID = 0, ATTR_TITLE = 1, ATTR_SUBTITLE = 2, ATTR_MESSAGE = 3 };
static const uint16_t MAX_TITLE = 64, MAX_SUBTITLE = 64, MAX_MESSAGE = 512;

// Apps to ignore (push service echoes) and friendly names - copied from the Pi bridge.
static const char* IGNORED_APPS[] = {"me.fin.bark", "io.heckel.ntfy"};
static const struct { const char* id; const char* name; } APP_NAMES[] = {
    {"com.apple.MobileSMS", "messages"},     {"com.apple.mobilephone", "phone"},
    {"com.apple.mobilecal", "mobilecal"},    {"com.apple.reminders", "reminders"},
    {"net.whatsapp.WhatsApp", "whatsapp"},   {"com.hammerandchisel.discord", "discord"},
    {"com.atebits.Tweetie2", "twitter"},     {"com.burbn.instagram", "instagram"},
    {"com.facebook.Messenger", "messenger"}, {"com.spotify.client", "spotify"},
    {"com.google.Gmail", "gmail"},           {"com.apple.mobilemail", "mail"},
    {"com.slack.Slack", "slack"},            {"org.telegram.Telegram", "telegram"},
    {"uk.co.dpd.consumer", "dpd"},           {"com.hermes.hermesconsumer", "evri"},
    {"com.ringapp", "ring"},
};

// --- State --------------------------------------------------------------------
struct Outgoing {
  String app, title, body, timestamp;
  uint8_t attempts = 0;
  uint32_t nextTryMs = 0;
};

static WebServer web(8081);
static Preferences prefs;
static NimBLEServer* bleServer = nullptr;
static QueueHandle_t uidQueue;          // new notification UIDs from the BLE task
static QueueHandle_t preExistingQueue;  // replayed on (re)connect, sorted out in resolveReplay()
static std::vector<uint32_t> replayBurst;
static uint32_t replayDeadlineMs = 0;
static std::deque<String> logBuffer;
static std::deque<Outgoing> outbox;

static portMUX_TYPE dsLock = portMUX_INITIALIZER_UNLOCKED;
static uint8_t dsBuf[1024];
static size_t dsLen = 0;

static volatile bool phoneConnected = false;  // link up (not necessarily encrypted)
static volatile bool needSetup = false;       // encrypted, ANCS not yet subscribed
static volatile uint16_t connHandle = BLE_HS_CONN_HANDLE_NONE;
static volatile int battery = -1;
static bool ancsReady = false;
static bool forwardEnabled = false;
static String peerAddress;
static NimBLERemoteCharacteristic* controlPoint = nullptr;

static uint32_t lastActivityMs = 0;
static uint32_t lastConnectedMs = 0;
static uint32_t wifiDownSinceMs = 0;
static uint32_t lastKumaMs = 0;
static volatile uint32_t loopTickMs = 0;

static uint32_t recentUids[32];
static size_t recentUidPos = 0;

static struct {
  uint32_t forwarded = 0, dryRun = 0, postFailures = 0, skippedPreExisting = 0,
           attrTimeouts = 0, connects = 0, disconnects = 0;
} stats;

RTC_NOINIT_ATTR uint32_t rebootsForDisconnect;  // survives soft reboots

// --- Logging --------------------------------------------------------------------
static String nowIso() {
  time_t now = time(nullptr);
  if (now < 1700000000) return "";  // NTP not synced yet
  struct tm t;
  gmtime_r(&now, &t);
  char buf[32];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &t);
  return buf;
}

static void logf(const char* fmt, ...) {
  char msg[256];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(msg, sizeof(msg), fmt, ap);
  va_end(ap);
  String ts = nowIso();
  String line = (ts.length() ? ts : String("+") + String(millis() / 1000) + "s") + " " + msg;
  Serial.println(line);
  logBuffer.push_back(line);
  while (logBuffer.size() > LOG_LINES) logBuffer.pop_front();
}

static uint32_t secondsSince(uint32_t ms) { return (millis() - ms) / 1000; }

// --- ANCS: BLE callbacks (run on the NimBLE host task - keep them short) ------
static void onNotificationSource(NimBLERemoteCharacteristic*, uint8_t* data, size_t len, bool) {
  if (len < 8) return;
  uint8_t eventId = data[0], flags = data[1];
  uint32_t uid = data[4] | (data[5] << 8) | (data[6] << 16) | ((uint32_t)data[7] << 24);
  lastActivityMs = millis();
  if (eventId != EVENT_ADDED) return;
  // iOS replays everything still on the phone after each (re)connect, flagged
  // PreExisting - including anything that arrived while the link was down.
  xQueueSend((flags & FLAG_PRE_EXISTING) ? preExistingQueue : uidQueue, &uid, 0);
}

static void onDataSource(NimBLERemoteCharacteristic*, uint8_t* data, size_t len, bool) {
  portENTER_CRITICAL(&dsLock);
  size_t n = min(len, sizeof(dsBuf) - dsLen);
  memcpy(dsBuf + dsLen, data, n);
  dsLen += n;
  portEXIT_CRITICAL(&dsLock);
}

static void onBattery(NimBLERemoteCharacteristic*, uint8_t* data, size_t len, bool) {
  if (len >= 1) battery = data[0];
}

class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer*, NimBLEConnInfo& info) override {
    phoneConnected = true;
    connHandle = info.getConnHandle();
    lastConnectedMs = millis();
    stats.connects++;
    // Pairs the first time (iPhone shows a prompt), re-encrypts with the bond after.
    NimBLEDevice::startSecurity(info.getConnHandle());
  }

  void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int reason) override {
    phoneConnected = false;
    needSetup = false;
    ancsReady = false;
    controlPoint = nullptr;
    connHandle = BLE_HS_CONN_HANDLE_NONE;
    lastConnectedMs = millis();
    stats.disconnects++;
    logf("BLE disconnected (reason 0x%x)", reason);
    NimBLEDevice::startAdvertising();
  }

  void onAuthenticationComplete(NimBLEConnInfo& info) override {
    if (!info.isEncrypted()) {
      logf("BLE pairing/encryption failed - forgetting peer");
      NimBLEDevice::getServer()->disconnect(info.getConnHandle());
      return;
    }
    connHandle = info.getConnHandle();
    peerAddress = String(info.getIdAddress().toString().c_str());
    needSetup = true;  // discovery must not run on the host task
  }
};

// --- ANCS: setup + attribute fetch (run from loop) ----------------------------
static bool setupAncs() {
  NimBLEClient* client = nullptr;
  for (int i = 0; i < 5 && !client && phoneConnected; i++) {
    client = bleServer->getClient(connHandle);
    if (!client) delay(200);
  }
  if (!client) {
    logf("ANCS: no client for connection");
    return false;
  }
  NimBLERemoteService* ancs = client->getService(ANCS_SERVICE);
  if (!ancs) {
    logf("ANCS: service not found (notification sharing off for this device?)");
    return false;
  }
  auto* ns = ancs->getCharacteristic(ANCS_NOTIFICATION_SOURCE);
  auto* ds = ancs->getCharacteristic(ANCS_DATA_SOURCE);
  controlPoint = ancs->getCharacteristic(ANCS_CONTROL_POINT);
  if (!ns || !ds || !controlPoint) {
    logf("ANCS: characteristics missing");
    return false;
  }
  // Apple: subscribe to Data Source before Notification Source.
  if (!ds->subscribe(true, onDataSource) || !ns->subscribe(true, onNotificationSource)) {
    logf("ANCS: subscribe failed");
    return false;
  }

  if (NimBLERemoteService* bas = client->getService(BATTERY_SERVICE)) {
    if (auto* lvl = bas->getCharacteristic(BATTERY_LEVEL)) {
      if (lvl->canRead()) battery = lvl->readValue<uint8_t>();
      if (lvl->canNotify()) lvl->subscribe(true, onBattery);
    }
  }
  logf("ANCS ready - iPhone %s, battery %d%%", peerAddress.c_str(), (int)battery);
  return true;
}

static String normalizeApp(const String& appId) {
  for (auto& a : APP_NAMES)
    if (appId == a.id) return a.name;
  int dot = appId.lastIndexOf('.');
  String tail = dot >= 0 ? appId.substring(dot + 1) : appId;
  tail.toLowerCase();
  return tail;
}

// Parses [cmd][uid x4] then (attrId, len16, value) x4. Returns false until the
// whole response has arrived (it can span several BLE notifications).
static bool parseAttributes(const uint8_t* buf, size_t len, String out[4]) {
  if (len < 5) return false;
  size_t pos = 5;
  for (int i = 0; i < 4; i++) {
    if (pos + 3 > len) return false;
    uint8_t id = buf[pos];
    uint16_t alen = buf[pos + 1] | (buf[pos + 2] << 8);
    pos += 3;
    if (pos + alen > len) return false;
    if (id < 4) {
      String v;
      v.reserve(alen);
      for (uint16_t j = 0; j < alen; j++) v += (char)buf[pos + j];
      out[id] = v;
    }
    pos += alen;
  }
  return true;
}

static bool seenRecently(uint32_t uid) {
  for (uint32_t u : recentUids)
    if (u == uid && uid != 0) return true;
  recentUids[recentUidPos++ % 32] = uid;
  return false;
}

// Decide which replayed notifications are genuinely new: anything with a UID
// above the last one we handled arrived while the link was down. On the very
// first connection we only record the high-water mark (no flood of old ones).
static void resolveReplay() {
  bool known = prefs.isKey("lastuid");
  uint32_t last = prefs.getUInt("lastuid", 0), burstMax = 0;
  std::sort(replayBurst.begin(), replayBurst.end());
  size_t caughtUp = 0;
  for (uint32_t uid : replayBurst) {
    burstMax = max(burstMax, uid);
    if (known && uid > last && xQueueSend(uidQueue, &uid, 0) == pdTRUE) caughtUp++;
  }
  stats.skippedPreExisting += replayBurst.size() - caughtUp;
  if (!known || burstMax > last) prefs.putUInt("lastuid", max(last, burstMax));
  logf("Reconnect replay: %u existing, %u new while disconnected", (unsigned)replayBurst.size(),
       (unsigned)caughtUp);
  replayBurst.clear();
}

static void fetchAndQueue(uint32_t uid) {
  if (!controlPoint || seenRecently(uid)) return;
  prefs.putUInt("lastuid", uid);  // live UIDs can restart low after an iPhone reboot

  portENTER_CRITICAL(&dsLock);
  dsLen = 0;
  portEXIT_CRITICAL(&dsLock);

  uint8_t cmd[] = {0x00,
                   (uint8_t)uid, (uint8_t)(uid >> 8), (uint8_t)(uid >> 16), (uint8_t)(uid >> 24),
                   ATTR_APP_ID,
                   ATTR_TITLE, MAX_TITLE & 0xFF, MAX_TITLE >> 8,
                   ATTR_SUBTITLE, MAX_SUBTITLE & 0xFF, MAX_SUBTITLE >> 8,
                   ATTR_MESSAGE, MAX_MESSAGE & 0xFF, MAX_MESSAGE >> 8};
  if (!controlPoint->writeValue(cmd, sizeof(cmd), true)) {
    logf("ANCS: control point write failed for %u", uid);
    return;
  }

  String attrs[4];
  uint32_t start = millis();
  while (millis() - start < ATTR_TIMEOUT_MS) {
    uint8_t copy[sizeof(dsBuf)];
    size_t n;
    portENTER_CRITICAL(&dsLock);
    n = dsLen;
    memcpy(copy, dsBuf, n);
    portEXIT_CRITICAL(&dsLock);
    if (parseAttributes(copy, n, attrs)) break;
    delay(10);
  }
  if (attrs[ATTR_APP_ID].isEmpty()) {
    stats.attrTimeouts++;
    logf("ANCS: no attributes for %u (timeout)", uid);
    return;
  }

  for (auto* ignored : IGNORED_APPS)
    if (attrs[ATTR_APP_ID] == ignored) return;

  Outgoing o;
  o.app = normalizeApp(attrs[ATTR_APP_ID]);
  o.title = attrs[ATTR_SUBTITLE].length() ? attrs[ATTR_TITLE] + ": " + attrs[ATTR_SUBTITLE]
                                          : attrs[ATTR_TITLE];
  o.body = attrs[ATTR_MESSAGE];
  o.timestamp = nowIso();
  logf("Received: %s | %s: %.50s", attrs[ATTR_APP_ID].c_str(), o.title.c_str(), o.body.c_str());
  if (outbox.size() < 20) outbox.push_back(o);
}

// --- Outbound HTTP -------------------------------------------------------------
static void processOutbox() {
  if (outbox.empty() || WiFi.status() != WL_CONNECTED) return;
  Outgoing& o = outbox.front();
  if (millis() < o.nextTryMs) return;

  if (!forwardEnabled) {
    stats.dryRun++;
    logf("Dry run (forwarding off): %s /%s", o.app.c_str(), o.title.c_str());
    outbox.pop_front();
    return;
  }

  JsonDocument doc;
  doc["app"] = o.app;
  doc["title"] = o.title;
  doc["body"] = o.body;
  doc["timestamp"] = o.timestamp;
  String payload;
  serializeJson(doc, payload);

  HTTPClient http;
  http.setTimeout(8000);
  http.begin(PROCESSOR_URL);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(payload);
  String resp = code > 0 ? http.getString() : http.errorToString(code);
  http.end();

  if (code == 200) {
    stats.forwarded++;
    logf("Sent: %s /%s -> 200: %.80s", o.app.c_str(), o.title.c_str(), resp.c_str());
    outbox.pop_front();
  } else if (++o.attempts >= 3) {
    stats.postFailures++;
    logf("Failed to send to processor after 3 tries (%d %s) - dropped", code, resp.c_str());
    outbox.pop_front();
  } else {
    logf("Send failed (%d %s), retrying", code, resp.c_str());
    o.nextTryMs = millis() + 5000 * o.attempts;
  }
}

static void kumaHeartbeat() {
  if (!strlen(KUMA_PUSH_URL) || !ancsReady || millis() - lastKumaMs < KUMA_INTERVAL_MS) return;
  lastKumaMs = millis();
  WiFiClientSecure tls;
  tls.setInsecure();  // uptime.lan uses the LAN mkcert CA
  HTTPClient http;
  http.setTimeout(5000);
  if (http.begin(tls, String(KUMA_PUSH_URL) + "?status=up&msg=iPhone+connected")) {
    int code = http.GET();
    if (code != 200) logf("Kuma heartbeat failed: %d", code);
    http.end();
  }
}

// --- HTTP endpoints ------------------------------------------------------------
static void addCommon(JsonDocument& doc) {
  doc["active_iphone"] = peerAddress.length() ? peerAddress : (const char*)nullptr;
  doc["configured_iphone"] = (const char*)nullptr;
  if (battery >= 0) doc["battery"] = (int)battery; else doc["battery"] = nullptr;
  JsonObject w = doc["watchdog_stats"].to<JsonObject>();
  w["forwarded"] = stats.forwarded;
  w["dry_run_skipped"] = stats.dryRun;
  w["post_failures"] = stats.postFailures;
  w["attr_timeouts"] = stats.attrTimeouts;
  w["skipped_pre_existing"] = stats.skippedPreExisting;
  w["connects"] = stats.connects;
  w["disconnects"] = stats.disconnects;
  w["reboots_for_disconnect"] = rebootsForDisconnect;
  doc["forwarding"] = forwardEnabled;
  doc["firmware"] = FW_VERSION;
  doc["uptime_s"] = millis() / 1000;
}

static void sendJson(int code, JsonDocument& doc) {
  String out;
  serializeJson(doc, out);
  web.send(code, "application/json", out);
}

static void handleHealth() {
  JsonDocument doc;
  uint32_t idle = secondsSince(lastActivityMs);
  if (!ancsReady) {
    doc["status"] = "unhealthy";
    doc["phone_connected"] = false;
    doc["reason"] = phoneConnected ? "iPhone connected but ANCS not set up (pairing?)"
                                   : "iPhone not connected";
    doc["disconnected_for"] = secondsSince(lastConnectedMs);
    addCommon(doc);
    return sendJson(503, doc);
  }
  doc["status"] = idle > STALE_THRESHOLD_S ? "degraded" : "healthy";
  doc["phone_connected"] = true;
  if (idle > STALE_THRESHOLD_S) doc["reason"] = "BLE connected but no notifications received";
  doc["last_activity_ago"] = idle;
  addCommon(doc);
  sendJson(200, doc);
}

static void handleLogs() {
  size_t lines = web.hasArg("lines") ? web.arg("lines").toInt() : LOG_LINES;
  JsonDocument doc;
  JsonArray arr = doc["logs"].to<JsonArray>();
  size_t start = logBuffer.size() > lines ? logBuffer.size() - lines : 0;
  for (size_t i = start; i < logBuffer.size(); i++) arr.add(logBuffer[i]);
  doc["total_lines"] = logBuffer.size();
  doc["log_file"] = "ram (esp32)";
  sendJson(200, doc);
}

static void handleStatus() {
  JsonDocument doc;
  doc["connected"] = (bool)phoneConnected;
  doc["ancs_ready"] = ancsReady;
  doc["advertising_active"] = NimBLEDevice::getAdvertising()->isAdvertising();
  doc["bonded_devices"] = NimBLEDevice::getNumBonds();
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["free_heap"] = ESP.getFreeHeap();
  doc["min_free_heap"] = ESP.getMinFreeHeap();
  doc["outbox"] = outbox.size();
  doc["last_activity_ago"] = secondsSince(lastActivityMs);
  addCommon(doc);
  sendJson(200, doc);
}

static void handleReset() {
  bool bonds = web.hasArg("bonds") && web.arg("bonds") == "1";
  JsonDocument doc;
  doc["ok"] = true;
  doc["action"] = bonds ? "forgetting paired iPhone and restarting" : "restarting";
  sendJson(200, doc);
  logf("Reset requested via HTTP%s", bonds ? " (clearing bonds)" : "");
  delay(300);
  if (bonds) NimBLEDevice::deleteAllBonds();
  ESP.restart();
}

static void handleForward() {
  if (web.hasArg("on")) {
    forwardEnabled = web.arg("on") == "1";
    prefs.putBool("forward", forwardEnabled);
    logf("Forwarding %s", forwardEnabled ? "ON" : "OFF (dry run)");
  }
  JsonDocument doc;
  doc["forwarding"] = forwardEnabled;
  sendJson(200, doc);
}

// --- Setup ---------------------------------------------------------------------
static void startBle() {
  NimBLEDevice::init(BLE_NAME);
  esp_coex_preference_set(ESP_COEX_PREFER_BT);  // one radio: favour the BLE link over WiFi
  NimBLEDevice::setMTU(517);
  NimBLEDevice::setSecurityAuth(true, false, true);  // bond, no MITM (no screen), secure conn
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_NO_INPUT_OUTPUT);

  bleServer = NimBLEDevice::createServer();
  bleServer->setCallbacks(new ServerCallbacks());

  // Advertise "I want ANCS" (128-bit service solicitation) so iOS offers it.
  NimBLEAdvertisementData adv;
  adv.setFlags(BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP);
  uint8_t solicit[18] = {17, 0x15};
  const uint8_t* uuid = reinterpret_cast<const ble_uuid128_t*>(ANCS_SERVICE.getBase())->value;  // little-endian
  memcpy(solicit + 2, uuid, 16);
  adv.addData(solicit, sizeof(solicit));
  NimBLEAdvertisementData scan;
  scan.setName(BLE_NAME);

  NimBLEAdvertising* advertising = NimBLEDevice::getAdvertising();
  advertising->setAdvertisementData(adv);
  advertising->setScanResponseData(scan);
  advertising->enableScanResponse(true);
  NimBLEDevice::startAdvertising();
  logf("BLE advertising as '%s' (%d bonded device(s))", BLE_NAME, NimBLEDevice::getNumBonds());
}

static void startWifi() {
  WiFi.mode(WIFI_STA);
  WiFiManager wm;
  wm.setHostname("sift-ancs");
  wm.setSTAStaticIPConfig(IPAddress(STATIC_IP), IPAddress(GATEWAY_IP), IPAddress(SUBNET_MASK),
                          IPAddress(DNS_IP));
  wm.setConnectTimeout(30);
  wm.setConfigPortalTimeout(600);  // nobody configured it in 10 min -> reboot and retry
  if (!wm.autoConnect(SETUP_AP_NAME, SETUP_AP_PASSWORD)) {
    Serial.println("WiFi setup timed out - rebooting");
    ESP.restart();
  }
  WiFi.setAutoReconnect(true);
  logf("WiFi connected: %s, RSSI %d", WiFi.localIP().toString().c_str(), WiFi.RSSI());
}

static void softwareWatchdog(void*) {
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(10000));
    if (millis() - loopTickMs > LOOP_STALL_REBOOT_MS) {
      Serial.println("Main loop stalled - rebooting");
      esp_restart();
    }
  }
}

void setup() {
  Serial.begin(115200);
  if (esp_reset_reason() == ESP_RST_POWERON) rebootsForDisconnect = 0;
  uidQueue = xQueueCreate(32, sizeof(uint32_t));
  preExistingQueue = xQueueCreate(64, sizeof(uint32_t));
  prefs.begin("sift-ancs", false);
  forwardEnabled = prefs.getBool("forward", false);

  logf("Sift ANCS bridge %s starting (forwarding %s)", FW_VERSION, forwardEnabled ? "ON" : "OFF");
  startWifi();
  configTime(0, 0, "pool.ntp.org", "time.cloudflare.com");

  ArduinoOTA.setHostname("sift-ancs");
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.begin();

  web.on("/health", HTTP_GET, handleHealth);
  web.on("/logs", HTTP_GET, handleLogs);
  web.on("/status", HTTP_GET, handleStatus);
  web.on("/reset", HTTP_POST, handleReset);
  web.on("/forward", HTTP_POST, handleForward);
  web.begin();

  startBle();
  lastActivityMs = lastConnectedMs = loopTickMs = millis();
  xTaskCreate(softwareWatchdog, "swdt", 2048, nullptr, 1, nullptr);
}

void loop() {
  loopTickMs = millis();
  ArduinoOTA.handle();
  web.handleClient();

  if (needSetup) {
    needSetup = false;
    ancsReady = phoneConnected && setupAncs();
    if (ancsReady) {
      // iOS defaults to a ~0.7s supervision timeout, too tight while WiFi shares
      // the radio. Ask for 30-60ms interval, 5s timeout (within Apple's limits).
      bleServer->updateConnParams(connHandle, 24, 48, 0, 500);
      replayBurst.clear();
      replayDeadlineMs = millis() + REPLAY_WINDOW_MS;
    } else if (phoneConnected) {
      bleServer->disconnect(connHandle);  // iOS reconnects and we retry
    }
    lastActivityMs = millis();
  }

  uint32_t uid;
  while (xQueueReceive(preExistingQueue, &uid, 0) == pdTRUE) replayBurst.push_back(uid);
  if (replayDeadlineMs && millis() > replayDeadlineMs) {
    replayDeadlineMs = 0;
    resolveReplay();
  }
  if (ancsReady && !replayDeadlineMs && xQueueReceive(uidQueue, &uid, 0) == pdTRUE) fetchAndQueue(uid);

  processOutbox();
  kumaHeartbeat();

  // Self-healing (replaces the Pi's connection/staleness watchdogs).
  if (!ancsReady && secondsSince(lastConnectedMs) > DISCONNECT_REBOOT_S) {
    logf("No iPhone for %us - rebooting", DISCONNECT_REBOOT_S);
    rebootsForDisconnect++;
    delay(200);
    ESP.restart();
  }
  if (WiFi.status() != WL_CONNECTED) {
    if (!wifiDownSinceMs) wifiDownSinceMs = millis();
    if (secondsSince(wifiDownSinceMs) > WIFI_DOWN_REBOOT_S) ESP.restart();
  } else {
    wifiDownSinceMs = 0;
  }
  if (!phoneConnected && !NimBLEDevice::getAdvertising()->isAdvertising())
    NimBLEDevice::startAdvertising();

  delay(5);
}
