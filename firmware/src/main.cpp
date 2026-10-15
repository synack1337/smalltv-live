// SmallTV Live firmware for the GeekMagic SmallTV-Ultra (ESP-12F / ESP8266, 240x240 ST7789 IPS).
//
// The TV becomes a WiFi display. A host renders the screen and streams changed rectangles of RGB565
// pixels over TCP; they are written straight to the panel. There is no framebuffer and nothing is
// written to flash while streaming.
//
// Compatibility with the stock firmware:
//  - The flash layout matches the stock Ultra firmware (4M3M) and LittleFS is never mounted, so the
//    stock filesystem (its web UI, settings and images) stays intact and the stock firmware can be
//    flashed back through /update.
//  - WiFi uses the station credentials stored in the SDK config. If they are missing or fail, an open
//    "SmallTV-Live" access point serves a WiFi form and /update at 192.168.4.1.
//
// See docs/protocol.md for the wire format and docs/security.md for the threat model.
#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266mDNS.h>
#include <SPI.h>

#ifndef FW_VERSION
#define FW_VERSION "1.0.0"
#endif

namespace {

// Pins: SCLK 14 and MOSI 13 are the fixed hardware SPI pins.
constexpr uint8_t PIN_DC = 0;
constexpr uint8_t PIN_RST = 2;
constexpr uint8_t PIN_CS = 15;
constexpr uint8_t PIN_BL = 5;          // backlight, active low

constexpr uint16_t WIDTH = 240;
constexpr uint16_t HEIGHT = 240;
constexpr uint16_t STREAM_PORT = 7777;
constexpr uint8_t DEFAULT_BACKLIGHT = 160;
constexpr uint32_t MAINTENANCE_WINDOW_MS = 10UL * 60UL * 1000UL;   // firmware upload and WiFi change after power-on
constexpr uint32_t HOST_SILENT_MS = 15UL * 1000UL;          // drop a host that sends nothing
constexpr uint32_t IDLE_SCREEN_MS = 2UL * 60UL * 1000UL;      // host silent this long: show the IP
constexpr uint32_t WIFI_JOIN_MS = 30UL * 1000UL;
constexpr uint32_t WIFI_RETRY_MS = 30UL * 1000UL;
constexpr uint32_t SETUP_RETRY_EVERY_MS = 2UL * 60UL * 1000UL;   // setup mode: try the saved network again
constexpr uint32_t SETUP_RETRY_FOR_MS = 15UL * 1000UL;
constexpr const char* HOSTNAME = "smalltv";
constexpr const char* SETUP_AP = "SmallTV-Live";

constexpr uint16_t COLOR_BLACK = 0x0000;
constexpr uint16_t COLOR_WHITE = 0xFFFF;
constexpr uint16_t COLOR_GREY = 0x4208;
constexpr uint16_t COLOR_GREEN = 0x07E0;
constexpr uint16_t COLOR_AMBER = 0xFD20;

ESP8266WebServer web(80);
WiFiServer streamServer(STREAM_PORT);
WiFiClient host;

bool setupMode = false;
String savedSsid;                    // network stored in the SDK config at boot
String savedPass;
uint8_t backlight = DEFAULT_BACKLIGHT;
uint32_t lastFrameMs = 0;
uint32_t framesShown = 0;
uint32_t bytesIn = 0;
uint32_t lastRxMs = 0;
bool streamedSinceIdle = false;

// Firmware upload state
bool updateRejected = false;
String updateError;

// ------------------------------------------------------------------ panel

inline void panelCommand(uint8_t c) {
  digitalWrite(PIN_DC, LOW);
  SPI.write(c);
  digitalWrite(PIN_DC, HIGH);
}

inline void panelData(uint8_t d) { SPI.write(d); }

void setBacklight(uint8_t level) {
  backlight = level;
  analogWrite(PIN_BL, 255 - level);
}

// Opens a write window; pixel bytes (RGB565, big endian) follow with DC high.
void panelWindow(uint16_t x, uint16_t y, uint16_t w, uint16_t h) {
  const uint16_t x1 = x + w - 1;
  const uint16_t y1 = y + h - 1;
  panelCommand(0x2A);  // CASET
  panelData(x >> 8); panelData(x & 0xFF); panelData(x1 >> 8); panelData(x1 & 0xFF);
  panelCommand(0x2B);  // RASET
  panelData(y >> 8); panelData(y & 0xFF); panelData(y1 >> 8); panelData(y1 & 0xFF);
  panelCommand(0x2C);  // RAMWR
}

void panelFill(uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t color) {
  panelWindow(x, y, w, h);
  uint8_t chunk[64];
  for (size_t i = 0; i < sizeof(chunk); i += 2) {
    chunk[i] = color >> 8;
    chunk[i + 1] = color & 0xFF;
  }
  uint32_t left = static_cast<uint32_t>(w) * h * 2;
  while (left) {
    const uint32_t n = left > sizeof(chunk) ? sizeof(chunk) : left;
    SPI.writeBytes(chunk, n);
    left -= n;
  }
}

void panelInit() {
  pinMode(PIN_DC, OUTPUT);
  digitalWrite(PIN_DC, HIGH);
  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, LOW);           // the panel is the only device on the bus
  pinMode(PIN_RST, OUTPUT);
  digitalWrite(PIN_RST, HIGH); delay(5);
  digitalWrite(PIN_RST, LOW); delay(20);
  digitalWrite(PIN_RST, HIGH); delay(150);

