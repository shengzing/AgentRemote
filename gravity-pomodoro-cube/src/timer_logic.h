#pragma once

#include <Arduino.h>
#include "config.h"
#include "orientation.h"

// ─── Timer state machine ─────────────────────────────────────────────────────

enum class Mode : uint8_t {
    IDLE,       // no timer running
    FOCUS,      // pomodoro focus session
    BREAK,      // short break
};

enum class Phase : uint8_t {
    READY,      // waiting for orientation trigger
    RUNNING,    // counting down
    PAUSED,     // halted (face-down)
    COMPLETED,  // finished, showing result
};

struct TimerEvent {
    enum Type : uint8_t { NONE, STARTED, PAUSED, RESUMED, COMPLETED, STOPPED };
    Type type = Type::NONE;
    Mode mode = Mode::IDLE;
};

class PomodoroTimer {
public:
    void begin() {
        _mode = Mode::IDLE;
        _phase = Phase::READY;
        _durationMs = 0;
        _remainingMs = 0;
        _lastTickMs = 0;
    }

    // Main tick; call every loop. Returns events for UI/audio/stats.
    TimerEvent update() {
        TimerEvent evt;
        if (_phase != Phase::RUNNING) return evt;

        uint32_t now = millis();
        uint32_t elapsed = now - _lastTickMs;
        _lastTickMs = now;

        if (elapsed >= _remainingMs) {
            _remainingMs = 0;
            _phase = Phase::COMPLETED;
            evt.type = TimerEvent::Type::COMPLETED;
            evt.mode = _mode;
        } else {
            _remainingMs -= elapsed;
        }
        return evt;
    }

    // Orientation handler: start/resume/pause/stop based on physical position.
    TimerEvent onOrientation(Orientation o) {
        TimerEvent evt;

        switch (o) {
        case Orientation::UPRIGHT:
            if (_mode != Mode::FOCUS || _phase == Phase::COMPLETED) {
                start(Mode::FOCUS);
                evt.type = TimerEvent::Type::STARTED;
                evt.mode = Mode::FOCUS;
            } else if (_phase == Phase::PAUSED) {
                resume();
                evt.type = TimerEvent::Type::RESUMED;
                evt.mode = Mode::FOCUS;
            }
            break;

        case Orientation::FLAT_UP:
            if (_mode != Mode::BREAK || _phase == Phase::COMPLETED) {
                start(Mode::BREAK);
                evt.type = TimerEvent::Type::STARTED;
                evt.mode = Mode::BREAK;
            } else if (_phase == Phase::PAUSED) {
                resume();
                evt.type = TimerEvent::Type::RESUMED;
                evt.mode = Mode::BREAK;
            }
            break;

        case Orientation::FACE_DOWN:
            if (_phase == Phase::RUNNING) {
                pause();
                evt.type = TimerEvent::Type::PAUSED;
                evt.mode = _mode;
            } else if (_phase == Phase::COMPLETED) {
                stop();
                evt.type = TimerEvent::Type::STOPPED;
                evt.mode = Mode::IDLE;
            }
            break;

        case Orientation::UNKNOWN:
            // Picked up / transitioning → keep current state
            break;
        }

        return evt;
    }

    // ─── Accessors ───────────────────────────────────────────────────────────
    Mode   mode()        const { return _mode; }
    Phase  phase()       const { return _phase; }
    bool   isRunning()   const { return _phase == Phase::RUNNING; }
    bool   isCompleted() const { return _phase == Phase::COMPLETED; }

    uint32_t remainingMs() const { return _remainingMs; }
    uint32_t durationMs()  const { return _durationMs; }

    // Remaining seconds, rounded up (for display).
    uint32_t remainingSec() const {
        return (_remainingMs + 999) / 1000;
    }

    // Progress 0.0–1.0 (how much of the timer has elapsed).
    float progress() const {
        if (_durationMs == 0) return 0.0f;
        return 1.0f - (float)_remainingMs / (float)_durationMs;
    }

    // Elapsed minutes for stats recording.
    uint32_t elapsedMin() const {
        return (_durationMs - _remainingMs) / 60000UL;
    }

private:
    void start(Mode m) {
        _mode = m;
        _phase = Phase::RUNNING;
        _durationMs = (m == Mode::FOCUS) ? FOCUS_DURATION_MS : BREAK_DURATION_MS;
        _remainingMs = _durationMs;
        _lastTickMs = millis();
    }

    void pause() {
        _phase = Phase::PAUSED;
    }

    void resume() {
        _phase = Phase::RUNNING;
        _lastTickMs = millis();
    }

    void stop() {
        _mode = Mode::IDLE;
        _phase = Phase::READY;
        _durationMs = 0;
        _remainingMs = 0;
    }

    Mode     _mode;
    Phase    _phase;
    uint32_t _durationMs;
    uint32_t _remainingMs;
    uint32_t _lastTickMs;
};
