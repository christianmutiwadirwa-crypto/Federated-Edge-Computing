// ===========================================================================
//  TCPClient.cpp
//  Reliable TCP transmission with ACK-based delivery and retransmission.
// ===========================================================================

#include "TCPClient.h"

// ---------------------------------------------------------------------------
TCPClient::TCPClient(WiFiManager& wifiMgr)
    : m_wifiMgr(wifiMgr)
{}

// ---------------------------------------------------------------------------
bool TCPClient::connect() {
    if (!m_wifiMgr.isConnected()) {
        ErrorHandler::report(ErrorCode::TCP_CONNECT_FAIL,
                             "TCPClient: WiFi not connected – cannot open TCP socket");
        return false;
    }

    Serial.printf("[TCPClient] Connecting to %s:%d\n", SERVER_IP, SERVER_PORT);

    // WiFiClient::connect() returns 1 on success
    if (!m_client.connect(SERVER_IP, SERVER_PORT, TCP_CONNECT_TIMEOUT_MS)) {
        ErrorHandler::report(ErrorCode::TCP_CONNECT_FAIL,
                             "TCPClient: failed to connect to server");
        return false;
    }

    // Set receive timeout to avoid hanging on waitForAck()
    m_client.setTimeout(TCP_ACK_TIMEOUT_MS / 1000);  // setTimeout takes seconds

    Serial.println("[TCPClient] Connected to server");
    return true;
}

// ---------------------------------------------------------------------------
bool TCPClient::isConnected() {
    return m_client.connected();
}

// ---------------------------------------------------------------------------
void TCPClient::disconnect() {
    m_client.stop();
    Serial.println("[TCPClient] Disconnected");
}

// ---------------------------------------------------------------------------
bool TCPClient::sendPacket(const DataPacket& pkt) {
    const uint8_t* data = PacketBuilder::rawBytes(pkt);
    const size_t   len  = PacketBuilder::packetSize();

    for (uint8_t attempt = 0; attempt < TCP_MAX_RETRIES; ++attempt) {
        // Ensure connection is alive before each attempt
        maintainConnection();
        if (!isConnected()) {
            vTaskDelay(pdMS_TO_TICKS(TCP_RETRY_DELAY_MS));
            continue;
        }

        if (!transmit(data, len)) {
            vTaskDelay(pdMS_TO_TICKS(TCP_RETRY_DELAY_MS));
            continue;
        }

        if (waitForAck()) {
            Serial.printf("[TCPClient] Packet seq=%lu sent & ACK'd\n",
                          static_cast<unsigned long>(pkt.sequenceNumber));
            return true;
        }

        Serial.printf("[TCPClient] No ACK for seq=%lu (attempt %d/%d)\n",
                      static_cast<unsigned long>(pkt.sequenceNumber),
                      attempt + 1,
                      TCP_MAX_RETRIES);

        vTaskDelay(pdMS_TO_TICKS(TCP_RETRY_DELAY_MS));
    }

    ErrorHandler::report(ErrorCode::TCP_MAX_RETRIES,
                         "TCPClient: max retransmissions reached – packet dropped");
    return false;
}

// ---------------------------------------------------------------------------
void TCPClient::maintainConnection() {
    m_wifiMgr.maintainConnection();

    if (!isConnected() && m_wifiMgr.isConnected()) {
        Serial.println("[TCPClient] TCP socket lost – reconnecting...");
        m_client.stop();
        connect();
    }
}

// ---------------------------------------------------------------------------
bool TCPClient::transmit(const uint8_t* data, size_t len) {
    size_t written = m_client.write(data, len);
    if (written != len) {
        ErrorHandler::report(ErrorCode::TCP_SEND_FAIL,
                             "TCPClient: short write on socket");
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
bool TCPClient::waitForAck() {
    const uint32_t deadline = millis() + TCP_ACK_TIMEOUT_MS;

    while (millis() < deadline) {
        if (m_client.available() > 0) {
            uint8_t b = static_cast<uint8_t>(m_client.read());
            if (b == ACK_BYTE) return true;

            // Unexpected byte – log and continue waiting
            Serial.printf("[TCPClient] Unexpected byte 0x%02X while waiting for ACK\n", b);
        }
        vTaskDelay(pdMS_TO_TICKS(10));  // Yield, check again
    }

    ErrorHandler::report(ErrorCode::TCP_ACK_TIMEOUT,
                         "TCPClient: ACK timeout");
    return false;
}