  SPI.begin();
  SPI.setFrequency(40000000);
  SPI.setDataMode(SPI_MODE3);

  panelCommand(0x01); delay(150);                     // SWRESET
  panelCommand(0x11); delay(120);                     // SLPOUT
  panelCommand(0x3A); panelData(0x55); delay(10);     // COLMOD: 16 bits per pixel
  panelCommand(0x36); panelData(0x00);                // MADCTL: RGB order, no rotation
  panelCommand(0x21);                                 // INVON: IPS panel
  panelCommand(0x13);                                 // NORON
  panelFill(0, 0, WIDTH, HEIGHT, COLOR_BLACK);
  panelCommand(0x29); delay(10);                      // DISPON
}

// ------------------------------------------------------------------ status screen

// Seven-segment digits avoid shipping a font. Cell is 14x24 px with a 3 px stroke.
void drawDigit(int x, int y, char ch, uint16_t color) {
  static const uint8_t SEGMENTS[10] = {0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F};
  if (ch == '.') {
    panelFill(x + 2, y + 21, 3, 3, color);
    return;
  }
  if (ch < '0' || ch > '9') return;
  const uint8_t s = SEGMENTS[ch - '0'];
  if (s & 0x01) panelFill(x + 2, y, 10, 3, color);
  if (s & 0x02) panelFill(x + 11, y + 2, 3, 10, color);
  if (s & 0x04) panelFill(x + 11, y + 12, 3, 10, color);
  if (s & 0x08) panelFill(x + 2, y + 21, 10, 3, color);
  if (s & 0x10) panelFill(x, y + 12, 3, 10, color);
  if (s & 0x20) panelFill(x, y + 2, 3, 10, color);
  if (s & 0x40) panelFill(x + 2, y + 10, 10, 3, color);
}

// Green bars: online, waiting for the host. Amber bars: setup access point.
void drawStatusScreen() {
  const String ip = setupMode ? WiFi.softAPIP().toString() : WiFi.localIP().toString();
  const uint16_t accent = setupMode ? COLOR_AMBER : COLOR_GREEN;
  panelFill(0, 0, WIDTH, HEIGHT, COLOR_BLACK);
  panelFill(20, 70, 200, 4, accent);
  int width = 0;
  for (char ch : ip) width += (ch == '.') ? 7 : 17;
  int x = (WIDTH - width) / 2;
  for (char ch : ip) {
    drawDigit(x, 108, ch, COLOR_WHITE);
    x += (ch == '.') ? 7 : 17;
  }
  panelFill(20, 166, 200, 4, accent);
}

// ------------------------------------------------------------------ stream protocol

constexpr size_t HEADER_SIZE = 9;
constexpr size_t MAX_PARAMS = 4;

enum class StreamState { Header, Pixels, Params };

StreamState streamState = StreamState::Header;
uint8_t header[HEADER_SIZE];
size_t headerFill = 0;
uint32_t payloadLeft = 0;
uint8_t panelCmd = 0;
uint8_t params[MAX_PARAMS];
size_t paramFill = 0;
uint8_t rxBuffer[1460];

void resetStream() {
  streamState = StreamState::Header;
  headerFill = 0;
  payloadLeft = 0;
  paramFill = 0;
}

void dropHost() {
  host.stop();
  resetStream();
}

// Panel commands the host may send: inversion on/off and memory access control (colour order).
bool panelCommandAllowed(uint8_t c, uint32_t len) {
  return ((c == 0x20 || c == 0x21) && len == 0) || (c == 0x36 && len == 1);
}

