/*
  Fennsill panel firmware for the Seeed TRMNL 7.5" DIY kit (XIAO ESP32-S3 Plus + EE04).

  Board: esp32:esp32:XIAO_ESP32S3_Plus
  USB Mode: Hardware CDC and JTAG
  USB CDC On Boot: Enabled (menu value "cdc" means Disabled on this core)
  PSRAM: OPI PSRAM
  Library: Seeed_GFX with driver.h beside this sketch

  Boot turns on panel power (GPIO 43), then draws the Fennsill splash.
  Dashboards arrive over USB from the Fennsill desktop app (frames only).
  Cloud MCP / account auth is not on this device — USB is the trust boundary.

  Privacy: Wi-Fi SSID/PSK stay in NVS. Never print them on Serial.
  OTA: HTTPS manifest + HMAC signature + SHA-256 of binary; user confirms on buttons.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <Update.h>
#include <Preferences.h>
#include <esp_sleep.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>
#include <mbedtls/base64.h>
#include <TFT_eSPI.h>
#include "driver.h"
#include "update_key.h"
#include "splash_frame.h"
// Optional USB SETUP drive (TinyUSB only). Keep off for Hardware CDC builds.
// #define FENNSILL_USB_INSTALLER
#include "usb_installer.h"

#ifdef EPAPER_ENABLE
EPaper epaper;
#endif

static const char *FW_VERSION = "1.2.0";
static const char *DEFAULT_MANIFEST = "https://updates.fennsill.com/manifest.json";
static const int FRAME_W = 800;
static const int FRAME_H = 480;
static const int ROW_BYTES = 100;
static const int FRAME_BYTES = 48000;
static const int CHUNK_SIZE = 1024;
static const uint32_t BUSY_TIMEOUT_MS = 15000;
static const uint64_t DAY_US = 24ULL * 60ULL * 60ULL * 1000000ULL;

static Preferences prefs;
static char deviceId[20];
static uint8_t frameStore[FRAME_BYTES];
static bool chunkGot[64];
static uint16_t chunkTotal = 0;
static bool repairMode = false;
static bool readySent = false;
static bool yesWasDown = false;
static bool noWasDown = false;
static unsigned long lastUsb = 0;

static bool asking = false;
static String offerVersion;
static String offerUrl;
static String offerSha;

enum class RxPhase { Line, Magic, Header, Body };
static RxPhase rxPhase = RxPhase::Line;
static uint8_t magic[4];
static uint8_t header[10];
static uint8_t body[CHUNK_SIZE];
static size_t got = 0;
static size_t headerNeed = 0;
static uint16_t chunkIndex = 0;
static uint16_t chunkLength = 0;
static uint32_t chunkCrc = 0;
static bool headerIsShow = false;
static char lineBuf[280];
static size_t lineLen = 0;

static uint16_t read16(const uint8_t *bytes) {
  return (uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8);
}

static uint32_t read32(const uint8_t *bytes) {
  return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) | ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static uint32_t crc32Bytes(const uint8_t *data, size_t len) {
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; bit++) {
      uint32_t mask = -(crc & 1u);
      crc = (crc >> 1) ^ (0xEDB88320u & mask);
    }
  }
  return ~crc;
}

static void panelPower(bool on) {
  pinMode(PIN_ENABLE, OUTPUT);
  digitalWrite(PIN_ENABLE, on ? HIGH : LOW);
  delay(on ? 200 : 10);
}

static bool panelReady() {
  pinMode(PIN_BUSY, INPUT);
  uint32_t start = millis();
  // UC8179 on EE04: BUSY stays HIGH while refreshing.
  while (digitalRead(PIN_BUSY) == HIGH) {
    if (millis() - start >= BUSY_TIMEOUT_MS) return false;
    delay(10);
  }
  return true;
}

static void reportDisplayError() {
  Serial.println("ERR display not detected");
}

static void initDeviceId() {
  uint64_t mac = ESP.getEfuseMac();
  // Stable USB pairing id (not a cloud secret). Format: FS + 12 hex (MAC).
  snprintf(deviceId, sizeof(deviceId), "FS%02X%02X%02X%02X%02X%02X",
           (unsigned)(mac & 0xFF),
           (unsigned)((mac >> 8) & 0xFF),
           (unsigned)((mac >> 16) & 0xFF),
           (unsigned)((mac >> 24) & 0xFF),
           (unsigned)((mac >> 32) & 0xFF),
           (unsigned)((mac >> 40) & 0xFF));
}

static const char *panelSerial() {
  // Human serial locked at factory; falls back to chip id (never changes either).
  static char buf[40];
  String saved = prefs.getString("serial", "");
  if (saved.length() > 0) {
    saved.toCharArray(buf, sizeof(buf));
    return buf;
  }
  return deviceId;
}

static bool serialAllowed(const char *text) {
  size_t n = strlen(text);
  if (n < 4 || n > 32) return false;
  for (size_t i = 0; i < n; i++) {
    char c = text[i];
    bool ok = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '-';
    if (!ok) return false;
  }
  return true;
}

static bool hex64Ok(const char *text) {
  if (strlen(text) != 64) return false;
  for (int i = 0; i < 64; i++) {
    char c = text[i];
    bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
    if (!ok) return false;
  }
  return true;
}

static void printReady() {
  Serial.print("READY ");
  Serial.print(FW_VERSION);
  Serial.print(" id=");
  Serial.print(deviceId);
  Serial.print(" serial=");
  Serial.println(panelSerial());
}

static int versionPart(const String &version, int index) {
  int start = 0;
  int current = 0;
  for (int i = 0; i <= version.length(); i++) {
    if (i == version.length() || version[i] == '.') {
      if (current == index) return version.substring(start, i).toInt();
      current++;
      start = i + 1;
    }
  }
  return 0;
}

static bool isNewer(const String &offer) {
  for (int i = 0; i < 3; i++) {
    int left = versionPart(offer, i);
    int right = versionPart(String(FW_VERSION), i);
    if (left != right) return left > right;
  }
  return false;
}

static String toHex(const uint8_t *bytes, size_t len) {
  String out;
  out.reserve(len * 2);
  for (size_t i = 0; i < len; i++) {
    char cell[3];
    sprintf(cell, "%02x", bytes[i]);
    out += cell;
  }
  return out;
}

static bool hexEqual(const String &hex, const uint8_t *bytes, size_t len) {
  return hex.equalsIgnoreCase(toHex(bytes, len));
}

static bool signatureOk(const String &version, const String &sha, const String &signature) {
  String message = version + "\n" + sha;
  uint8_t out[32];
  if (mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), UPDATE_KEY, sizeof(UPDATE_KEY),
                      (const unsigned char *)message.c_str(), message.length(), out) != 0) {
    return false;
  }
  return hexEqual(signature, out, sizeof(out));
}

static int hexNibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

static bool parseHexKey(const String &hex, uint8_t out[32]) {
  if (hex.length() != 64) return false;
  for (int i = 0; i < 32; i++) {
    int hi = hexNibble(hex[i * 2]);
    int lo = hexNibble(hex[i * 2 + 1]);
    if (hi < 0 || lo < 0) return false;
    out[i] = (uint8_t)((hi << 4) | lo);
  }
  return true;
}

static void answerChallenge(const char *nonce) {
  size_t n = strlen(nonce);
  if (n < 8 || n > 128) {
    Serial.println("NAK 0");
    return;
  }
  String hexKey = prefs.getString("dkey", "");
  uint8_t key[32];
  if (!parseHexKey(hexKey, key)) {
    Serial.println("ERR key missing");
    return;
  }
  uint8_t out[32];
  if (mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), key, sizeof(key),
                      (const unsigned char *)nonce, n, out) != 0) {
    Serial.println("ERR challenge");
    return;
  }
  Serial.print("PROOF ");
  Serial.println(toHex(out, sizeof(out)));
}

static String jsonString(const String &body, const char *key) {
  String pattern = String("\"") + key + "\"";
  int at = body.indexOf(pattern);
  if (at < 0) return "";
  int colon = body.indexOf(':', at + pattern.length());
  int first = body.indexOf('"', colon + 1);
  if (colon < 0 || first < 0) return "";
  String value;
  for (int i = first + 1; i < body.length(); i++) {
    if (body[i] == '\\' && i + 1 < body.length()) {
      value += body[i + 1];
      i++;
      continue;
    }
    if (body[i] == '"') break;
    value += body[i];
  }
  return value;
}

static bool decodeB64(const String &text, String &out) {
  size_t olen = 0;
  unsigned char buffer[128];
  int rc = mbedtls_base64_decode(buffer, sizeof(buffer), &olen, (const unsigned char *)text.c_str(), text.length());
  if (rc != 0 || olen >= sizeof(buffer)) return false;
  buffer[olen] = 0;
  out = String((char *)buffer);
  return true;
}

static void paintFrame(const uint8_t *frame) {
#ifdef EPAPER_ENABLE
  // Seeed_GFX waits on BUSY inside update(). Do not block forever before drawing.
  epaper.fillScreen(TFT_WHITE);
  for (int y = 0; y < FRAME_H; y++) {
    const uint8_t *row = frame + y * ROW_BYTES;
    for (int x = 0; x < FRAME_W; x++) {
      bool white = row[x >> 3] & (0x80 >> (x & 7));
      if (!white) epaper.drawPixel(x, y, TFT_BLACK);
    }
  }
  epaper.update();
  if (!panelReady()) {
    reportDisplayError();
    return;
  }
#else
  reportDisplayError();
#endif
}

static void drawFrame() {
  paintFrame(frameStore);
  Serial.println("OK");
}

static void showSplash() {
  memcpy_P(frameStore, SPLASH_FRAME, FRAME_BYTES);
  paintFrame(frameStore);
  Serial.println("SPLASH");
}

static void drawQuestion() {
  Serial.print("UPDATE ");
  Serial.println(offerVersion);
  if (!panelReady()) {
    reportDisplayError();
    return;
  }
#ifdef EPAPER_ENABLE
  epaper.fillScreen(TFT_WHITE);
  epaper.setTextColor(TFT_BLACK, TFT_WHITE);
  epaper.setTextSize(3);
  epaper.setCursor(24, 70);
  epaper.print("Software update");
  epaper.setCursor(24, 130);
  epaper.print(offerVersion);
  epaper.setTextSize(2);
  epaper.setCursor(24, 210);
  epaper.print("Top button installs it");
  epaper.setCursor(24, 246);
  epaper.print("Middle button skips it");
  epaper.update();
#endif
  if (!panelReady()) reportDisplayError();
}

static void declineUpdate() {
  asking = false;
  offerVersion = "";
  offerUrl = "";
  offerSha = "";
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  Serial.println("OK");
}

static bool installOffer() {
  if (!offerUrl.startsWith("https://")) {
    Serial.println("ERR ota url");
    asking = false;
    return false;
  }
  HTTPClient http;
  http.setTimeout(30000);
  http.begin(offerUrl);
  int status = http.GET();
  int size = http.getSize();
  if (status != 200 || size <= 0) {
    http.end();
    Serial.println("ERR ota http");
    asking = false;
    return false;
  }
  if (!Update.begin(size)) {
    http.end();
    Serial.println("ERR ota begin");
    asking = false;
    return false;
  }
  WiFiClient *stream = http.getStreamPtr();
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
#if defined(MBEDTLS_VERSION_NUMBER) && MBEDTLS_VERSION_NUMBER >= 0x03000000
  mbedtls_sha256_starts(&ctx, 0);
#else
  mbedtls_sha256_starts_ret(&ctx, 0);
#endif
  uint8_t buffer[1024];
  int remaining = size;
  bool writeFail = false;
  while (remaining > 0) {
    int n = stream->readBytes(buffer, remaining > (int)sizeof(buffer) ? sizeof(buffer) : remaining);
    if (n <= 0) break;
    if (Update.write(buffer, n) != (size_t)n) {
      writeFail = true;
      break;
    }
#if defined(MBEDTLS_VERSION_NUMBER) && MBEDTLS_VERSION_NUMBER >= 0x03000000
    mbedtls_sha256_update(&ctx, buffer, n);
#else
    mbedtls_sha256_update_ret(&ctx, buffer, n);
#endif
    remaining -= n;
  }
  uint8_t hash[32];
#if defined(MBEDTLS_VERSION_NUMBER) && MBEDTLS_VERSION_NUMBER >= 0x03000000
  mbedtls_sha256_finish(&ctx, hash);
#else
  mbedtls_sha256_finish_ret(&ctx, hash);
#endif
  mbedtls_sha256_free(&ctx);
  http.end();
  if (writeFail) {
    Update.abort();
    Serial.println("ERR ota write");
    asking = false;
    return false;
  }
  if (remaining != 0 || !hexEqual(offerSha, hash, sizeof(hash))) {
    Update.abort();
    Serial.println("ERR ota sha");
    asking = false;
    return false;
  }
  if (!Update.end(true)) {
    Serial.println("ERR ota end");
    asking = false;
    return false;
  }
  Serial.println("OK");
  delay(100);
  ESP.restart();
  return true;
}

static void checkForUpdate() {
  String ssid = prefs.getString("ssid", "");
  if (ssid.length() == 0) return;
  // PSK leaves NVS only into WiFi.begin — never Serial.
  String psk = prefs.getString("psk", "");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid.c_str(), psk.c_str());
  psk = "";
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) delay(200);
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    return;
  }

  String manifestUrl = prefs.getString("updates", DEFAULT_MANIFEST);
  if (!manifestUrl.startsWith("https://")) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    Serial.println("ERR ota url");
    return;
  }
  HTTPClient http;
  http.setTimeout(15000);
  http.begin(manifestUrl);
  if (http.GET() != 200) {
    http.end();
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    return;
  }
  String body = http.getString();
  http.end();
  String version = jsonString(body, "version");
  String url = jsonString(body, "url");
  String sha = jsonString(body, "sha256");
  String signature = jsonString(body, "signature");
  if (version.length() == 0 || url.length() == 0 || sha.length() == 0 || signature.length() == 0 ||
      !signatureOk(version, sha, signature)) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    Serial.println("ERR bad signature");
    return;
  }
  if (!url.startsWith("https://")) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    Serial.println("ERR ota url");
    return;
  }
  if (!isNewer(version)) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    return;
  }
  offerVersion = version;
  offerUrl = url;
  offerSha = sha;
  asking = true;
  drawQuestion();
  // Stay on Wi-Fi while the user decides; installOffer needs it.
}

static void handleLine(char *line) {
  if (strcmp(line, "HELLO") == 0 || strcmp(line, "READY?") == 0) {
    printReady();
    readySent = true;
    return;
  }
  if (strcmp(line, "ID?") == 0 || strcmp(line, "WHOAMI") == 0) {
    Serial.print("ID ");
    Serial.println(deviceId);
    return;
  }
  if (strcmp(line, "SERIAL?") == 0) {
    Serial.print("SERIAL ");
    Serial.println(panelSerial());
    return;
  }
  if (strncmp(line, "SERIALSET ", 10) == 0) {
    // Write-once factory serial. Survives PC changes; cannot be overwritten.
    if (prefs.getString("serial", "").length() > 0) {
      Serial.println("ERR serial locked");
      return;
    }
    const char *value = line + 10;
    if (!serialAllowed(value)) {
      Serial.println("NAK 0");
      return;
    }
    prefs.putString("serial", value);
    Serial.println("OK");
    return;
  }
  if (strcmp(line, "KEY?") == 0) {
    // Never dump the device key — only whether factory locked one in.
    Serial.print("KEY ");
    Serial.println(prefs.getString("dkey", "").length() == 64 ? "locked" : "missing");
    return;
  }
  if (strncmp(line, "KEYSET ", 7) == 0) {
    // Write-once device secret (64 hex). Used to bind Fennsill installs / cloud claim.
    if (prefs.getString("dkey", "").length() == 64) {
      Serial.println("ERR key locked");
      return;
    }
    const char *value = line + 7;
    if (!hex64Ok(value)) {
      Serial.println("NAK 0");
      return;
    }
    prefs.putString("dkey", value);
    Serial.println("OK");
    return;
  }
  if (strncmp(line, "CHALLENGE ", 10) == 0) {
    answerChallenge(line + 10);
    return;
  }
  if (asking && strcmp(line, "YES") == 0) {
    installOffer();
    return;
  }
  if (asking && strcmp(line, "NO") == 0) {
    declineUpdate();
    return;
  }
  if (strcmp(line, "FORGET") == 0) {
    prefs.remove("ssid");
    prefs.remove("psk");
    Serial.println("OK");
    return;
  }
  if (strcmp(line, "STATUS") == 0) {
    // Never include SSID, PSK, or device key — flags only.
    Serial.print("STATUS version=");
    Serial.print(FW_VERSION);
    Serial.print(" id=");
    Serial.print(deviceId);
    Serial.print(" serial=");
    Serial.print(panelSerial());
    Serial.print(" key=");
    Serial.print(prefs.getString("dkey", "").length() == 64 ? "1" : "0");
    Serial.print(" wifi=");
    Serial.println(prefs.getString("ssid", "").length() ? "1" : "0");
    return;
  }
  if (strncmp(line, "WIFI ", 5) == 0) {
    char *ssidB64 = line + 5;
    char *split = strchr(ssidB64, ' ');
    if (!split) {
      Serial.println("NAK 0");
      return;
    }
    *split = 0;
    String ssid;
    String pass;
    if (!decodeB64(ssidB64, ssid) || !decodeB64(split + 1, pass)) {
      Serial.println("NAK 0");
      return;
    }
    prefs.putString("ssid", ssid);
    prefs.putString("psk", pass);
    // Echo OK only — do not print decoded SSID/PSK.
    Serial.println("OK");
    return;
  }
  if (strncmp(line, "UPDATES ", 8) == 0) {
    String url = String(line + 8);
    url.trim();
    if (!url.startsWith("https://")) {
      Serial.println("NAK 0");
      return;
    }
    prefs.putString("updates", url);
    Serial.println("OK");
    return;
  }
  Serial.println("NAK 0");
}

static void handleChunk() {
  bool bad = chunkLength > CHUNK_SIZE || chunkIndex >= 64 || chunkTotal == 0 || chunkTotal > 64;
  bad = bad || crc32Bytes(body, chunkLength) != chunkCrc;
  bad = bad || (size_t)chunkIndex * CHUNK_SIZE + chunkLength > FRAME_BYTES;
  if (bad) {
    Serial.print("NAK ");
    Serial.println(chunkIndex);
    return;
  }
  memcpy(frameStore + (size_t)chunkIndex * CHUNK_SIZE, body, chunkLength);
  chunkGot[chunkIndex] = true;
  Serial.print("ACK ");
  Serial.println(chunkIndex);
}

static void handleShow(uint32_t expected) {
  bool complete = chunkTotal > 0;
  for (uint16_t i = 0; complete && i < chunkTotal; i++) {
    if (!chunkGot[i]) complete = false;
  }
  if (!complete || crc32Bytes(frameStore, FRAME_BYTES) != expected) {
    Serial.println("NAK 0");
    return;
  }
  drawFrame();
  memset(chunkGot, 0, sizeof(chunkGot));
  chunkTotal = 0;
}

static void onByte(uint8_t byte) {
  repairMode = true;
  lastUsb = millis();
  if (rxPhase == RxPhase::Line) {
    if (lineLen == 0 && byte == 'A') {
      magic[0] = byte;
      got = 1;
      rxPhase = RxPhase::Magic;
      return;
    }
    if (byte == '\n') {
      lineBuf[lineLen] = 0;
      lineLen = 0;
      handleLine(lineBuf);
      return;
    }
    if (lineLen < sizeof(lineBuf) - 1) lineBuf[lineLen++] = (char)byte;
    return;
  }
  if (rxPhase == RxPhase::Magic) {
    magic[got++] = byte;
    if (got < 4) return;
    headerIsShow = memcmp(magic, "AFS1", 4) == 0;
    bool isChunk = memcmp(magic, "AFC1", 4) == 0;
    if (!headerIsShow && !isChunk) {
      rxPhase = RxPhase::Line;
      lineLen = 0;
      return;
    }
    headerNeed = headerIsShow ? 4 : 10;
    got = 0;
    rxPhase = RxPhase::Header;
    return;
  }
  if (rxPhase == RxPhase::Header) {
    header[got++] = byte;
    if (got < headerNeed) return;
    if (headerIsShow) {
      uint32_t expected = read32(header);
      rxPhase = RxPhase::Line;
      handleShow(expected);
      return;
    }
    chunkIndex = read16(header);
    chunkTotal = read16(header + 2);
    chunkLength = read16(header + 4);
    chunkCrc = read32(header + 6);
    if (chunkLength > CHUNK_SIZE) {
      Serial.print("NAK ");
      Serial.println(chunkIndex);
      rxPhase = RxPhase::Line;
      return;
    }
    got = 0;
    rxPhase = RxPhase::Body;
    return;
  }
  body[got++] = byte;
  if (got < chunkLength) return;
  rxPhase = RxPhase::Line;
  handleChunk();
}

static void pollUsb() {
  if (!readySent) {
    printReady();
    readySent = true;
  }
  while (Serial.available()) onByte((uint8_t)Serial.read());
}

static void maybeSleep() {
  if (asking || repairMode) return;
  if (prefs.getString("ssid", "").length() == 0) return;
  if (millis() - lastUsb < 30000) return;
  uint64_t mask = (1ULL << PIN_YES) | (1ULL << PIN_NO) | (1ULL << PIN_WAKE);
  esp_sleep_enable_timer_wakeup(DAY_US);
  esp_sleep_enable_ext1_wakeup(mask, ESP_EXT1_WAKEUP_ANY_LOW);
  esp_deep_sleep_start();
}

void setup() {
  // Optional: show FENNSILL USB drive with SETUP.BAT for first-time PC install.
  fennsillMscStart();

  Serial.setRxBufferSize(65536);
  Serial.begin(115200);
  delay(200);
  // Do not announce READY until after splash. E-ink paint blocks USB handling,
  // and an early READY makes the host start pushing while setup() is still busy.

  prefs.begin("fennsill", false);
  initDeviceId();
  pinMode(PIN_YES, INPUT_PULLUP);
  pinMode(PIN_NO, INPUT_PULLUP);
  pinMode(PIN_WAKE, INPUT_PULLUP);

  panelPower(true);
#ifdef EPAPER_ENABLE
  epaper.begin();
#else
  Serial.println("ERR Seeed_GFX epaper disabled");
#endif
  lastUsb = millis();
  showSplash();
  checkForUpdate();
  printReady();
  readySent = true;
}

void loop() {
  pollUsb();
  bool yesDown = digitalRead(PIN_YES) == LOW;
  bool noDown = digitalRead(PIN_NO) == LOW;
  if (asking && yesDown && !yesWasDown) installOffer();
  if (asking && noDown && !noWasDown) declineUpdate();
  yesWasDown = yesDown;
  noWasDown = noDown;
  maybeSleep();
}
