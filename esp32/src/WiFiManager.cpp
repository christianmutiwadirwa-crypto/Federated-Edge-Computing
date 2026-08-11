// ===========================================================================
//  WiFiManager.cpp
//  WiFi association management with automatic reconnection.
// ===========================================================================

#include "WiFiManager.h"

// ---------------------------------------------------------------------------
WiFiManager::WiFiManager()
    : m_lastAttemptMs(0)
{}

// ---------------------------------------------------------------------------
bool WiFiManager::connect() {
    Serial.printf("[WiFiManager] Connecting to SSID: %s\n", WIFI_SSID);
    return attemptConnect();
}

// ---------------------------------------------------------------------------
bool WiFiManager::isConnected() const {
    return (WiFi.status() == WL_CONNECTED);
}

// ---------------------------------------------------------------------------
void WiFiManager::maintainConnection() {
    if (isConnected()) return;

    uint32_t now = millis();
    if ((now - m_lastAttemptMs) >= WIFI_RECONNECT_DELAY_MS) {
        m_lastAttemptMs = now;
        ErrorHandler::report(ErrorCode::WIFI_LOST,
                             "WiFiManager: connection lost – attempting reconnect");
        attemptConnect();
    }
}

// ---------------------------------------------------------------------------
void WiFiManager::printStatus() const {
    if (isConnected()) {
        Serial.printf("[WiFiManager] Connected | IP: %s | SSID: %s | RSSI: %d dBm\n",
                      WiFi.localIP().toString().c_str(),
                      WiFi.SSID().c_str(),
                      WiFi.RSSI());
    } else {
        Serial.println("[WiFiManager] Not connected");
    }
}

// ---------------------------------------------------------------------------
bool WiFiManager::attemptConnect() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    const uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if ((millis() - start) >= WIFI_CONNECT_TIMEOUT_MS) {
            ErrorHandler::report(ErrorCode::WIFI_CONNECT_FAIL,
                                 "WiFiManager: connection timed out");
            return false;
        }
        vTaskDelay(pdMS_TO_TICKS(250));   // Yield to RTOS – never use delay()
        Serial.print('.');
    }

    Serial.println();
    printStatus();
    return true;
}
