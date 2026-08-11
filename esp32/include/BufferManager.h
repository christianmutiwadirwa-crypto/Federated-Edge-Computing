#pragma once
// ===========================================================================
//  BufferManager.h
//  Lock-free double (ping-pong) buffer for accelerometer samples.
//
//  Concept
//  -------
//  Two equal-sized sample arrays (A and B) alternate roles:
//    • "write buffer"  – filled by the ISR / sensor task.
//    • "read buffer"   – consumed by the feature-extraction task.
//
//  When the write buffer is full the manager atomically swaps roles so the
//  processing task can work on the completed window while the next window
//  is already being collected.  No sample is ever lost as long as processing
//  completes within one window duration.
//
//  Thread safety
//  -------------
//  The swap is protected by a FreeRTOS mutex.  The ISR calls
//  trySwap() which must complete without blocking; it uses
//  xSemaphoreTakeFromISR() to stay ISR-safe.
// ===========================================================================

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include "Config.h"

// ---------------------------------------------------------------------------
// Raw 3-axis sample (fixed-point from ADXL345 registers).
// ---------------------------------------------------------------------------
struct AccelSample {
    int16_t x;
    int16_t y;
    int16_t z;
    uint32_t timestamp_ms;  ///< millis() at acquisition time
};

// ---------------------------------------------------------------------------
// A single acquisition window.
// ---------------------------------------------------------------------------
struct SampleWindow {
    AccelSample samples[SAMPLES_PER_WINDOW];
    uint32_t    count;          ///< How many samples are currently stored
    uint32_t    windowStart_ms; ///< millis() when window collection began
    bool        ready;          ///< True when window is full and ready to process
};

// ---------------------------------------------------------------------------
// BufferManager
// ---------------------------------------------------------------------------
class BufferManager {
public:
    BufferManager();

    /// Must be called before use (creates the mutex).
    bool init();

    /// Add one accelerometer sample to the active write buffer.
    /// Called from sensor task or timer ISR.
    /// @return true if sample was stored; false if window is full (should not happen).
    bool pushSample(const AccelSample& sample);

    /// Called by feature-extraction task to check whether a completed window
    /// is available for reading.
    bool isReadReady() const;

    /// Obtain a pointer to the completed (read) buffer for processing.
    /// Caller must call releaseRead() when done.
    const SampleWindow* acquireRead();

    /// Release the read buffer back to the pool so it can be reused.
    void releaseRead();

private:
    SampleWindow  m_buffers[NUM_BUFFERS];
    uint8_t       m_writeIdx;   ///< Index of the buffer currently being written
    uint8_t       m_readIdx;    ///< Index of the buffer ready for reading
    bool          m_readLocked; ///< True while processing task holds the read buf

    SemaphoreHandle_t m_mutex;

    /// Swap write/read buffers when the write buffer is full.
    void swap();
};
