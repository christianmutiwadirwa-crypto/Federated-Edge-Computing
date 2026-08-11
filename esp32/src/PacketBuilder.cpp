// ===========================================================================
//  PacketBuilder.cpp
//  Binary packet construction and CRC appending.
// ===========================================================================

#include "PacketBuilder.h"
#include "CRCManager.h"
#include "Config.h"
#include <cstring>

// ---------------------------------------------------------------------------
PacketBuilder::PacketBuilder()
    : m_sequenceNumber(0)
{}

// ---------------------------------------------------------------------------
void PacketBuilder::build(const FeatureSet& f, DataPacket& pkt) {
    // ---- Header ----
    pkt.magic          = PACKET_MAGIC;
    pkt.version        = PROTOCOL_VERSION;
    pkt.nodeId         = NODE_ID;
    pkt.sequenceNumber = m_sequenceNumber++;
    pkt.timestamp_ms   = static_cast<uint64_t>(f.windowStart_ms);

    // ---- X Axis ----
    pkt.meanX = f.x.mean;       pkt.meanY = f.y.mean;       pkt.meanZ = f.z.mean;
    pkt.rmsX  = f.x.rms;        pkt.rmsY  = f.y.rms;        pkt.rmsZ  = f.z.rms;
    pkt.stdX  = f.x.stdDev;     pkt.stdY  = f.y.stdDev;     pkt.stdZ  = f.z.stdDev;
    pkt.maxX  = f.x.maxVal;     pkt.maxY  = f.y.maxVal;     pkt.maxZ  = f.z.maxVal;
    pkt.minX  = f.x.minVal;     pkt.minY  = f.y.minVal;     pkt.minZ  = f.z.minVal;
    pkt.p2pX  = f.x.peakToPeak; pkt.p2pY  = f.y.peakToPeak; pkt.p2pZ = f.z.peakToPeak;
    pkt.skewX = f.x.skewness;   pkt.skewY = f.y.skewness;   pkt.skewZ = f.z.skewness;
    pkt.kurtX = f.x.kurtosis;   pkt.kurtY = f.y.kurtosis;   pkt.kurtZ = f.z.kurtosis;
    pkt.crfX  = f.x.crestFactor;pkt.crfY  = f.y.crestFactor;pkt.crfZ  = f.z.crestFactor;

    // ---- CRC (covers everything except the crc field itself) ----
    const size_t crcLen = sizeof(DataPacket) - sizeof(uint16_t);
    pkt.crc = CRCManager::compute(reinterpret_cast<const uint8_t*>(&pkt), crcLen);
}

// ---------------------------------------------------------------------------
const uint8_t* PacketBuilder::rawBytes(const DataPacket& pkt) {
    return reinterpret_cast<const uint8_t*>(&pkt);
}
