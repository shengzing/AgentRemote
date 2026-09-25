#pragma once

#include <Arduino.h>
#include <M5Unified.h>
#include "config.h"
#include "timer_logic.h"
#include "orientation.h"
#include "stats.h"

// ─── UI renderer ─────────────────────────────────────────────────────────────
// Direct LCD drawing; no sprite buffering to keep memory footprint minimal.

// Colors (RGB565)
constexpr uint16_t COLOR_BG      = 0x0000;   // black
constexpr uint16_t COLOR_FG      = 0xFFFF;   // white
constexpr uint16_t COLOR_FOCUS   = 0xFDA0;   // amber/orange
constexpr uint16_t COLOR_BREAK   = 0x07E0;   // green
constexpr uint16_t COLOR_DIM     = 0x4208;   // dark gray
constexpr uint16_t COLOR_DONE    = 0x07FF;   // cyan
constexpr uint16_t COLOR_WARN    = 0xF800;   // red
constexpr uint16_t COLOR_PANEL   = 0x18E3;   // dark blue-gray

class UIRenderer {
public:
    void begin() {
        M5.Lcd.setRotation(0);   // portrait, USB at bottom (135×240)
        M5.Lcd.fillScreen(COLOR_BG);
        _forceRedraw = true;
        _lastRenderMs = 0;
        _lastRenderedSec = UINT32_MAX;
        _lastRenderedPhase = Phase::READY;
        _lastRenderedMode = Mode::IDLE;
    }

    // Force a full redraw on next render (e.g., after screen wake).
    void forceRedraw() { _forceRedraw = true; }

    // Main render; call every loop. Only redraws when content changes.
    void render(const PomodoroTimer& timer,
                const OrientationDetector& orient,
                const StatsStore& stats,
                bool screenOff) {
        if (screenOff) return;

        uint32_t now = millis();

        // Full redraw when mode/phase changes or after wake
        if (_forceRedraw ||
            timer.mode() != _lastRenderedMode ||
            timer.phase() != _lastRenderedPhase) {
            _forceRedraw = false;
            _lastRenderedMode = timer.mode();
            _lastRenderedPhase = timer.phase();
            _lastRenderedSec = UINT32_MAX;
            M5.Lcd.fillScreen(COLOR_BG);
            drawStatic(timer, stats);
        }

        // Per-second update for countdown
        uint32_t sec = timer.remainingSec();
        if (sec != _lastRenderedSec && now - _lastRenderMs >= 250) {
            _lastRenderedSec = sec;
            _lastRenderMs = now;
            drawDynamic(timer, orient, stats);
        }
    }

private:
    // Elements that only change on mode/phase switch.
    void drawStatic(const PomodoroTimer& timer, const StatsStore& stats) {
        uint16_t accent = modeColor(timer.mode());

        // Header
        M5.Lcd.setTextColor(accent, COLOR_BG);
        M5.Lcd.setTextSize(2);
        M5.Lcd.setTextDatum(MC_DATUM);

        const char* title = "";
        switch (timer.mode()) {
            case Mode::FOCUS: title = "FOCUS"; break;
            case Mode::BREAK: title = "BREAK"; break;
            default: title = "READY"; break;
        }
        M5.Lcd.drawString(title, SCREEN_W / 2, 30);

        // Divider
        M5.Lcd.drawFastHLine(20, 48, SCREEN_W - 40, accent);

        // Footer hint
        M5.Lcd.setTextColor(COLOR_DIM, COLOR_BG);
        M5.Lcd.setTextSize(1);
        const char* hint = "";
        switch (timer.phase()) {
            case Phase::READY:
                hint = "Stand up = focus | Lie flat = break";
                break;
            case Phase::PAUSED:
                hint = "PAUSED - flip to resume";
                break;
            case Phase::COMPLETED:
                hint = timer.mode() == Mode::FOCUS
                    ? "Done! Flip over for break"
                    : "Ready! Stand up to focus";
                break;
            default:
                hint = "Face down = pause";
                break;
        }
        // Split hint into two lines if too long (135px wide, size 1 ≈ 8px/char)
        drawWrapped(hint, SCREEN_W / 2, SCREEN_H - 20, SCREEN_W - 12);
    }

