// ===========================================================================
//  ErrorHandler.cpp
// ===========================================================================

#include "ErrorHandler.h"

// Static member definition
ErrorCode ErrorHandler::s_lastError = ErrorCode::OK;

// ---------------------------------------------------------------------------
void ErrorHandler::report(ErrorCode code, const char* msg) {
    s_lastError = code;

    if (code == ErrorCode::OK) return;

    Serial.printf("[ERROR] Code=%d (%s) | %s\n",
                  static_cast<int>(code),
                  errorName(code),
                  msg);
}

// ---------------------------------------------------------------------------
ErrorCode ErrorHandler::lastError() {
    return s_lastError;
}

// ---------------------------------------------------------------------------
void ErrorHandler::clear() {
    s_lastError = ErrorCode::OK;
}

// ---------------------------------------------------------------------------
const char* ErrorHandler::errorName(ErrorCode code) {
    switch (code) {
        case ErrorCode::OK:                  return "OK";
        case ErrorCode::ADXL345_INIT_FAIL:   return "ADXL345_INIT_FAIL";
        case ErrorCode::ADXL345_READ_FAIL:   return "ADXL345_READ_FAIL";
        case ErrorCode::DHT_READ_FAIL:       return "DHT_READ_FAIL";
        case ErrorCode::BUFFER_OVERFLOW:     return "BUFFER_OVERFLOW";
        case ErrorCode::WIFI_CONNECT_FAIL:   return "WIFI_CONNECT_FAIL";
        case ErrorCode::WIFI_LOST:           return "WIFI_LOST";
        case ErrorCode::TCP_CONNECT_FAIL:    return "TCP_CONNECT_FAIL";
        case ErrorCode::TCP_SEND_FAIL:       return "TCP_SEND_FAIL";
        case ErrorCode::TCP_ACK_TIMEOUT:     return "TCP_ACK_TIMEOUT";
        case ErrorCode::TCP_MAX_RETRIES:     return "TCP_MAX_RETRIES";
        case ErrorCode::FEATURE_EXTRACT_FAIL:return "FEATURE_EXTRACT_FAIL";
        case ErrorCode::PACKET_BUILD_FAIL:   return "PACKET_BUILD_FAIL";
        case ErrorCode::TASK_STACK_OVERFLOW: return "TASK_STACK_OVERFLOW";
        default:                             return "UNKNOWN";
    }
}
