// ===========================================================================
//  CRCManager.cpp
//  CRC-16/CCITT implementation (bit-by-bit, no lookup table).
//
//  For better performance on high-throughput applications a 256-entry lookup
//  table can replace the inner loop – but for 134-byte packets the difference
//  is negligible and the table-less approach saves 512 bytes of RAM.
// ===========================================================================

#include "CRCManager.h"

// ---------------------------------------------------------------------------
uint16_t CRCManager::update(uint16_t crc, uint8_t byte) {
    crc ^= static_cast<uint16_t>(byte) << 8;
    for (uint8_t i = 0; i < 8; ++i) {
        if (crc & 0x8000u) {
            crc = (crc << 1) ^ POLY;
        } else {
            crc <<= 1;
        }
    }
    return crc;
}

// ---------------------------------------------------------------------------
uint16_t CRCManager::compute(const uint8_t* data, size_t length) {
    uint16_t crc = 0xFFFF;  // CCITT initial value
    for (size_t i = 0; i < length; ++i) {
        crc = update(crc, data[i]);
    }
    return crc;
}
