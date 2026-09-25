#include <M5Unified.h>
#include "config.h"
#include "orientation.h"
#include "timer_logic.h"
#include "stats.h"
#include "audio.h"
#include "ui.h"

// ─── Global objects ──────────────────────────────────────────────────────────

static OrientationDetector orient;
static PomodoroTimer       timer;
static StatsStore          stats;
static ChimePlayer         chime;
static UIRenderer          ui;

// Screen power state
static bool     screenOn       = true;
static bool     screenDimmed   = false;
static uint32_t lastActivityMs = 0;
static uint32_t completedAtMs  = 0;     // 0 = not in completed state

// Forward declaration (defined below)
static void wakeScreen();

// ─── Orientation callback (fires on confirmed change) ───────────────────────

static void onOrientationConfirmed(Orientation o) {
    lastActivityMs = millis();

    TimerEvent evt = timer.onOrientation(o);

    switch (evt.type) {
    case TimerEvent::Type::STARTED:
        completedAtMs = 0;   // leaving completed state
        wakeScreen();
        chime.playBlip();
        break;

    case TimerEvent::Type::RESUMED:
        completedAtMs = 0;
        wakeScreen();
        chime.playBlip();
        break;

    case TimerEvent::Type::PAUSED:
        // Face-down → screen off is handled in power management
        break;

    case TimerEvent::Type::COMPLETED:
        // Handled by timer update, not here
        break;

    case TimerEvent::Type::STOPPED:
        completedAtMs = 0;
        wakeScreen();
        break;

    default:
        break;
    }
}

// ─── Screen power helpers ────────────────────────────────────────────────────

static void wakeScreen() {
    lastActivityMs = millis();
    if (!screenOn) {
        M5.Lcd.setBrightness(BRIGHTNESS_NORMAL);
        screenOn = true;
        // Force full UI redraw after wake
        ui.forceRedraw();
    }
    if (screenDimmed) {
        M5.Lcd.setBrightness(BRIGHTNESS_NORMAL);
        screenDimmed = false;
    }
}

static void sleepScreen() {
    if (screenOn) {
        M5.Lcd.setBrightness(0);
        screenOn = false;
    }
}

static void updatePowerManagement() {
    uint32_t now = millis();
    uint32_t idle = now - lastActivityMs;

    // Face-down → immediate screen off
    if (orient.confirmed() == Orientation::FACE_DOWN) {
        sleepScreen();
        return;
    }

    // Completed state → auto-off after 30 s to save battery
    if (timer.isCompleted() && completedAtMs > 0 &&
        now - completedAtMs > 30000) {
        sleepScreen();
        return;
    }

    // Running timer keeps screen on but dims after 15 s
    if (!screenDimmed && idle > SCREEN_DIM_MS && screenOn) {
        M5.Lcd.setBrightness(BRIGHTNESS_DIM);
        screenDimmed = true;
    }

    // Full off after 60 s if not running (running timer never full-off)
    if (screenOn && !timer.isRunning() && idle > SCREEN_OFF_MS) {
        sleepScreen();
    }
}

// ─── Setup / loop ────────────────────────────────────────────────────────────

void setup() {
    auto cfg = M5.config();
    cfg.internal_imu = true;
    cfg.internal_spk = true;
    M5.begin(cfg);

    orient.begin();
    orient.onConfirm(onOrientationConfirmed);
    timer.begin();
    stats.begin();
    chime.begin();
    ui.begin();

    lastActivityMs = millis();

    // Boot screen
    M5.Lcd.fillScreen(COLOR_BG);
    M5.Lcd.setTextColor(COLOR_FG, COLOR_BG);
    M5.Lcd.setTextSize(2);
    M5.Lcd.setTextDatum(MC_DATUM);
    M5.Lcd.drawString("Pomodoro", SCREEN_W / 2, 100);
    M5.Lcd.drawString("Cube", SCREEN_W / 2, 125);
    M5.Lcd.setTextSize(1);
    M5.Lcd.setTextColor(COLOR_DIM, COLOR_BG);
    M5.Lcd.drawString("v0.1.0", SCREEN_W / 2, 160);
    delay(1500);

    M5.Lcd.fillScreen(COLOR_BG);
}

void loop() {
    M5.update();

    // 1. Read IMU and update orientation (with debounce)
    orient.update();

    // 2. Advance timer
    TimerEvent evt = timer.update();

    // 3. Handle timer completion
    if (evt.type == TimerEvent::Type::COMPLETED) {
        wakeScreen();
        completedAtMs = millis();
        if (evt.mode == Mode::FOCUS) {
            stats.recordFocusComplete(timer.durationMs() / 60000UL);
            chime.playFocusDone();
        } else if (evt.mode == Mode::BREAK) {
            stats.recordBreakComplete(timer.durationMs() / 60000UL);
            chime.playBreakDone();
        }
        lastActivityMs = millis();
    }

    // 4. Advance audio sequencer (non-blocking)
    chime.update();

    // 5. Button overrides
    //    BtnA: force-start focus (even if orientation is ambiguous)
    //    BtnB: force-start break
    if (M5.BtnA.wasClicked()) {
        onOrientationConfirmed(Orientation::UPRIGHT);
    }
    if (M5.BtnB.wasClicked()) {
        onOrientationConfirmed(Orientation::FLAT_UP);
    }

    // 6. Render UI (skips when screen is off)
    ui.render(timer, orient, stats, !screenOn);

    // 7. Power management (dim / sleep)
    updatePowerManagement();

    delay(10);   // ~100 Hz loop
}
