#pragma once
// ===========================================================================
//  PacketBuilder.h
//  Constructs the binary transmission packet from a computed FeatureSet.
//
//  Packet layout (little-endian, packed struct):
//
//  Offset  Size  Field
//  ------  ----  -----
//    0      2    Magic number    (0xABCD)
//    2      1    Protocol version
//    3      1    Node ID
//    4      4    Sequence number (monotonically increasing)
//    8      8    Timestamp       (millis() of window start, cast to uint64)
//   16     12    Mean  X/Y/Z     (float × 3)
//   28     12    RMS   X/Y/Z
//   40     12    StdDev X/Y/Z
//   52     12    Max   X/Y/Z
//   64     12    Min   X/Y/Z
//   76     12    PeakToPeak X/Y/Z
//   88     12    Skewness X/Y/Z
//  100     12    Kurtosis X/Y/Z
//  112     12    CrestFactor X/Y/Z
//  124      2    CRC-16/CCITT    (over bytes 0–123)
//  ------  ----
//  Total: 126 bytes
// ===========================================================================

#include <cstdint>
#include <cstddef>
#include "FeatureExtractor.h"

// ---------------------------------------------------------------------------
// Packed binary packet structure.
// __attribute__((packed)) ensures no compiler padding bytes are inserted.
// ---------------------------------------------------------------------------
#pragma pack(push, 1)
struct DataPacket {
    uint16_t magic;
    uint8_t  version;
    uint8_t  nodeId;
    uint32_t sequenceNumber;
    uint64_t timestamp_ms;

    // Mean
    float meanX, meanY, meanZ;
    // RMS
    float rmsX,  rmsY,  rmsZ;
    // Standard deviation
    float stdX,  stdY,  stdZ;
    // Maximum
    float maxX,  maxY,  maxZ;
    // Minimum
    float minX,  minY,  minZ;
    // Peak-to-peak
    float p2pX,  p2pY,  p2pZ;
    // Skewness
    float skewX, skewY, skewZ;
    // Kurtosis
    float kurtX, kurtY, kurtZ;
    // Crest factor
    float crfX,  crfY,  crfZ;

    uint16_t crc;
};
#pragma pack(pop)

static_assert(sizeof(DataPacket) == 126,
              "DataPacket size mismatch – check padding / alignment");

// ---------------------------------------------------------------------------
// PacketBuilder
// ---------------------------------------------------------------------------
class PacketBuilder {
public:
    PacketBuilder();

    /// Build a DataPacket from a FeatureSet.
    /// Automatically increments the internal sequence counter and appends CRC.
    /// @param features  Computed feature set for this window.
    /// @param[out] pkt  Filled DataPacket ready for transmission.
    void build(const FeatureSet& features, DataPacket& pkt);

    /// Expose the raw byte pointer and size for transmission.
    static const uint8_t* rawBytes(const DataPacket& pkt);
    static constexpr size_t packetSize() { return sizeof(DataPacket); }

private:
    uint32_t m_sequenceNumber;
};
