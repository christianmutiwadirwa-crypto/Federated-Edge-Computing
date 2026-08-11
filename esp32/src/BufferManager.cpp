// ===========================================================================
//  BufferManager.cpp
//  Double (ping-pong) buffer implementation for accelerometer samples.
// ===========================================================================

#include "BufferManager.h"
#include "ErrorHandler.h"

// ---------------------------------------------------------------------------
BufferManager::BufferManager()
    : m_writeIdx(0),
      m_readIdx(1),
      m_readLocked(false),
      m_mutex(nullptr)
{
    // Initialise both windows
    for (auto& buf : m_buffers) {
        buf.count          = 0;
        buf.windowStart_ms = 0;
        buf.ready          = false;
    }
}

// ---------------------------------------------------------------------------
bool BufferManager::init() {
    m_mutex = xSemaphoreCreateMutex();
    if (m_mutex == nullptr) {
        ErrorHandler::report(ErrorCode::BUFFER_OVERFLOW,
                             "BufferManager: failed to create mutex");
        return false;
    }

    // Stamp the start time of the first write window
    m_buffers[m_writeIdx].windowStart_ms = millis();
    return true;
}

// ---------------------------------------------------------------------------
bool BufferManager::pushSample(const AccelSample& sample) {
    // Note: We access m_writeIdx without locking because only the sensor
    // task writes it, and swap() is the only place it changes (also sensor task).
    SampleWindow& wbuf = m_buffers[m_writeIdx];

    if (wbuf.count >= SAMPLES_PER_WINDOW) {
        // This should never happen in normal operation; indicates processing
        // is too slow to consume the previous window in time.
        ErrorHandler::report(ErrorCode::BUFFER_OVERFLOW,
                             "BufferManager: write buffer full – window missed");
        return false;
    }

    wbuf.samples[wbuf.count++] = sample;

    // When the window is full, swap buffers.
    if (wbuf.count >= SAMPLES_PER_WINDOW) {
        swap();
    }

    return true;
}

// ---------------------------------------------------------------------------
bool BufferManager::isReadReady() const {
    return m_buffers[m_readIdx].ready;
}

// ---------------------------------------------------------------------------
const SampleWindow* BufferManager::acquireRead() {
    if (xSemaphoreTake(m_mutex, portMAX_DELAY) == pdTRUE) {
        if (m_buffers[m_readIdx].ready) {
            m_readLocked = true;
            xSemaphoreGive(m_mutex);
            return &m_buffers[m_readIdx];
        }
        xSemaphoreGive(m_mutex);
    }
    return nullptr;
}

// ---------------------------------------------------------------------------
void BufferManager::releaseRead() {
    if (xSemaphoreTake(m_mutex, portMAX_DELAY) == pdTRUE) {
        m_buffers[m_readIdx].count          = 0;
        m_buffers[m_readIdx].ready          = false;
        m_buffers[m_readIdx].windowStart_ms = 0;
        m_readLocked                        = false;
        xSemaphoreGive(m_mutex);
    }
}

// ---------------------------------------------------------------------------
void BufferManager::swap() {
    // Called only from the sensor task – lock for atomic index swap.
    if (xSemaphoreTake(m_mutex, portMAX_DELAY) == pdTRUE) {
        // Mark write buffer as ready for processing
        m_buffers[m_writeIdx].ready = true;

        // Swap indices
        uint8_t tmp  = m_writeIdx;
        m_writeIdx   = m_readIdx;
        m_readIdx    = tmp;

        // Reset new write buffer
        m_buffers[m_writeIdx].count          = 0;
        m_buffers[m_writeIdx].ready          = false;
        m_buffers[m_writeIdx].windowStart_ms = millis();

        xSemaphoreGive(m_mutex);
    }
}
