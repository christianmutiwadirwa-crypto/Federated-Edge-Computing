class CRCManager:
    """Handles CRC-16/CCITT computation."""
    
    @staticmethod
    def compute(data: bytes) -> int:
        """
        Compute CRC-16/CCITT over a byte buffer.
        Polynomial: 0x1021, Initial value: 0xFFFF
        """
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return crc
