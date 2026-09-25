# Claude Code Companion Modular Design

## Scope and current baseline

This document turns the approved PRD v0.2 into independently buildable modules. The first release is the LAN MVP (v0.1): it supports up to eight Claude Code instances, pushes status changes to one M5StickC S3, and injects confirmed text into a selected tmux session. Public-network access, OTA, local transcription, and an external encoder remain separate future increments.

Current repository state: the gateway core, Hook HTTP adapter, pairing/token store, WebSocket state delivery, safe tmux injection, and bounded audio/transcription boundary are implemented with host tests. The hardware-independent C++ firmware state, list-view, input/alert, and message-flow modules are also host-tested. The connected M5StickC S3 is healthy and currently runs UiFlow2 v2.4.5; PlatformIO/M5Unified board integration, firmware upload, and physical validation remain intentionally pending user confirmation.

## Design principles

- Keep business rules independent of HTTP, WebSocket, tmux, and ESP32 libraries, so they can be unit tested on the host.
- Make the gateway authoritative for CC session state and assignment of `cc_code`; the device caches and renders a projection only.
- Version all device/gateway messages from the first implementation. Reject invalid messages without terminating the WebSocket session.
- Treat all text from hooks, speech recognition, and devices as data. Never compose a shell command; invoke tmux with an argument array and allow only the first input line.
- Ship a narrow end-to-end slice before optional features: hook -> gateway -> device display, then device text -> gateway -> tmux. Voice is added only after that path is reliable.

## Component map

```text
Claude Code hook scripts              M5StickC S3 firmware
          | HTTP POST                         | Wi-Fi / WebSocket
          v                                   v
  [Gateway HTTP adapter]              [Network and protocol]
          |                                   |
          v                                   v
  [Event normalizer]                  [Device application state]
          |                                   |
          v                                   v
  [Session registry + state machine]  [UI / input / alert / audio]
          |                                   |
          +------ [WebSocket hub] -----------+
          |
          +------ [tmux adapter]
          |
          +------ [Whisper adapter] (M4 only)
```

The left and right halves communicate exclusively through the versioned protocol module. This prevents the firmware UI from depending on the gateway's internal registry or tmux behavior.

## Module boundaries

| Module | Responsibility | Owns | Depends on | Explicitly does not own |
|---|---|---|---|---|
| `gateway.domain` | Normalize events, assign CC codes, state transitions, idle expiry | `Session`, `CcState`, summaries, event history | Python standard library | HTTP, tmux, WebSocket |
| `gateway.hooks` | Validate and accept Claude Code Hook POSTs | Request parsing and response status | `gateway.domain`, aiohttp | Session allocation details |
| `gateway.realtime` | Authenticate devices, broadcast deltas, serve snapshots | WebSocket lifecycle and connected clients | protocol, domain | UI layout, speech recognition |
| `gateway.tmux` | Confirm target reachability and inject one safe text line | tmux subprocess calls and errors | Python subprocess | Speech/UI semantics |
| `gateway.transcription` | Convert completed audio to text | Whisper request, audio limits, errors | protocol, OpenAI client | Recording or sending UI |
| `gateway.runtime` | Compose adapters, configuration, shutdown and metrics/logging | aiohttp app and service lifecycle | all gateway modules | Domain policy |
| `cc-integration` | Convert Claude Code Hook payloads to the gateway contract | hook launcher and example settings | curl or Python stdlib | Gateway internals |
| `firmware.protocol` | Connect/reconnect, authenticate, encode/decode messages | WS transport, message validation | Wi-Fi/WS library | Display state decisions |
| `firmware.state` | Cache CC rows and drive local view states | selected CC, notification read state, recording flow | protocol model | LCD or hardware drivers |
| `firmware.ui` | Render list/detail/record/confirm states | LCD drawing and font fallback | `firmware.state` | WebSocket/tmux |
| `firmware.input-alert` | Button/IMU interpretation, DND, buzzer feedback | debouncing, gestures, alert pattern | `firmware.state`, M5 hardware APIs | Network protocol |
| `firmware.audio` | Capture a bounded microphone recording and upload it | PCM buffering, duration/size checks | protocol, I2S/PDM API | Whisper/transcription |
| `firmware.provisioning` | First-run Wi-Fi and gateway configuration plus persisted device data | AP portal, NVS keys, reset action | Wi-Fi/NVS | Pairing decisions on gateway |
| `test-harness` | Reproducible fake hook/device/tmux integrations | fixtures and protocol captures | public module interfaces | product behavior |

## Repository layout

```text
cc-companion/
  gateway/
    app.py                 # Composition entry point only
    config.py
    domain/                # Pure models, registry, normalizer, state machine
    adapters/              # HTTP hooks, WS hub, tmux, Whisper
    protocol/              # JSON schemas / codecs shared semantically with firmware
    tests/
  cc-integration/
    hook.py
    settings.example.json
  firmware/
    platformio.ini
    src/
      main.cpp             # Hardware/runtime wiring only
      protocol/ state/ ui/ input_alert/ audio/ provisioning/
    test/                  # PlatformIO native tests where hardware-free
  docs/
```