void startMessage() {
  const uint8_t type = header[0];
  const uint16_t x = header[1];
  const uint16_t y = header[2];
  const uint16_t w = static_cast<uint16_t>(header[3]) + 1;
  const uint16_t h = static_cast<uint16_t>(header[4]) + 1;
  payloadLeft = static_cast<uint32_t>(header[5]) | (static_cast<uint32_t>(header[6]) << 8) |
                (static_cast<uint32_t>(header[7]) << 16) | (static_cast<uint32_t>(header[8]) << 24);

  switch (type) {
    case 'R':
      if (x + w > WIDTH || y + h > HEIGHT || payloadLeft != static_cast<uint32_t>(w) * h * 2) {
        dropHost();
        return;
      }
      panelWindow(x, y, w, h);
      streamState = StreamState::Pixels;
      return;
    case 'F':
      if (payloadLeft != 0) { dropHost(); return; }
      host.write('K');
      framesShown++;
      lastFrameMs = millis();
      streamedSinceIdle = true;
      return;
    case 'B':
      if (payloadLeft != 0) { dropHost(); return; }
      setBacklight(static_cast<uint8_t>(x));
      return;
    case 'C':
      if (!panelCommandAllowed(static_cast<uint8_t>(x), payloadLeft)) { dropHost(); return; }
      panelCmd = static_cast<uint8_t>(x);
      paramFill = 0;
      if (payloadLeft == 0) {
        panelCommand(panelCmd);
      } else {
        streamState = StreamState::Params;
      }
      return;
    default:
      dropHost();
      return;
  }
}

void pumpStream() {
  // The newest connection wins: a host that reconnects must not be locked out by a stale session.
  WiFiClient incoming = streamServer.accept();
  if (incoming) {
    if (host) host.stop();
    host = incoming;
    host.setNoDelay(true);
    resetStream();
    lastRxMs = millis();
  }
  if (!host || !host.connected()) {
    if (host) dropHost();
    return;
  }
  if (millis() - lastRxMs > HOST_SILENT_MS) {   // half-open or hung connection
    dropHost();
    return;
  }

  // Bounded work per loop() so the web server and WiFi stack keep running.
  for (int i = 0; i < 32; i++) {
    const int available = host.available();
    if (available <= 0) return;

    if (streamState == StreamState::Header) {
      const int n = host.read(header + headerFill, min(static_cast<size_t>(available), HEADER_SIZE - headerFill));
      if (n <= 0) return;
      headerFill += n;
      bytesIn += n;
      lastRxMs = millis();
      if (headerFill == HEADER_SIZE) {
        headerFill = 0;
        startMessage();
      }
      continue;
    }

    const size_t want = min(static_cast<size_t>(available), min(static_cast<size_t>(payloadLeft), sizeof(rxBuffer)));
    const int n = host.read(rxBuffer, want);
    if (n <= 0) return;
    payloadLeft -= n;
    bytesIn += n;
    lastRxMs = millis();

    if (streamState == StreamState::Pixels) {
      SPI.writeBytes(rxBuffer, n);
    } else {
      for (int k = 0; k < n && paramFill < MAX_PARAMS; k++) params[paramFill++] = rxBuffer[k];
      if (payloadLeft == 0) {
        panelCommand(panelCmd);
        for (size_t k = 0; k < paramFill; k++) panelData(params[k]);
      }
    }
    if (payloadLeft == 0) streamState = StreamState::Header;
  }
}

// ------------------------------------------------------------------ web

// Power-cycling the TV opens a 10 minute window for firmware upload and WiFi changes: physical access
// to the TV is the authorisation.
bool maintenanceWindowOpen() { return millis() < MAINTENANCE_WINDOW_MS; }
bool wifiChangeAllowed() { return setupMode || maintenanceWindowOpen(); }

String htmlEscape(const String& in) {
  String out;
  out.reserve(in.length() + 8);
  for (const char c : in) {
    switch (c) {
      case '&': out += F("&amp;"); break;
      case '<': out += F("&lt;"); break;
      case '>': out += F("&gt;"); break;
      case '"': out += F("&quot;"); break;
      case '\'': out += F("&#39;"); break;
      default: out += c;
    }
  }
  return out;
}

