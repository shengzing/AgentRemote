# Claude Code Companion MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and verify the LAN MVP that displays Claude Code status on M5StickC S3 and sends confirmed device text to a selected tmux-hosted Claude Code session.

**Architecture:** A Python/aiohttp gateway owns normalized session state and communicates with the M5StickC S3 through a versioned authenticated WebSocket protocol. PlatformIO firmware renders a local projection of gateway state and treats hardware input, alerts, audio, and provisioning as separate modules.

**Tech Stack:** Python 3.11+, aiohttp, pytest; PlatformIO, Arduino, M5Unified, ESP32-S3; tmux; OpenAI Whisper API for M4.

---

## Working agreement

- [ ] Keep each checkbox-sized item in its own focused change and commit after a passing test group.
- [ ] Do not include API keys, Wi-Fi passwords, pairing tokens, real transcript paths, or local settings in source control.
- [ ] Preserve `PRD_claude-code-companion.md` as the product baseline; update the design document when a public interface changes.
- [ ] Hardware target for manual tests: M5StickC S3 at `/dev/cu.usbmodem1101`, serial speed 115200.

## Phase 0: Scaffold and executable test loop

- [x] Create the repository layout described in `docs/2026-07-26-modular-design.md` and add `.gitignore` for Python, PlatformIO, firmware secrets, and audio captures.
- [x] Pin gateway developer dependencies (`aiohttp`, `pytest`, `pytest-asyncio`) and document one command to create/install the virtual environment.
- [ ] Add a `platformio.ini` targeting M5StickC S3 with a minimal M5Unified screen-and-serial boot program.
- [ ] Flash the minimal firmware, capture the serial boot log at 115200, and verify the LCD produces a visible build identifier.
- [x] Add one gateway test and one hardware-free firmware test command to the developer README; both must run on a clean checkout.

Acceptance: `pytest` and PlatformIO native tests pass; the M5 boots the project firmware rather than UiFlow2 and remains visible through `/dev/cu.usbmodem1101`.

## Phase 1: Gateway domain and Hook integration (M1a)

- [x] Define pure `Session`, `CcState`, normalized event, summary, and protocol-version models in `cc-companion/gateway/domain/`.
- [x] Write unit tests for state transitions from `Notification`, `Stop`, and throttled progress events, including unknown/malformed payloads.
- [x] Implement an eight-slot session registry with stable allocation for a live `session_id`, expiry/reclaim behavior, and deterministic snapshot ordering.
- [x] Define the `POST /hook` adapter input contract; write aiohttp tests for accepted payloads, invalid payloads, and a non-blocking response.
- [x] Implement the hook normalizer behind an isolated attention classifier; log only diagnostic metadata, not full user data by default.
- [x] Add `cc-companion/cc-integration/settings.example.json` and a launcher that forwards documented Hook JSON to `http://127.0.0.1:7421/hook`.
- [ ] Capture a real, redacted local Claude Code Hook payload and add it as a test fixture only after checking it contains no secret or private content.

Acceptance: a real/local test hook produces one correctly allocated CC state in the gateway log and test snapshot; malformed requests do not crash the service or create sessions.

## Phase 2: Safe tmux injection (M1b)

- [x] Define CC-to-tmux mapping configuration and validation; keep display `cc_code` separate from tmux target names.
- [x] Write tests using a fake tmux executable for argument construction, target-unreachable error mapping, empty text rejection, and multi-line first-line behavior.
- [x] Implement the tmux adapter with subprocess argument arrays and a short timeout; do not use a shell.
- [ ] Implement a local gateway command or temporary authenticated test endpoint to exercise `message.send` before a device exists.
- [ ] Start a disposable `tmux new-session -d -s cc1` test target and prove that one safe text line plus Enter reaches it.
- [ ] Remove or lock down any temporary test endpoint before merging device connectivity.

Acceptance: the test suite proves no shell interpolation; manual injection reaches the intended tmux pane and an absent target returns a non-destructive error.

## Phase 3: WebSocket protocol, pairing, and state delivery (M2a)

- [x] Write version-1 JSON fixtures for `device.hello`, `device.ready`, `cc.snapshot`, `cc.state`, `message.send`, `message.ack`, and `ping`/`pong`.
- [x] Write gateway tests for protocol version rejection, invalid type rejection, unauthorized device rejection, snapshot on connect, and state-delta broadcast.
- [x] Implement a six-digit, time-limited pairing-code flow; persist only a secure hash of the issued device token.
- [x] Implement the WebSocket hub with one device connection for MVP, 30-second liveness checks, and a revisioned full snapshot after every reconnect.
- [x] Add configuration loading for bind address, port, pairing storage path, and tmux mappings, with safe example values and environment-variable overrides.
- [x] Test hook -> registry -> WebSocket delta end-to-end with aiohttp's test client.

Acceptance: an authorized test WebSocket receives a valid full snapshot and then exactly one revisioned delta when a hook is submitted; invalid tokens receive no CC data.

## Phase 4: Firmware connectivity and display (M2b)

