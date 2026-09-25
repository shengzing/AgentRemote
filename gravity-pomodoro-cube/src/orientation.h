#pragma once

#include <Arduino.h>
#include <M5Unified.h>
#include "config.h"

// ─── Orientation enum ────────────────────────────────────────────────────────

enum class Orientation : uint8_t {
    UNKNOWN = 0,   // sideways / in-hand / transitioning
    UPRIGHT,       // standing on end (USB down or up)  → focus mode
    FLAT_UP,       // lying flat, screen facing up      → break mode
    FACE_DOWN,     // lying flat, screen facing down    → pause / stop
};

inline const char* orientationName(Orientation o) {
    switch (o) {
        case Orientation::UPRIGHT:  return "UPRIGHT";
        case Orientation::FLAT_UP:  return "FLAT_UP";
        case Orientation::FACE_DOWN: return "FACE_DOWN";
        default: return "UNKNOWN";
    }
}

// ─── Orientation detector with debounce ─────────────────────────────────────

class OrientationDetector {
public:
    void begin() {
        _raw = Orientation::UNKNOWN;
        _confirmed = Orientation::UNKNOWN;
        _candidate = Orientation::UNKNOWN;
        _candidateSince = 0;
        _lastReadMs = 0;
    }

    // Call every loop; reads IMU and updates internal state.
    void update() {
        uint32_t now = millis();
        if (now - _lastReadMs < 50) return;   // sample at 20 Hz
        _lastReadMs = now;

        M5.Imu.update();   // refresh sensor data before reading

        float ax, ay, az;
        M5.Imu.getAccelData(&ax, &ay, &az);
        _raw = classify(ax, ay, az);

        if (_raw != _candidate) {
            _candidate = _raw;
            _candidateSince = now;
            return;
        }

        // Candidate has been stable long enough → confirm
        if (_candidate != _confirmed &&
            now - _candidateSince >= ORIENTATION_DEBOUNCE_MS) {
            _confirmed = _candidate;
            _onConfirm(_confirmed);
        }
    }

    // Returns the last confirmed (debounced) orientation.
    Orientation confirmed() const { return _confirmed; }

    // Returns the instantaneous (raw) orientation, for UI feedback.
    Orientation raw() const { return _raw; }

    // Register callback for confirmed orientation changes.
    void onConfirm(void (*cb)(Orientation)) { _onConfirm = cb; }

private:
    static Orientation classify(float ax, float ay, float az) {
        float absX = fabsf(ax);
        float absY = fabsf(ay);
        float absZ = fabsf(az);

        // Face-down: Z dominant and negative
        if (az < -ORIENTATION_THRESHOLD && absX < 0.4f && absY < 0.4f)
            return Orientation::FACE_DOWN;

        // Flat screen-up: Z dominant and positive
        if (az > ORIENTATION_THRESHOLD && absX < 0.4f && absY < 0.4f)
            return Orientation::FLAT_UP;

        // Upright: Y dominant (either end down)
        if (absY > ORIENTATION_THRESHOLD && absX < 0.4f && absZ < 0.4f)
            return Orientation::UPRIGHT;

        return Orientation::UNKNOWN;
    }

    Orientation _raw;
    Orientation _confirmed;
    Orientation _candidate;
    uint32_t    _candidateSince;
    uint32_t    _lastReadMs;
    void (*_onConfirm)(Orientation) = nullptr;
};