void handleStatus() {
  String s;
  s.reserve(640);
  s += F("SmallTV Live " FW_VERSION "\n");
  s += F("mode: "); s += setupMode ? F("setup access point") : F("station"); s += '\n';
  s += F("ip: "); s += setupMode ? WiFi.softAPIP().toString() : WiFi.localIP().toString(); s += '\n';
  if (!setupMode) {
    s += F("ssid: "); s += WiFi.SSID(); s += '\n';
    s += F("rssi: "); s += WiFi.RSSI(); s += F(" dBm\n");
  }
  s += F("host: "); s += (host && host.connected()) ? host.remoteIP().toString() : String(F("none")); s += '\n';
  s += F("frames: "); s += framesShown; s += '\n';
  s += F("bytes received: "); s += bytesIn; s += '\n';
  s += F("backlight: "); s += backlight; s += '\n';
  s += F("free heap: "); s += ESP.getFreeHeap(); s += '\n';
  s += F("uptime: "); s += millis() / 1000; s += F(" s\n");
  s += F("firmware upload and WiFi change: ");
  s += wifiChangeAllowed() ? F("open") : F("closed (power-cycle the TV, then use them within 10 minutes)");
  s += F("\n\n/update  firmware upload\n/wifi    WiFi network\n");
  web.send(200, F("text/plain; charset=utf-8"), s);
}

// Network page. Nearby network names come from the air, so they are escaped before going into HTML.
void sendWifiForm() {
  const int found = WiFi.scanNetworks();
  String page;
  page.reserve(1600);
  page += F("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            "<title>SmallTV Live WiFi</title>"
            "<form method=post action=/wifi style='font:16px system-ui,sans-serif;max-width:320px;margin:40px auto'>"
            "<h3>WiFi network (2.4 GHz)</h3>");
  if (!setupMode) {
    page += F("<p>Connected to <b>");
    page += htmlEscape(WiFi.SSID());
    page += F("</b>.</p>");
  }
  page += F("<p>Network<br><input name=s list=nets maxlength=32 required autocomplete=off style='width:100%'>"
            "<datalist id=nets>");
  for (int i = 0; i < found && i < 20; i++) {
    const String name = WiFi.SSID(i);
    if (name.length() == 0) continue;
    page += F("<option value=\"");
    page += htmlEscape(name);
    page += F("\">");
  }
  WiFi.scanDelete();
  page += F("</datalist></p><p>Password<br><input name=p type=password maxlength=64 style='width:100%'></p>"
            "<p><button>Save and restart</button></p>"
            "<p style='font-size:13px;color:#666'>If the TV can't join the network, it opens the SmallTV-Live "
            "network again after 30 seconds.</p></form>");
  web.send(200, F("text/html; charset=utf-8"), page);
}

void handleWifi() {
  if (!wifiChangeAllowed()) {
    web.send(403, F("text/plain"), F("WiFi settings are closed. Power-cycle the TV and change them within 10 minutes."));
    return;
  }
  if (web.method() != HTTP_POST) {
    sendWifiForm();
    return;
  }
  const String ssid = web.arg("s");
  const String pass = web.arg("p");
  if (ssid.length() == 0 || ssid.length() > 32 || pass.length() > 64 || (pass.length() > 0 && pass.length() < 8)) {
    web.send(400, F("text/plain"), F("Invalid network name or password (WPA passwords are 8 to 64 characters)."));
    return;
  }
  web.send(200, F("text/plain"), F("Saved. The TV restarts and joins the new network."));
  delay(300);
  dropHost();
  WiFi.persistent(true);              // stored in the SDK config, where the stock firmware keeps it
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid.c_str(), pass.c_str());
  delay(500);
  ESP.restart();
}

const char UPDATE_FORM[] PROGMEM =
    "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
    "<title>SmallTV Live update</title>"
    "<form method=post enctype=multipart/form-data style='font:16px system-ui,sans-serif;max-width:360px;margin:40px auto'>"
    "<h3>Firmware update</h3><p>Upload a .bin or .bin.gz built for the SmallTV-Ultra (ESP8266).</p>"
    "<p><input type=file accept='.bin,.bin.gz' name=firmware required></p>"
    "<p><button>Update</button></p></form>";

void handleUpdateForm() {
  if (!maintenanceWindowOpen()) {
    web.send(403, F("text/plain"), F("Firmware upload is closed. Power-cycle the TV and upload within 10 minutes."));
    return;
  }
  web.send_P(200, "text/html; charset=utf-8", UPDATE_FORM);
}

