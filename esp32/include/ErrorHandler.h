#pragma once
// ===========================================================================
//  ErrorHandler.h
//  Centralised error code definitions and fault management.
//
//  All modules report errors through ErrorHandler::report() so that fault
//  handling policy (log, blink LED, reboot) is decoupled from business logic.
// ===========================================================================

#include <Arduino.h>

// ---------------------------------------------------------------------------
// Error Code Enum
// ---------------------------------------------------------------------------
enum class ErrorCode : uint8_t {
    OK                      = 0,

    // Sensor errors
    ADXL345_INIT_FAIL       = 10,
    ADXL345_READ_FAIL       = 11,
    DHT_READ_FAIL           = 12,

    // Buffer errors
    BUFFER_OVERFLOW         = 20,

    // Network errors
    WIFI_CONNECT_FAIL       = 30,
    WIFI_LOST               = 31,
    TCP_CONNECT_FAIL        = 40,
    TCP_SEND_FAIL           = 41,
    TCP_ACK_TIMEOUT         = 42,
    TCP_MAX_RETRIES         = 43,

    // Processing errors
    FEATURE_EXTRACT_FAIL    = 50,
    PACKET_BUILD_FAIL       = 51,

    // System errors
    TASK_STACK_OVERFLOW     = 90,
    UNKNOWN                 = 255
};

// ---------------------------------------------------------------------------
// ErrorHandler Class
// ---------------------------------------------------------------------------
class ErrorHandler {
public:
    /// Report an error with an optional descriptive message.
    /// @param code   Error code from the ErrorCode enum.
    /// @param msg    Human-readable context string (printed to Serial).
    static void report(ErrorCode code, const char* msg = "");

    /// Return the most recent error code (for polling by other modules).
    static ErrorCode lastError();

    /// Reset the stored error code to OK.
    static void clear();

    /// Return a string name for a given error code (for logging).
    static const char* errorName(ErrorCode code);

private:
    static ErrorCode s_lastError;
};
