#pragma once
// ===========================================================================
//  ADXL345.h
//  Custom register-level SPI driver for the ADXL345 accelerometer.
//
//  Operates via SPI Mode 3.
// ===========================================================================

#include <Arduino.h>
#include <SPI.h>

class ADXL345 {
public:
    /// @param csPin   The Chip Select (CS) GPIO pin for this sensor.
    /// @param spiFreq The SPI clock frequency in Hz (e.g. 1000000).
    ADXL345(uint8_t csPin, uint32_t spiFreq);

    /// Initializes the ADXL345.
    /// Checks the Device ID, sets the data format (Full Res, ±16g),
    /// sets the output data rate (400 Hz), and enables measurement mode.
    /// @return true if initialization succeeded and device ID matched 0xE5.
    bool initialize();

    /// Reads the raw X, Y, and Z acceleration values.
    /// @param[out] x Raw X-axis value (signed 16-bit).
    /// @param[out] y Raw Y-axis value (signed 16-bit).
    /// @param[out] z Raw Z-axis value (signed 16-bit).
    void readRawAcceleration(int16_t& x, int16_t& y, int16_t& z);

private:
    uint8_t  m_csPin;
    uint32_t m_spiFreq;

    // Register Definitions
    static constexpr uint8_t REG_DEVID       = 0x00;
    static constexpr uint8_t REG_BW_RATE     = 0x2C;
    static constexpr uint8_t REG_POWER_CTL   = 0x2D;
    static constexpr uint8_t REG_DATA_FORMAT = 0x31;
    static constexpr uint8_t REG_DATAX0      = 0x32;

    // SPI read/write masks
    static constexpr uint8_t SPI_READ_MASK  = 0x80;
    static constexpr uint8_t SPI_MULTI_MASK = 0x40;

    /// Writes a single byte to a register.
    void writeRegister(uint8_t reg, uint8_t value);

    /// Reads a single byte from a register.
    uint8_t readRegister(uint8_t reg);
};
