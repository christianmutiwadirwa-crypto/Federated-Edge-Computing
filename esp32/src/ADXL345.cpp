#include "ADXL345.h"

// ---------------------------------------------------------------------------
ADXL345::ADXL345(uint8_t csPin, uint32_t spiFreq)
    : m_csPin(csPin), m_spiFreq(spiFreq)
{
}

// ---------------------------------------------------------------------------
bool ADXL345::initialize() {
    pinMode(m_csPin, OUTPUT);
    digitalWrite(m_csPin, HIGH);

    // Read Device ID (should be 0xE5)
    uint8_t devId = readRegister(REG_DEVID);
    if (devId != 0xE5) {
        Serial.printf("[ADXL345] Init failed! Expected Device ID 0xE5, got 0x%02X\n", devId);
        return false;
    }
    Serial.println("[ADXL345] Device ID 0xE5 found.");

    // Configure DATA_FORMAT
    // Bit 3 (FULL_RES) = 1 (Full resolution)
    // Bits [1:0] (Range) = 0x03 (±16g)
    // Value = 0x0B (0000 1011)
    writeRegister(REG_DATA_FORMAT, 0x0B);

    // Configure BW_RATE (Output Data Rate)
    // 400 Hz = 0x0C (0000 1100)
    writeRegister(REG_BW_RATE, 0x0C);

    // Configure POWER_CTL
    // Bit 3 (Measure) = 1 (Measurement mode)
    // Value = 0x08
    writeRegister(REG_POWER_CTL, 0x08);

    return true;
}

// ---------------------------------------------------------------------------
void ADXL345::readRawAcceleration(int16_t& x, int16_t& y, int16_t& z) {
    uint8_t buf[6];

    SPI.beginTransaction(SPISettings(m_spiFreq, MSBFIRST, SPI_MODE3));
    digitalWrite(m_csPin, LOW);

    // Send: read | multi-byte | register address
    SPI.transfer(SPI_READ_MASK | SPI_MULTI_MASK | REG_DATAX0);

    // Burst read 6 data bytes (X0, X1, Y0, Y1, Z0, Z1)
    for (auto& b : buf) {
        b = SPI.transfer(0x00);
    }

    digitalWrite(m_csPin, HIGH);
    SPI.endTransaction();

    // Reconstruct signed 16-bit values (little-endian)
    x = static_cast<int16_t>((buf[1] << 8) | buf[0]);
    y = static_cast<int16_t>((buf[3] << 8) | buf[2]);
    z = static_cast<int16_t>((buf[5] << 8) | buf[4]);
}

// ---------------------------------------------------------------------------
void ADXL345::writeRegister(uint8_t reg, uint8_t value) {
    SPI.beginTransaction(SPISettings(m_spiFreq, MSBFIRST, SPI_MODE3));
    digitalWrite(m_csPin, LOW);

    // Bit 7 = 0 for Write
    SPI.transfer(reg & ~SPI_READ_MASK);
    SPI.transfer(value);

    digitalWrite(m_csPin, HIGH);
    SPI.endTransaction();
}

// ---------------------------------------------------------------------------
uint8_t ADXL345::readRegister(uint8_t reg) {
    SPI.beginTransaction(SPISettings(m_spiFreq, MSBFIRST, SPI_MODE3));
    digitalWrite(m_csPin, LOW);

    // Bit 7 = 1 for Read
    SPI.transfer(reg | SPI_READ_MASK);
    uint8_t value = SPI.transfer(0x00);

    digitalWrite(m_csPin, HIGH);
    SPI.endTransaction();
    return value;
}
