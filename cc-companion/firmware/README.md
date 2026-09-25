# Companion Firmware Core

This directory currently contains hardware-independent C++ logic for the M5StickC S3 firmware. It intentionally does not flash or communicate with a connected device.

Run the host-side tests on macOS:

```sh
cd cc-companion/firmware
make test
```

`AppState` owns the device's cached CC rows, selection, gateway status, and gateway revision checks. `ReconnectBackoff` provides the capped 1s-to-60s reconnect schedule. `BuildListView` derives LCD-ready text and highlight flags without using M5 libraries, so display behavior is host-tested. `MainButton` derives short/long press actions and `AlertPolicy` centralizes DND alert suppression for actual confirmation/input events. `MessageFlow` implements the recording/transcription/confirmation/sending/ack lifecycle, preserving failed drafts for retry and blocking duplicate sends. The later M5Unified display, Wi-Fi/WebSocket transport, IMU, buzzer, and audio modules must adapt these public interfaces instead of duplicating state logic.
