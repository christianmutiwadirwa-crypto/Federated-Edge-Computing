// ===========================================================================
//  main.cpp
//  Entry point for the Predictive Maintenance Edge Node firmware.
//
//  Architecture Overview
//  ---------------------
//  Three FreeRTOS tasks run concurrently:
//
//  ┌─────────────────────────────────────────────────────────────────┐
//  │  CORE 1  │  Task: sensorTask  (priority 5)                      │
//  │          │  • Hardware timer fires at 500 Hz → sampleAccel()    │
//  │          │  • Pushes AccelSamples into the write buffer         │
//  │          │  • BufferManager auto-swaps on window completion      │
//  ├──────────┼─────────────────────────────────────────────────────┤
//  │  CORE 1  │  Task: processorTask  (priority 4)                   │
//  │          │  • Polls BufferManager for a ready read window        │
//  │          │  • Calls FeatureExtractor → PacketBuilder             │
//  │          │  • Posts DataPacket to a FreeRTOS queue               │
//  ├──────────┼─────────────────────────────────────────────────────┤
//  │  CORE 0  │  Task: commsTask  (priority 3)                       │
//  │          │  • Manages WiFi & TCP connections                     │
//  │          │  • Blocks on queue → sends packet → waits for ACK    │
//  └──────────┴─────────────────────────────────────────────────────┘
//
//  Timer ISR
//  ---------
//  A hardware timer (hw_timer_t) generates an interrupt every
//  1/SAMPLE_FREQ_HZ seconds and sets a binary semaphore that the
//  sensorTask waits on, achieving deterministic 500 Hz sampling without
//  any use of delay().
//
//  Double Buffer Flow
//  ------------------
//  [ ISR sets sem ] → [ sensorTask wakes → sampleAccel() → pushSample() ]
//  When SAMPLES_PER_WINDOW samples collected → BufferManager.swap()
//  [ processorTask detects readReady() → acquireRead() → extract features ]
//  → [ releaseRead() ] → [ post to commsQueue ]
// ===========================================================================

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>
#include <freertos/queue.h>

#include "Config.h"
#include "ErrorHandler.h"
#include "BufferManager.h"
#include "SensorManager.h"
#include "FeatureExtractor.h"
#include "PacketBuilder.h"
#include "WiFiManager.h"
#include "TCPClient.h"

// ===========================================================================
// Global Objects (all constructed before setup())
// ===========================================================================
static BufferManager   g_bufMgr;
static SensorManager   g_sensorMgr(g_bufMgr);
static FeatureExtractor g_extractor;
static PacketBuilder   g_pktBuilder;
static WiFiManager     g_wifiMgr;
static TCPClient       g_tcpClient(g_wifiMgr);

// ---------------------------------------------------------------------------
// FreeRTOS primitives
// ---------------------------------------------------------------------------
/// Binary semaphore given by the 500 Hz timer ISR; taken by sensorTask.
static SemaphoreHandle_t g_samplerSem = nullptr;

/// Queue of fully-built DataPackets ready for transmission.
/// Depth 4 provides backpressure without losing windows.
static QueueHandle_t g_commsQueue = nullptr;
static constexpr uint8_t COMMS_QUEUE_DEPTH = 4;

// ---------------------------------------------------------------------------
// Hardware Timer
// ---------------------------------------------------------------------------
static hw_timer_t* g_samplingTimer = nullptr;

/// Timer ISR – fires at SAMPLE_FREQ_HZ.
/// Gives the semaphore to wake sensorTask.
void IRAM_ATTR onSamplingTimer() {
    BaseType_t higherPrioTaskWoken = pdFALSE;
    xSemaphoreGiveFromISR(g_samplerSem, &higherPrioTaskWoken);
    if (higherPrioTaskWoken == pdTRUE) {
        portYIELD_FROM_ISR();
    }
}

// ===========================================================================
// Task: sensorTask
// Runs on Core 1 at priority 5.
// Waits for the 500 Hz timer semaphore, then reads one accelerometer sample.
// ===========================================================================
static void sensorTask(void* /*pvParameters*/) {
    Serial.println("[sensorTask] Started on Core 1");

    for (;;) {
        // Block until timer ISR fires (timeout = 2× period for safety)
        if (xSemaphoreTake(g_samplerSem, pdMS_TO_TICKS(10)) == pdTRUE) {
            g_sensorMgr.sampleAccel();
        }
        // If semaphore times out, we missed a sample – continue gracefully
    }
}

// ===========================================================================
// Task: processorTask
// Runs on Core 1 at priority 4.
// Waits for a complete sample window, extracts features, builds a packet,
// and posts it to the communications queue.
// ===========================================================================
static void processorTask(void* /*pvParameters*/) {
    Serial.println("[processorTask] Started on Core 1");

    for (;;) {
        // --- Check for a completed acquisition window ---
        if (!g_bufMgr.isReadReady()) {
            // No window ready yet – yield and check again shortly
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }

        // --- Acquire the completed window ---
        const SampleWindow* window = g_bufMgr.acquireRead();
        if (window == nullptr) {
            vTaskDelay(pdMS_TO_TICKS(1));
            continue;
        }

        // --- Extract statistical features ---
        FeatureSet features;
        if (!g_extractor.extract(*window, features)) {
            g_bufMgr.releaseRead();
            continue;
        }

        // --- Release the read buffer immediately after extraction ---
        g_bufMgr.releaseRead();

        // --- Build the binary packet ---
        DataPacket pkt;
        g_pktBuilder.build(features, pkt);

        // --- Post to comms queue (non-blocking; drop if full) ---
        if (xQueueSend(g_commsQueue, &pkt, 0) != pdTRUE) {
            Serial.println("[processorTask] WARNING: comms queue full – packet dropped");
        } else {
            Serial.printf("[processorTask] Packet seq=%lu queued for TX\n",
                          static_cast<unsigned long>(pkt.sequenceNumber));
        }
    }
}