    // Elements that update every second.
    void drawDynamic(const PomodoroTimer& timer,
                     const OrientationDetector& orient,
                     const StatsStore& stats) {
        uint16_t accent = modeColor(timer.mode());

        if (timer.phase() == Phase::COMPLETED) {
            drawCompleted(timer, stats);
            return;
        }

        // ─── Countdown text ────────────────────────────────────────────────
        uint32_t sec = timer.remainingSec();
        uint32_t mm = sec / 60;
        uint32_t ss = sec % 60;
        char buf[8];
        snprintf(buf, sizeof(buf), "%02u:%02u", (unsigned)mm, (unsigned)ss);

        M5.Lcd.setTextColor(timer.phase() == Phase::PAUSED ? COLOR_DIM : COLOR_FG,
                            COLOR_BG);
        M5.Lcd.setTextDatum(MC_DATUM);
        M5.Lcd.setTextSize(4);   // large countdown
        M5.Lcd.drawString(buf, SCREEN_W / 2, 100);

        // ─── Progress bar ──────────────────────────────────────────────────
        int barY = 140;
        int barW = SCREEN_W - 40;
        int barH = 8;
        int filled = (int)(barW * timer.progress());

        M5.Lcd.drawRoundRect(20, barY, barW, barH, 4, COLOR_DIM);
        if (filled > 0) {
            if (filled < 4) filled = 4;   // minimum visible sliver
            if (filled > barW) filled = barW;
            M5.Lcd.fillRoundRect(20, barY, filled, barH, 4, accent);
        }

        // ─── Stats row ─────────────────────────────────────────────────────
        M5.Lcd.setTextColor(COLOR_DIM, COLOR_BG);
        M5.Lcd.setTextSize(1);
        M5.Lcd.setTextDatum(MC_DATUM);

        char statBuf[32];
        snprintf(statBuf, sizeof(statBuf), "%u pomo | %u min today",
                 (unsigned)stats.get().bootPomodoros,
                 (unsigned)stats.get().bootFocusMin);
        M5.Lcd.drawString(statBuf, SCREEN_W / 2, 170);

        // ─── Orientation indicator (subtle) ─────────────────────────────────
        const char* orientLabel = orientationName(orient.confirmed());
        M5.Lcd.setTextColor(orient.confirmed() == Orientation::UNKNOWN
                            ? COLOR_DIM : COLOR_PANEL, COLOR_BG);
        M5.Lcd.drawString(orientLabel, SCREEN_W / 2, 190);
    }

    void drawCompleted(const PomodoroTimer& timer, const StatsStore& stats) {
        uint16_t accent = (timer.mode() == Mode::FOCUS) ? COLOR_DONE : COLOR_BREAK;

        M5.Lcd.setTextColor(accent, COLOR_BG);
        M5.Lcd.setTextDatum(MC_DATUM);

        M5.Lcd.setTextSize(3);
        M5.Lcd.drawString("DONE!", SCREEN_W / 2, 90);

        M5.Lcd.setTextSize(2);
        char buf[32];
        if (timer.mode() == Mode::FOCUS) {
            snprintf(buf, sizeof(buf), "+1 pomo");
        } else {
            snprintf(buf, sizeof(buf), "+5 min break");
        }
        M5.Lcd.setTextColor(COLOR_FG, COLOR_BG);
        M5.Lcd.drawString(buf, SCREEN_W / 2, 130);

        // Today's tally
        M5.Lcd.setTextColor(COLOR_DIM, COLOR_BG);
        M5.Lcd.setTextSize(1);
        snprintf(buf, sizeof(buf), "Today: %u pomo / %u min",
                 (unsigned)stats.get().bootPomodoros,
                 (unsigned)stats.get().bootFocusMin);
        M5.Lcd.drawString(buf, SCREEN_W / 2, 160);
    }

    static uint16_t modeColor(Mode m) {
        switch (m) {
            case Mode::FOCUS: return COLOR_FOCUS;
            case Mode::BREAK: return COLOR_BREAK;
            default: return COLOR_DIM;
        }
    }

    void drawWrapped(const char* text, int cx, int y, int maxW) {
        // Simple 2-line wrap for short hints
        int len = strlen(text);
        if (len == 0) return;

        int charsPerLine = maxW / 6;   // size 1 font ≈ 6px per char
        if (charsPerLine > 60) charsPerLine = 60;   // match buffer size
        if (len <= charsPerLine) {
            M5.Lcd.drawString(text, cx, y);
            return;
        }

        // Find split point near middle
        int split = len / 2;
        for (int i = split; i < len; i++) {
            if (text[i] == ' ') { split = i; break; }
        }

        char line1[64] = {0}, line2[64] = {0};
        if (split >= (int)sizeof(line1) - 1) split = sizeof(line1) - 2;
        strncpy(line1, text, split);
        line1[split] = '\0';
        strncpy(line2, text + split + 1, sizeof(line2) - 2);
        line2[sizeof(line2) - 1] = '\0';

        M5.Lcd.drawString(line1, cx, y - 6);
        M5.Lcd.drawString(line2, cx, y + 6);
    }

    uint32_t _lastRenderMs;
    uint32_t _lastRenderedSec;
    Phase    _lastRenderedPhase;
    Mode     _lastRenderedMode;
    bool     _forceRedraw;
};
