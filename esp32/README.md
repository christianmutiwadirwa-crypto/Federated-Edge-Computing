
# ESP32 Predictive Maintenance Edge Node

Production-quality firmware for an industrial edge node that acquires vibration
and environmental data, extracts statistical features, and transmits compact
binary packets to a Raspberry Pi server over TCP/WiFi.

---

## Project Directory Structure

```
esp32/
├── README.md                  ← This file
├── platformio.ini             ← PlatformIO project configuration
├── include/
│   ├── Config.h               ← Global constants, pin definitions, tunables
│   ├── SensorManager.h        ← ADXL345 (SPI) + DHT11 acquisition
│   ├── FeatureExtractor.h     ← Statistical feature computation
│   ├── PacketBuilder.h        ← Binary packet construction
│   ├── CRCManager.h           ← CRC-16/CCITT checksum
│   ├── WiFiManager.h          ← WiFi connection & auto-reconnect
│   ├── TCPClient.h            ← TCP socket, ACK wait, retransmit
│   ├── BufferManager.h        ← Lock-free double buffer
│   └── ErrorHandler.h         ← Error codes, logging, fault management
└── src/
    ├── main.cpp               ← Entry point, RTOS tasks, timer ISR
    ├── SensorManager.cpp
    ├── FeatureExtractor.cpp
    ├── PacketBuilder.cpp
    ├── CRCManager.cpp
    ├── WiFiManager.cpp
    ├── TCPClient.cpp
    ├── BufferManager.cpp
    └── ErrorHandler.cpp
```

---

## Hardware Connections

### ADXL345 Accelerometer (SPI)

| ADXL345 Pin | ESP32 Pin | Notes                    |
|-------------|-----------|--------------------------|
| VCC         | 3.3 V     |                          |
| GND         | GND       |                          |
| CS          | GPIO 5    | SPI Chip Select          |
| SDO / MISO  | GPIO 19   | SPI MISO (VSPI)          |
| SDA / MOSI  | GPIO 23   | SPI MOSI (VSPI)          |
| SCL / SCLK  | GPIO 18   | SPI Clock (VSPI)         |
| INT1        | NC        | (optional interrupt pin) |

> Set CS pin LOW and SDO pin LOW on the ADXL345 to select SPI 4-wire mode
> and I²C address 0x53 (irrelevant for SPI but good practice).

### DHT11 Temperature / Humidity Sensor

| DHT11 Pin | ESP32 Pin | Notes                       |
|-----------|-----------|-----------------------------|
| VCC       | 3.3 V     |                             |
| GND       | GND       |                             |
| DATA      | GPIO 4    | 10 kΩ pull-up to 3.3 V      |

### WiFi

WiFi credentials are configured in `include/Config.h`:

```cpp
constexpr char WIFI_SSID[]     = "default";
constexpr char WIFI_PASSWORD[] = "default";
constexpr char SERVER_IP[]     = "192.168.1.100"; // Raspberry Pi IP
constexpr uint16_t SERVER_PORT = 9000;
```

---

## Dependencies (PlatformIO libraries)

| Library            | Purpose                     |
|--------------------|-----------------------------|
| adafruit/ADXL345   | ADXL345 register helpers    |
| adafruit/DHT sensor library | DHT11 driver       |
| adafruit/Adafruit Unified Sensor | Sensor HAL    |

All are declared in `platformio.ini`.

---

## Packet Format (Binary, Little-Endian)

| Field           | Type      | Bytes | Description                  |
|-----------------|-----------|-------|------------------------------|
| Magic           | uint16_t  | 2     | 0xABCD – frame start marker  |
| Version         | uint8_t   | 1     | Protocol version = 1         |
| Node ID         | uint8_t   | 1     | Unique edge-node identifier  |
| Sequence Number | uint32_t  | 4     | Monotonic packet counter     |
| Timestamp       | uint64_t  | 8     | ms since epoch (millis())    |
| Mean X/Y/Z      | float×3   | 12    |                              |
| RMS X/Y/Z       | float×3   | 12    |                              |
| StdDev X/Y/Z    | float×3   | 12    |                              |
| Max X/Y/Z       | float×3   | 12    |                              |
| Min X/Y/Z       | float×3   | 12    |                              |
| Peak-to-Peak    | float×3   | 12    |                              |
| Skewness X/Y/Z  | float×3   | 12    |                              |
| Kurtosis X/Y/Z  | float×3   | 12    |                              |
| Crest Factor X/Y/Z | float×3| 12   |                              |
| Temperature     | float     | 4     | °C                           |
| Humidity        | float     | 4     | %RH                          |
| CRC16           | uint16_t  | 2     | CRC-16/CCITT over all prior  |
| **Total**       |           | **133**|                             |

---

## Building & Flashing

```bash
# Install PlatformIO CLI
pip install platformio

# Build
pio run

# Upload to ESP32
pio run --target upload

# Monitor serial output
pio device monitor --baud 115200
```
