#pragma once

#include <Arduino.h>
#include <Preferences.h>

// ─── Persistent statistics via NVS ───────────────────────────────────────────

struct SessionStats {
    uint32_t totalFocusMin   = 0;   // all-time focus minutes
    uint32_t totalBreakMin   = 0;   // all-time break minutes
    uint32_t totalPomodoros  = 0;   // all-time completed focus sessions
    uint32_t bootPomodoros   = 0;   // completed since last boot
    uint32_t bootFocusMin    = 0;   // focus minutes since last boot
};

class StatsStore {
public:
    void begin() {
        _prefs.begin("pomodoro", false);
        _stats.totalFocusMin  = _prefs.getULong("tFocus", 0);
        _stats.totalBreakMin  = _prefs.getULong("tBreak", 0);
        _stats.totalPomodoros = _prefs.getULong("tPomo",  0);
    }

    void recordFocusComplete(uint32_t focusMinutes) {
        _stats.totalFocusMin  += focusMinutes;
        _stats.totalPomodoros += 1;
        _stats.bootPomodoros  += 1;
        _stats.bootFocusMin   += focusMinutes;
        _prefs.putULong("tFocus", _stats.totalFocusMin);
        _prefs.putULong("tPomo",  _stats.totalPomodoros);
    }

    void recordBreakComplete(uint32_t breakMinutes) {
        _stats.totalBreakMin += breakMinutes;
        _prefs.putULong("tBreak", _stats.totalBreakMin);
    }

    const SessionStats& get() const { return _stats; }

    void factoryReset() {
        _prefs.clear();
        _stats = SessionStats{};
    }

private:
    Preferences   _prefs;
    SessionStats  _stats;
};
