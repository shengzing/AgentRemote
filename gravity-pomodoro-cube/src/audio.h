#pragma once

#include <Arduino.h>
#include <M5Unified.h>
#include "config.h"

// ─── Non-blocking chime sequencer ────────────────────────────────────────────

struct ToneStep {
    uint16_t freq;
    uint16_t durationMs;
    uint16_t gapMs;      // silence after this tone
};

class ChimePlayer {
public:
    void begin() {
        _playing = false;
        _stepIdx = 0;
        _stepCount = 0;
        _stepStartMs = 0;
    }

    void playFocusDone() {
        static const ToneStep seq[] = {
            { NOTE_C5, 180, 80 },
            { NOTE_E5, 180, 80 },
            { NOTE_G5, 300, 0 },
        };
        start(seq, 3);
    }

    void playBreakDone() {
        static const ToneStep seq[] = {
            { NOTE_A5, 400, 0 },
        };
        start(seq, 1);
    }

    void playBlip() {
        static const ToneStep seq[] = {
            { NOTE_E5, 80, 0 },
        };
        start(seq, 1);
    }

    void update() {
        if (!_playing) return;

        uint32_t now = millis();
        const ToneStep& step = _seq[_stepIdx];

        uint32_t stepTotalMs = (uint32_t)step.durationMs + step.gapMs;
        if (now - _stepStartMs >= stepTotalMs) {
            _stepIdx++;
            if (_stepIdx >= _stepCount) {
                _playing = false;
            } else {
                _stepStartMs = now;
                const ToneStep& next = _seq[_stepIdx];
                M5.Speaker.tone(next.freq, next.durationMs);
            }
        }
    }

    bool isPlaying() const { return _playing; }

private:
    void start(const ToneStep* seq, uint8_t count) {
        if (_playing) return;   // don't interrupt an ongoing chime
        _seq = seq;
        _stepCount = count;
        _stepIdx = 0;
        _stepStartMs = millis();
        _playing = true;
        M5.Speaker.tone(_seq[0].freq, _seq[0].durationMs);
    }

    const ToneStep* _seq = nullptr;
    uint8_t  _stepCount;
    uint8_t  _stepIdx;
    uint32_t _stepStartMs;
    bool     _playing;
};
