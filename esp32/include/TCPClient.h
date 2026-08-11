#pragma once
// ===========================================================================
//  TCPClient.h
//  TCP socket client with ACK-based reliable delivery and retransmission.
//
//  Protocol
//  --------
//  1. ESP32 opens a TCP connection to SERVER_IP:SERVER_PORT.
//  2. ESP32 sends the binary DataPacket (134 bytes).
//  3. ESP32 waits up to TCP_ACK_TIMEOUT_MS for a single ACK byte (0x06).
//  4. If no ACK is received within the timeout the packet is retransmitted
//     up to TCP_MAX_RETRIES times before being dropped and an error logged.
//  5. If the TCP connection drops it is re-established transparently.
// ===========================================================================

#include <Arduino.h>
#include <WiFiClient.h>
#include "Config.h"
#include "PacketBuilder.h"
#include "WiFiManager.h"
#include "ErrorHandler.h"

class TCPClient {
public:
    /// @param wifiMgr Reference to the shared WiFiManager.
    explicit TCPClient(WiFiManager& wifiMgr);

    /// Establish TCP connection to the server.
    /// @return true on success.
    bool connect();

    /// @return true if the TCP socket is currently open.
    bool isConnected();

    /// Disconnect the TCP socket gracefully.
    void disconnect();

    /// Send a DataPacket, wait for ACK, retransmit if needed.
    /// @param pkt  The packet to send.
    /// @return true if ACK was received; false after max retries.
    bool sendPacket(const DataPacket& pkt);

    /// Ensure connection is alive, reconnect if dropped.
    void maintainConnection();

private:
    WiFiClient  m_client;
    WiFiManager& m_wifiMgr;

    /// Transmit raw bytes over the socket.
    bool transmit(const uint8_t* data, size_t len);

    /// Block until ACK byte is received or timeout expires.
    bool waitForAck();
};
