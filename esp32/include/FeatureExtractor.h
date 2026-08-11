#pragma once
// ===========================================================================
//  FeatureExtractor.h
//  Computes time-domain statistical features from a completed sample window.
//
//  Features per axis (X, Y, Z):
//    • Mean
//    • RMS (Root Mean Square)
//    • Standard Deviation
//    • Maximum
//    • Minimum
//    • Peak-to-Peak (max − min)
//    • Skewness  (3rd standardised moment)
//    • Kurtosis  (4th standardised moment, excess kurtosis)
//    • Crest Factor (peak / RMS)
//
//  All raw int16_t counts are converted to g before computation using
//  SensorManager::ADXL_SCALE_G.
// ===========================================================================

#include <cstdint>
#include "BufferManager.h"
#include "SensorManager.h"

// ---------------------------------------------------------------------------
// Feature vector for one axis.
// ---------------------------------------------------------------------------
struct AxisFeatures {
    float mean;
    float rms;
    float stdDev;
    float maxVal;
    float minVal;
    float peakToPeak;
    float skewness;
    float kurtosis;
    float crestFactor;
};

// ---------------------------------------------------------------------------
// Full feature set for one acquisition window.
// ---------------------------------------------------------------------------
struct FeatureSet {
    AxisFeatures x;
    AxisFeatures y;
    AxisFeatures z;
    uint32_t     windowStart_ms;
};

// ---------------------------------------------------------------------------
// FeatureExtractor
// ---------------------------------------------------------------------------
class FeatureExtractor {
public:
    /// Compute all features from a completed sample window.
    /// @param window     The filled SampleWindow from BufferManager.
    /// @param[out] out   Populated FeatureSet.
    /// @return true on success.
    bool extract(const SampleWindow& window, FeatureSet& out);

private:
    /// Compute all features for a single axis.
    AxisFeatures computeAxis(const float* data, uint32_t n);
};
