// ===========================================================================
//  SensorManager.cpp
//  ADXL345 (SPI) sensor management.
// ===========================================================================

#include "SensorManager.h"

// ---------------------------------------------------------------------------
SensorManager::SensorManager(BufferManager& bufMgr)
    : m_adxl(PIN_ADXL_CS, SPI_FREQ_HZ),
      m_bufMgr(bufMgr)
{}

// ---------------------------------------------------------------------------
bool SensorManager::init() {
    // ----- SPI Bus Init -----
    SPI.begin(PIN_SPI_SCK, PIN_SPI_MISO, PIN_SPI_MOSI, PIN_ADXL_CS);

    // ----- ADXL345 Init via Custom Driver -----
    if (!m_adxl.initialize()) {
        ErrorHandler::report(ErrorCode::ADXL345_INIT_FAIL,
                             "SensorManager: ADXL345 initialization failed");
        return false;
    }

    Serial.println("[SensorManager] ADXL345 initialised OK");

    return true;
}

// ---------------------------------------------------------------------------
void SensorManager::sampleAccel() {
    int16_t x, y, z;
    m_adxl.readRawAcceleration(x, y, z);

    AccelSample s;
    s.x            = x;
    s.y            = y;
    s.z            = z;
    s.timestamp_ms = millis();

    if (!m_bufMgr.pushSample(s)) {
        // Error already reported inside BufferManager
    }
}
