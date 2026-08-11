import struct
from CRCManager import CRCManager

class PacketParser:
    """Parses binary data packets from ESP32."""
    
    # Packet layout:
    # 0   2  Magic (0xABCD)
    # 2   1  Version (1)
    # 3   1  Node ID
    # 4   4  Sequence Number
    # 8   8  Timestamp ms
    # 16  12 Mean X/Y/Z
    # 28  12 RMS X/Y/Z
    # 40  12 StdDev X/Y/Z
    # 52  12 Max X/Y/Z
    # 64  12 Min X/Y/Z
    # 76  12 P2P X/Y/Z
    # 88  12 Skewness X/Y/Z
    # 100 12 Kurtosis X/Y/Z
    # 112 12 CrestFactor X/Y/Z
    # 124  2 CRC16
    # Total: 126 bytes
    PACKET_FMT = "<HBBIQfffffffffffffffffffffffffff H"
    PACKET_SIZE = 126
    PACKET_MAGIC = 0xABCD

    def __init__(self):
        self._struct = struct.Struct(self.PACKET_FMT)

    def parse(self, data: bytes) -> dict:
        """
        Parses and validates a packet.
        Returns a dict with parsed fields and 'valid' flag, or None if completely malformed.
        """
        if len(data) != self.PACKET_SIZE:
            return {"valid": False, "error": "Invalid length"}
        
        try:
            fields = self._struct.unpack(data)
        except struct.error:
            return {"valid": False, "error": "Unpack failed"}

        (
            magic, version, node_id, seq, ts_ms,
            mean_x, mean_y, mean_z,
            rms_x,  rms_y,  rms_z,
            std_x,  std_y,  std_z,
            max_x,  max_y,  max_z,
            min_x,  min_y,  min_z,
            p2p_x,  p2p_y,  p2p_z,
            skew_x, skew_y, skew_z,
            kurt_x, kurt_y, kurt_z,
            crf_x,  crf_y,  crf_z,
            received_crc
        ) = fields

        if magic != self.PACKET_MAGIC:
            return {"valid": False, "error": "Bad magic"}

        computed_crc = CRCManager.compute(data[:-2])
        crc_pass = (computed_crc == received_crc)

        return {
            "valid": crc_pass,  # Packet is only valid if CRC passes
            "crc_pass": crc_pass,
            "error": "CRC mismatch" if not crc_pass else None,
            "node_id": node_id,
            "seq": seq,
            "timestamp_ms": ts_ms,
            "features": {
                "mean_x": mean_x, "mean_y": mean_y, "mean_z": mean_z,
                "rms_x": rms_x, "rms_y": rms_y, "rms_z": rms_z,
                "std_x": std_x, "std_y": std_y, "std_z": std_z,
                "max_x": max_x, "max_y": max_y, "max_z": max_z,
                "min_x": min_x, "min_y": min_y, "min_z": min_z,
                "p2p_x": p2p_x, "p2p_y": p2p_y, "p2p_z": p2p_z,
                "skew_x": skew_x, "skew_y": skew_y, "skew_z": skew_z,
                "kurt_x": kurt_x, "kurt_y": kurt_y, "kurt_z": kurt_z,
                "crf_x": crf_x, "crf_y": crf_y, "crf_z": crf_z,
            },
            "raw_length": len(data),
            "payload_length": len(data) - 4,  # excluding magic and crc
            "version": version
        }
