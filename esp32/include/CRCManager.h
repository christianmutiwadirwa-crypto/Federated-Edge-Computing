#pragma once
// ===========================================================================
//  CRCManager.h
//  CRC-16/CCITT (polynomial 0x1021, initial value 0xFFFF) checksum.
//
//  Used to validate packet integrity end-to-end between ESP32 and the
//  Raspberry Pi server.  The same algorithm must be implemented on the server.
// ===========================================================================

#include <cstdint>
#include <cstddef>

class CRCManager {
public:
    /// Compute CRC-16/CCITT over a byte buffer.
    /// @param data   Pointer to the data buffer.
    /// @param length Number of bytes to process.
    /// @return       16-bit CRC value.
    static uint16_t compute(const uint8_t* data, size_t length);

    /// Update a running CRC with a single byte (for streaming use).
    /// @param crc    Current CRC value (start with 0xFFFF).
    /// @param byte   Next byte to fold in.
    /// @return       Updated CRC value.
    static uint16_t update(uint16_t crc, uint8_t byte);

private:
    /// CRC polynomial: 0x1021 (CCITT).
    static constexpr uint16_t POLY = 0x1021;
};