// ===========================================================================
// Task: commsTask
// Runs on Core 0 at priority 3.
// Manages WiFi and TCP, then blocks on the queue waiting for packets.
// ===========================================================================
static void commsTask(void* /*pvParameters*/) {
    Serial.println("[commsTask] Started on Core 0");

    // --- Initial WiFi connection ---
    while (!g_wifiMgr.connect()) {
        Serial.println("[commsTask] WiFi connect failed – retrying...");
        vTaskDelay(pdMS_TO_TICKS(WIFI_RECONNECT_DELAY_MS));
    }

    // --- Initial TCP connection ---
    while (!g_tcpClient.connect()) {
        Serial.println("[commsTask] TCP connect failed – retrying...");
        vTaskDelay(pdMS_TO_TICKS(TCP_RETRY_DELAY_MS));
    }

    DataPacket pkt;
    for (;;) {
        // Maintain WiFi and TCP health every iteration
        g_tcpClient.maintainConnection();

        // Block waiting for a packet (up to 100 ms)
        if (xQueueReceive(g_commsQueue, &pkt, pdMS_TO_TICKS(100)) == pdTRUE) {
            // Send with retry logic
            if (!g_tcpClient.sendPacket(pkt)) {
                Serial.printf("[commsTask] ERROR: failed to deliver packet seq=%lu\n",
                              static_cast<unsigned long>(pkt.sequenceNumber));
            }
        }
    }
}

// ===========================================================================
// Arduino setup()
// ===========================================================================
void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(500);  // One-time delay at startup is acceptable
    Serial.println("\n=== Predictive Maintenance Edge Node ===");
    Serial.printf("Node ID: %d | Protocol v%d | Fs=%d Hz\n",
                  NODE_ID, PROTOCOL_VERSION, SAMPLE_FREQ_HZ);

    // --- BufferManager init (creates mutex) ---
    if (!g_bufMgr.init()) {
        Serial.println("FATAL: BufferManager init failed");
        esp_restart();
    }

    // --- SensorManager init (SPI + ADXL345) ---
    if (!g_sensorMgr.init()) {
        Serial.println("FATAL: SensorManager init failed");
        esp_restart();
    }

    // --- FreeRTOS Primitives ---
    g_samplerSem = xSemaphoreCreateBinary();
    if (!g_samplerSem) {
        Serial.println("FATAL: could not create sampler semaphore");
        esp_restart();
    }

    g_commsQueue = xQueueCreate(COMMS_QUEUE_DEPTH, sizeof(DataPacket));
    if (!g_commsQueue) {
        Serial.println("FATAL: could not create comms queue");
        esp_restart();
    }

    // --- Hardware Timer (500 Hz = period 2000 µs) ---
    // ESP32 timer: timerBegin(unit, divider, countUp)
    // APB clock = 80 MHz; divider=80 → 1 µs ticks
    g_samplingTimer = timerBegin(0, 80, true);
    timerAttachInterrupt(g_samplingTimer, &onSamplingTimer, true);
    timerAlarmWrite(g_samplingTimer,
                    1000000UL / SAMPLE_FREQ_HZ,  // 2000 µs at 500 Hz
                    true);                           // auto-reload
    timerAlarmEnable(g_samplingTimer);

    // --- Spawn FreeRTOS Tasks ---
    xTaskCreatePinnedToCore(sensorTask,    "SensorTask",
                            STACK_SENSOR,    nullptr,
                            PRIORITY_SENSOR, nullptr, CORE_SENSOR);

    xTaskCreatePinnedToCore(processorTask, "ProcessorTask",
                            STACK_PROCESSOR,    nullptr,
                            PRIORITY_PROCESSOR, nullptr, CORE_PROCESSOR);

    xTaskCreatePinnedToCore(commsTask,     "CommsTask",
                            STACK_COMMS,    nullptr,
                            PRIORITY_COMMS, nullptr, CORE_COMMS);

    Serial.println("[setup] All tasks created – entering scheduler");
}

// ===========================================================================
// Arduino loop()
// ===========================================================================
// The scheduler handles all work. loop() is left empty and can optionally
// print a periodic heartbeat or watchdog check.
void loop() {
    // Heartbeat: print uptime every 30 seconds
    static uint32_t lastHeartbeat = 0;
    if ((millis() - lastHeartbeat) >= 30000UL) {
        lastHeartbeat = millis();
        Serial.printf("[Heartbeat] Uptime: %lu s | Free heap: %u bytes\n",
                      millis() / 1000UL,
                      esp_get_free_heap_size());
    }
    vTaskDelay(pdMS_TO_TICKS(1000));
}
