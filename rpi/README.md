# Raspberry Pi Edge Node - Predictive Maintenance

This module serves as the central data collection and feature extraction hub for the predictive maintenance system. It runs 24/7, continuously receiving physical vibration/environmental data from ESP32 edge nodes and simultaneously generating cyber features (network performance, timing, reliability metrics) to fuel future machine learning models.

## Responsibilities

1.  **Reliable TCP Reception**: A non-blocking multithreaded TCP server receives binary packets.
2.  **Packet Validation**: Validates the payload format, sequence numbers, and CRC16 checksums.
3.  **Physical Dataset Generation**: Unpacks hardware features (mean, RMS, skewness, kurtosis, etc.) to a physical CSV dataset.
4.  **Cyber Feature Extraction**: Monitors connection states and timing to generate a 23-feature cyber dataset for network health and anomaly detection.
5.  **Event Logging**: Maintains an `events.log` of connections, disconnections, packet loss, and corruption.

## Directory Structure

The system automatically generates the `EdgeNode` working directory:

```text
rpi/
├── src/                    ← Python source files
│   ├── main.py             ← Entry point
│   ├── ConfigManager.py
│   ├── Logger.py
│   ├── TCPServer.py
│   ├── PacketReceiver.py
│   ├── PacketParser.py
│   ├── DataManager.py
│   ├── ConnectionStateManager.py
│   ├── SlidingWindow.py
│   ├── CyberFeatureExtractor.py
│   ├── PhysicalCSVWriter.py
│   └── CyberCSVWriter.py
└── EdgeNode/               ← Auto-generated operational directory
    ├── config/
    │   └── config.json     ← Configuration parameters (port, queue sizes, etc.)
    ├── physical/
    │   └── physical_data.csv
    ├── cyber/
    │   └── cyber_data.csv
    └── logs/
        └── events.log
```

## Running the Server

1.  Navigate to the `rpi/src` directory.
2.  Run the application using Python 3:

```bash
cd rpi/src
python3 main.py
```

The application is highly multithreaded (Server thread, Validation thread, Cyber extraction, Physical writer, Cyber writer, Logger). All inter-thread communication uses fast, thread-safe Queues to ensure packet reception is never blocked.

## Cyber Features Extracted

-   **Identity**: Node ID, Source/Dest IPs, Source/Dest Ports
-   **Packet Info**: Raw Length, Payload Length, CRC Status, Sequence Number, Validity
-   **Timing**: Arrival Timestamp, Inter-arrival Time, Packet Rate, Data Rate, Connection Duration
-   **Reliability**: Loss Rate, Duplicate Count, Out-of-order Count, Sequence Gap
-   **Statistical Behavior**: Sliding-window Mean and StdDev for Packet Size and Arrival Intervals.

By default, an `AttackLabel` column defaults to `Unknown`. This facilitates future dataset generation scripts that can alter this label during controlled network anomaly experiments.