- [ ] Implement `firmware/protocol` connection configuration, JSON decoding, ping/pong, reconnect backoff, and only the v1 messages required for snapshots/deltas. (Reconnect policy is implemented; hardware transport remains pending.)
- [x] Implement hardware-free parser/revision tests for malformed messages, stale deltas, and snapshot replacement.
- [x] Implement `firmware/state` for eight rows, selected target preservation, summary truncation, and explicit gateway-offline state.
- [x] Implement `firmware/ui` list rendering within the 160x80 display, using numbered badges as the primary identifier and colors only as a secondary cue.
- [ ] Add a compiled-in development configuration for a controlled LAN test; move credentials out of firmware source before the phase is accepted.
- [ ] Flash the device, pair it, connect it to the gateway, and submit hooks for at least two test sessions.

Acceptance: the M5 shows up to eight rows from a gateway snapshot, updates a row within the PRD's 1.5-second LAN target, and displays an offline indication after the gateway is stopped.

## Phase 5: Selection, attention, and text send (M3)

- [x] Implement debounced front-button short press for next-target selection and long-press detection without blocking the rendering/network loop.
- [ ] Implement list/detail state transitions. Add IMU single/double-tap only after button behavior is stable.
- [x] Implement Attention alert behavior: wake/display highlight plus a two-beep pattern; keep Done and Progress silent. (Policy layer complete; hardware buzzer remains pending.)
- [ ] Implement local DND state and face-down detection; DND suppresses wake/beep but never drops state updates. (DND policy is complete; IMU integration remains pending.)
- [x] Implement confirmation view and `message.send` / `message.ack` handling. Preserve the draft after an unreachable-target acknowledgement. (Hardware transport/rendering remains pending.)
- [ ] Perform manual test of button selection -> confirmed text -> WebSocket -> tmux target, including failure and retry paths.

Acceptance: a Notification hook highlights and alerts the correct CC; the user can change target, send one confirmed line, receive an acknowledgement, and retry after an unavailable tmux session.

## Phase 6: Voice record and cloud transcription (M4)

- [ ] Bring up the PDM microphone independently and verify 16-kHz, 16-bit mono samples over serial or a local WAV capture.
- [ ] Implement bounded push-to-talk recording with a 15-second maximum, a minimum 0.5-second threshold, and a deterministic cancellation path. (Flow state complete; PDM hardware capture pending.)
- [x] Add audio protocol messages (`audio.start`, binary chunks, `audio.end`) with a recording ID, sequence validation, and explicit size limits.
- [x] Write gateway integration tests for chunk ordering, size/duration rejection, transcription failure, and a successful text result.
- [ ] Implement a transcription adapter using the server-side OpenAI API key only; add redacted configuration documentation and no key logging.
- [ ] Render transcription-pending, transcript-confirmation, re-record, and send-success/failure states on the device.
- [ ] Measure spoken-word-to-tmux latency on the LAN and record the result against the three-second PRD target.

Acceptance: a valid spoken phrase becomes an editable/confirmable transcript and is injected only after a button confirmation; oversized/short/failed recordings provide an actionable retry state.

## Phase 7: Provisioning, resilience, and release readiness (M5/M6)

- [ ] Implement first-boot AP provisioning for Wi-Fi SSID/password and gateway address, with NVS persistence and a documented button-combination reset.
- [ ] Replace the development network configuration with provisioned settings and verify credentials are never printed to serial logs.
- [ ] Verify restart behavior: device reconnects after gateway restart, gateway resumes snapshot delivery, and the last display remains understandable while offline.
- [ ] Add display sleep/wake policy that preserves network liveness and Attention wake behavior.
- [ ] Run a two-to-eight-session soak test for one hour, observing registry code stability, reconnects, RAM behavior, and alert delivery.
- [ ] Produce an operator README covering installation, tmux launch convention, Hook setup, pairing, Wi-Fi provisioning, logs, and recovery.

Acceptance: a freshly flashed device can be provisioned and paired without source edits; the system survives expected reconnections and completes the one-hour v0.1 soak without a lost state update.

## Deferred backlog

- [ ] v0.2: Choose either Tailscale or WSS/cloudflared before implementation; write a threat model and do not expose the LAN HTTP Hook endpoint publicly.
- [ ] v0.2: Add TLS/public connectivity integration tests over the selected route and repeat remote status + injection acceptance.
- [ ] v1.1: Design signed/verified OTA updates and rollback before enabling OTA.
- [ ] v1.1: Add optional shortcut phrase mapping only after preserving the default full-phrase injection semantics.
- [ ] v1.1: Add local `whisper.cpp` as a configuration-selectable gateway adapter with equivalent result/error contracts.
- [ ] v1.1: Evaluate a Grove encoder as an input-only module; it must not alter the gateway protocol.

## Completion definition for v0.1

- [ ] Every M1-M6 acceptance condition above passes on the actual M5StickC S3 and a local machine running tmux and Claude Code.
- [ ] Gateway and firmware automated tests pass from documented commands.
- [ ] No secrets, live tokens, audio samples, or private transcripts are tracked.
- [ ] The operator README supports a fresh setup and a known-good recovery path.
