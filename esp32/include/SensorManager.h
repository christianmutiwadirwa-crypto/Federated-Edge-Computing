#pragma once
// ===========================================================================
//  SensorManager.h
//  Manages the ADXL345 accelerometer (SPI).
//
//  Responsibilities
//  ----------------
//  • Initialise the ADXL345 sensor at startup.
//  • Provide a sampleAccel() method called by the deterministic sampling timer.
// ===========================================================================

#include <Arduino.h>
#include <SPI.h>
#include "ADXL345.h"
#include "Config.h"
#include "BufferManager.h"
#include "ErrorHandler.h"

class SensorManager {
public:
    /// @param bufMgr Reference to the shared BufferManager.
    explicit SensorManager(BufferManager& bufMgr);

    /// Initialise SPI bus and ADXL345.
    /// @return true on success; false if the sensor fails to init.
    bool init();

    /// Read one accelerometer sample and push it into the BufferManager.
    /// Designed to be called from a 500 Hz timer callback (ISR-safe path).
    void sampleAccel();

    /// ADXL345 full-scale range sensitivity (g/LSB).
    /// In Full Resolution mode (which we use), scale is fixed at ~3.9 mg/LSB
    /// regardless of the ±g range selected.
    static constexpr float ADXL_SCALE_G = 0.00390625f;  // 1/256

private:
    ADXL345        m_adxl;
    BufferManager& m_bufMgr;
};