Use Python 3.11+ and `aiohttp` for the LAN gateway. Use PlatformIO with Arduino and M5Unified for the M5StickC S3, rather than retaining the interactive UiFlow2 firmware. `gateway.domain` and `firmware.state` must remain free of framework calls.

## Core contracts

### Hook to gateway

`POST /hook` receives the PRD's `session_id`, `hook_event_name`, `cwd`, `transcript_path`, and `message`. The adapter returns `202 Accepted` after validation and enqueues normalization; hook failures must never block Claude Code. A missing `session_id` or unknown event returns `400`, is logged with no secret payloads, and does not create a session.

Normalization maps event names to `WORKING`, `AWAITING_CONFIRMATION`, `AWAITING_INPUT`, `DONE`, or `ERROR`. `Notification` is high priority only when its text indicates user action; the exact classifier is isolated behind a function so it can be improved without changing transport code. `cc_code` values are allocated from 1 through 8, stay stable for a live `session_id`, and are reclaimed only after session expiry.

### Gateway to device

Every JSON envelope contains `version: 1` and `type`. The initial protocol consists of:

| Direction | Type | Purpose |
|---|---|---|
| device -> gateway | `device.hello` | device ID, token, and protocol version |
| gateway -> device | `device.ready` / `device.error` | auth result and capability negotiation |
| gateway -> device | `cc.snapshot` | full current registry after connect/reconnect |
| gateway -> device | `cc.state` | one normalized state delta |
| device -> gateway | `cc.select` | optional persistence of the current target |
| device -> gateway | `message.send` | confirmed, single-line text and `cc_code` |
| gateway -> device | `message.ack` | accepted/injected or actionable failure reason |
| either direction | `ping` / `pong` | 30-second liveness check |

Pairing is a separate pre-auth exchange: `pair.begin` -> `pair.code` -> `pair.complete`. The gateway stores only a hashed token; the device stores the token in NVS. The protocol's snapshot shape is the source of truth for the maximum-eight list, including a `revision` so old state deltas can be discarded after reconnect.

### Text injection and audio

For `message.send`, the gateway trims the input, rejects empty text, converts multi-line text to its first line while returning a warning, and imposes a modest character limit. It invokes `tmux send-keys -t <configured-session> -- <text> Enter` via an argument array, never a shell. The selected CC must have a configured tmux target; absence returns `TARGET_UNREACHABLE` without discarding the device's displayed draft.

Audio is deliberately deferred until the text round-trip works. M4 adds `audio.start` metadata, binary PCM chunks, and `audio.end`; a recording ID ties the chunks and transcription result together. The gateway rejects recordings longer than 15 seconds or outside 16-kHz, 16-bit mono parameters before calling Whisper. The returned transcript enters the same device confirmation state that produces `message.send`, keeping transcription separate from injection.

## State ownership and failure behavior

The session registry is the sole writer of CC state. It publishes immutable snapshot/delta messages to the WebSocket hub. The device updates its local cache only from accepted revisions, preserves its selected valid code across a snapshot, and selects the first available row otherwise. A device may locally mark an Attention row read, but it cannot turn that CC back to working; only a gateway event can do so.

On WebSocket loss, firmware shows `gateway offline`, keeps the last snapshot, and retries with exponential backoff capped at 60 seconds. On reconnect, it requests/receives a snapshot rather than replaying arbitrary events. Gateway restarts deliberately invalidate active connections; a future durable queue is not required for v0.1, provided hooks return quickly and state is rebuilt by new events. The device may remain plugged in for MVP; battery sleep is M5.

## Versioned increments

| Increment | Delivers | Excluded intentionally |
|---|---|---|
| M1 | Hook ingestion, registry, one tmux-safe text injection | Device and voice |
| M2 | Device pairing, WS snapshot/deltas, static list UI | IMU, buzzer, audio |
| M3 | Selection, attention alert, DND and reconnect | AP portal and voice |
| M4 | PTT recording, cloud transcription, confirmation/retry | Local Whisper |
| M5 | AP provisioning, persisted config, sleep behavior and endurance test | OTA |
| M7 / v0.2 | Tailscale or WSS public path, device authentication hardening | New UI features |
| v1.1 | OTA, shortcut phrases, local Whisper option, Grove encoder | Changes to M1-M5 contracts |

## Verification strategy

Unit-test the domain state machine, code allocation/reclamation, summary truncation, message validation, safe single-line injection argument construction, and revision handling. Integration-test the aiohttp hook and WebSocket endpoints with a fake tmux executable. Keep JSON fixtures shared conceptually between gateway tests and firmware tests. Manual hardware tests use the identified port `/dev/cu.usbmodem1101` at 115200 baud: boot, Wi-Fi connection, WS reconnect, display list, alert tone, button transition, and microphone capture are recorded against acceptance cases in the To-Do document.

## Deferred decisions

- The PRD's open questions remain: grouping/color policy, Grove encoder, and the specific v0.2 public route. The v0.1 design assumes allocation by session start order and no encoder.
- Decide whether a device has a fixed `device_id` printed/derived from MAC or created on first boot. The recommended choice is a MAC-derived non-secret ID and a separately generated pairing token.
- Hook event payloads vary by Claude Code version. Capture real local Hook JSON during M1 and constrain the normalizer to verified fields rather than guessing transcript semantics.
