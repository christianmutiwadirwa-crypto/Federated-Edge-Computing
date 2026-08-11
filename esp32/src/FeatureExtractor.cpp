// ===========================================================================
//  FeatureExtractor.cpp
//  Time-domain statistical feature computation.
//
//  All computations use single-precision float (float), which is hardware-
//  accelerated on the ESP32's Xtensa LX6 FPU.
//
//  Formulas
//  --------
//  Let N = number of samples, x_i = i-th sample in g.
//
//  Mean        = (1/N) Σ x_i
//  RMS         = sqrt( (1/N) Σ x_i² )
//  StdDev      = sqrt( (1/N) Σ (x_i - mean)² )
//  Skewness    = (1/N) Σ ((x_i - mean)/σ)³           (Fisher's moment)
//  Kurtosis    = (1/N) Σ ((x_i - mean)/σ)⁴ − 3       (excess kurtosis)
//  CrestFactor = max(|x_i|) / RMS
// ===========================================================================

#include "FeatureExtractor.h"
#include "ErrorHandler.h"
#include <cmath>

// ---------------------------------------------------------------------------
bool FeatureExtractor::extract(const SampleWindow& window, FeatureSet& out)
{
    const uint32_t N = window.count;
    if (N == 0) {
        ErrorHandler::report(ErrorCode::FEATURE_EXTRACT_FAIL,
                             "FeatureExtractor: empty sample window");
        return false;
    }

    // Convert raw int16 counts to g values for each axis into local arrays.
    // SAMPLES_PER_WINDOW floats × 3 axes on the heap to avoid stack overflow.
    float* axisData[3];
    for (int a = 0; a < 3; ++a) {
        axisData[a] = new float[N];
        if (!axisData[a]) {
            ErrorHandler::report(ErrorCode::FEATURE_EXTRACT_FAIL,
                                 "FeatureExtractor: heap alloc failed");
            // Clean up already allocated
            for (int b = 0; b < a; ++b) delete[] axisData[b];
            return false;
        }
    }

    for (uint32_t i = 0; i < N; ++i) {
        axisData[0][i] = window.samples[i].x * SensorManager::ADXL_SCALE_G;
        axisData[1][i] = window.samples[i].y * SensorManager::ADXL_SCALE_G;
        axisData[2][i] = window.samples[i].z * SensorManager::ADXL_SCALE_G;
    }

    out.x = computeAxis(axisData[0], N);
    out.y = computeAxis(axisData[1], N);
    out.z = computeAxis(axisData[2], N);

    for (int a = 0; a < 3; ++a) delete[] axisData[a];

    out.windowStart_ms  = window.windowStart_ms;

    return true;
}

// ---------------------------------------------------------------------------
AxisFeatures FeatureExtractor::computeAxis(const float* data, uint32_t n) {
    AxisFeatures f{};

    // --- Pass 1: mean, max, min, sum of squares ---
    double sum    = 0.0;
    double sumSq  = 0.0;
    float  maxV   = data[0];
    float  minV   = data[0];

    for (uint32_t i = 0; i < n; ++i) {
        const float v = data[i];
        sum   += v;
        sumSq += static_cast<double>(v) * v;
        if (v > maxV) maxV = v;
        if (v < minV) minV = v;
    }

    const double mean   = sum / n;
    const double rms    = std::sqrt(sumSq / n);
    const double varNum = (sumSq / n) - (mean * mean);   // Var = E[x²] - (E[x])²
    const double sigma  = std::sqrt(varNum > 0.0 ? varNum : 0.0);

    f.mean       = static_cast<float>(mean);
    f.rms        = static_cast<float>(rms);
    f.stdDev     = static_cast<float>(sigma);
    f.maxVal     = maxV;
    f.minVal     = minV;
    f.peakToPeak = maxV - minV;

    // Crest factor: peak absolute value divided by RMS
    const float peakAbs = std::max(std::abs(maxV), std::abs(minV));
    f.crestFactor = (rms > 0.0) ? static_cast<float>(peakAbs / rms) : 0.0f;

    // --- Pass 2: skewness and kurtosis (require mean and sigma) ---
    if (sigma > 0.0) {
        double m3 = 0.0;  // 3rd central moment accumulator
        double m4 = 0.0;  // 4th central moment accumulator

        for (uint32_t i = 0; i < n; ++i) {
            const double z = (data[i] - mean) / sigma;  // standardised value
            const double z2 = z * z;
            m3 += z2 * z;
            m4 += z2 * z2;
        }

        f.skewness = static_cast<float>(m3 / n);
        f.kurtosis = static_cast<float>(m4 / n - 3.0);  // excess kurtosis
    } else {
        f.skewness = 0.0f;
        f.kurtosis = 0.0f;
    }

    return f;
}