void handleUpdateUpload() {
  HTTPUpload& upload = web.upload();
  if (upload.status == UPLOAD_FILE_START) {
    updateError = "";
    updateRejected = !maintenanceWindowOpen();
    if (updateRejected) return;
    dropHost();
    WiFiUDP::stopAll();
    const uint32_t maxSize = (ESP.getFreeSketchSpace() - 0x1000) & 0xFFFFF000;
    if (!Update.begin(maxSize, U_FLASH)) updateError = Update.getErrorString();
  } else if (updateRejected || updateError.length()) {
    if (upload.status == UPLOAD_FILE_ABORTED) Update.end();
    return;
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) updateError = Update.getErrorString();
  } else if (upload.status == UPLOAD_FILE_END) {
    if (!Update.end(true)) updateError = Update.getErrorString();
  } else if (upload.status == UPLOAD_FILE_ABORTED) {
    Update.end();
    updateError = F("upload aborted");
  }
  yield();
}

void handleUpdateDone() {
  if (updateRejected) {
    web.send(403, F("text/plain"), F("Firmware upload is closed. Power-cycle the TV and upload within 10 minutes."));
    return;
  }
  if (updateError.length()) {
    web.send(500, F("text/plain"), String(F("Update failed: ")) + updateError);
    return;
  }
  web.send(200, F("text/plain"), F("Update complete. Restarting..."));
  delay(500);
  ESP.restart();
}

// ------------------------------------------------------------------ WiFi

void startWifi() {
  WiFi.persistent(false);             // don't rewrite the stored config on every boot
  WiFi.mode(WIFI_STA);
  WiFi.hostname(HOSTNAME);
  WiFi.begin();                       // credentials stored in the SDK config
  savedSsid = WiFi.SSID();
  savedPass = WiFi.psk();
  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_JOIN_MS) delay(250);
  if (WiFi.status() != WL_CONNECTED) {
    // Setup mode. The saved network is still retried now and then (see retrySavedNetwork), so a TV that
    // booted before the router after a power cut goes back to normal on its own.
    setupMode = true;
    wifi_station_disconnect();
    WiFi.setAutoReconnect(false);
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(SETUP_AP);
  }
  WiFi.setSleepMode(WIFI_NONE_SLEEP);   // lower latency while streaming
}

// In setup mode, try the saved network for 15 s every 2 minutes; restart into normal mode once it works.
// Between attempts the station is idle so phones connected to the setup network aren't disturbed.
void retrySavedNetwork() {
  static uint32_t attemptStart = 0;
  static bool attempting = false;
  if (savedSsid.length() == 0) return;
  if (!attempting && millis() - attemptStart > SETUP_RETRY_EVERY_MS) {
    attempting = true;
    attemptStart = millis();
    WiFi.begin(savedSsid.c_str(), savedPass.c_str());
  } else if (attempting && WiFi.status() == WL_CONNECTED) {
    ESP.restart();
  } else if (attempting && millis() - attemptStart > SETUP_RETRY_FOR_MS) {
    attempting = false;
    attemptStart = millis();
    wifi_station_disconnect();
  }
}

}  // namespace

void setup() {
  pinMode(PIN_BL, OUTPUT);
  analogWriteRange(255);
  analogWriteFreq(1000);
  setBacklight(0);                    // dark until the panel holds a defined image
  panelInit();
  setBacklight(DEFAULT_BACKLIGHT);
  panelFill(20, 118, 200, 4, COLOR_GREY);   // joining WiFi

  startWifi();
  if (!setupMode) MDNS.begin(HOSTNAME);

  web.on("/", HTTP_GET, handleStatus);
  web.on("/wifi", handleWifi);
  web.on("/update", HTTP_GET, handleUpdateForm);
  web.on("/update", HTTP_POST, handleUpdateDone, handleUpdateUpload);
  web.onNotFound([]() { web.send(404, F("text/plain"), F("Not found")); });
  web.begin();

  streamServer.begin();
  streamServer.setNoDelay(true);
  if (!setupMode) MDNS.addService("smalltv-live", "tcp", STREAM_PORT);

  drawStatusScreen();
}

void loop() {
  web.handleClient();
  if (!setupMode) MDNS.update();
  pumpStream();

  if (streamedSinceIdle && millis() - lastFrameMs > IDLE_SCREEN_MS) {
    dropHost();
    drawStatusScreen();
    streamedSinceIdle = false;
  }

  if (setupMode) retrySavedNetwork();
  static uint32_t lastRetry = 0;
  if (!setupMode && WiFi.status() != WL_CONNECTED && millis() - lastRetry > WIFI_RETRY_MS) {
    lastRetry = millis();
    WiFi.reconnect();
  }
  yield();
}
