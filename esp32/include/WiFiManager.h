#pragma once
// ===========================================================================
//  WiFiManager.h
//  Manages WiFi association with automatic reconnection.
//
//  Design notes
//  ------------
//  • Uses the ESP32 Arduino WiFi library (non-blocking where possible).
//  • Reconnection is handled by a dedicated background check; the main
//    communication task blocks on isConnected() before each transmission.
//  • No delay() calls – uses millis()-based timeout loops.
// ===========================================================================

#include <Arduino.h>
#include <WiFi.h>
#include "Config.h"
#include "ErrorHandler.h"

class WiFiManager {
public:
    WiFiManager();

    /// Attempt initial WiFi connection.
    /// Blocks until connected or timeout.
    /// @return true if connected within WIFI_CONNECT_TIMEOUT_MS.
    bool connect();

    /// @return true if currently associated with the AP.
    bool isConnected() const;

    /// Check connection status and reconnect if needed.
    /// Call periodically from the comms task loop.
    void maintainConnection();

    /// Print current IP, SSID, RSSI to Serial.
    void printStatus() const;

private:
    uint32_t m_lastAttemptMs;   ///< millis() of last reconnection attempt

    /// Internal blocking connect with timeout.
    bool attemptConnect();
};
