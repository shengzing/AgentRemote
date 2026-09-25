#pragma once

// ─── Timer durations ─────────────────────────────────────────────────────────
constexpr uint32_t FOCUS_DURATION_MS = 25UL * 60UL * 1000UL;   // 25 minutes
constexpr uint32_t BREAK_DURATION_MS =  5UL * 60UL * 1000UL;   //  5 minutes

// ─── Orientation detection ───────────────────────────────────────────────────
constexpr float    ORIENTATION_THRESHOLD  = 0.75f;   // g-force for axis dominance
constexpr uint32_t ORIENTATION_DEBOUNCE_MS = 1500;   // must hold position this long

// ─── Display / power management ─────────────────────────────────────────────
constexpr uint32_t SCREEN_DIM_MS       = 15000;      // dim after 15 s inactivity
constexpr uint32_t SCREEN_OFF_MS       = 60000;      // off after 60 s inactivity
constexpr uint8_t  BRIGHTNESS_NORMAL   = 80;
constexpr uint8_t  BRIGHTNESS_DIM      = 15;
constexpr uint8_t  BRIGHTNESS_MIN      = 1;

// ─── UI geometry (StickS3 LCD: 135 × 240 portrait) ──────────────────────────
constexpr int SCREEN_W = 135;
constexpr int SCREEN_H = 240;

// ─── Audio ──────────────────────────────────────────────────────────────────
// Gentle chime frequencies (Hz)
constexpr uint16_t NOTE_C5 = 523;
constexpr uint16_t NOTE_E5 = 659;
constexpr uint16_t NOTE_G5 = 784;
constexpr uint16_t NOTE_A5 = 880;
