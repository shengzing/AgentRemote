# Claude Code Companion — 设备接入层设计（Device Access Layer）

| 项 | 内容 |
|---|---|
| 文档版本 | v0.1（草案） |
| 创建日期 | 2026-09-24 |
| 状态 | 已评审（v0.1 修正后通过） |
| 前置文档 | [PRD v0.2](../PRD_claude-code-companion.md)、[Modular Design](2026-07-26-modular-design.md) |

---

## 1. 背景与动机

### 1.1 现状

当前 `adapters/realtime.py` 的 `websocket_handler` 是一个 145 行单体函数，将 7 个职责耦合在一个 async 循环里：

1. WebSocket 传输生命周期（prepare / iterate / close）
2. 配对认证（`pair.complete` / `device.hello`）
3. 状态推送（attach hub + push snapshot + broadcast delta）
4. 心跳保活（`ping` / `pong`）
5. 文本注入（`message.send` → tmux inject → `message.ack`）
6. 音频录制+转写（`audio.start` / binary / `audio.end` → Whisper）
7. 断线清理（cancel recording / detach hub / log）

配对、认证、状态广播、动作分发全部绑死在 aiohttp WebSocket 传输上。要接一个 REST 设备或 CLI 设备，就得把这 145 行逻辑重新实现一遍。

### 1.2 问题

- **传输绑定**：配对/认证/动作分发与 aiohttp WS 耦合，无法复用到其他传输
- **能力假设**：所有设备被默认推送快照，但有的终端只有输入功能、没有显示能力
- **测试困难**：动作分发逻辑无法脱离 aiohttp TestClient 做纯单元测试
- **扩展成本高**：新增设备类型 = 重写整套认证+状态+动作逻辑

### 1.3 目标

抽象出**设备接入层（DeviceAccessLayer）**，统一管理配对认证和设备动作，让不同传输协议的设备（M5 WebSocket、Web 模拟器、REST API、CLI 等）只需实现薄适配器即可接入网关。

### 1.4 非目标

- 不改变设备看到的 WebSocket JSON 协议（v1 协议不变，对固件透明）
- 不改动 `domain/` 业务核心层（Registry / Normalizer / models）
- 不改动 `protocol/messages.py` 的消息编解码逻辑（仅新增可选字段）
- 不在本阶段实现 REST / CLI 适配器（仅定义接口规范）

---

## 2. 设计原则

1. **接入层不感知传输协议** — 只接受/返回 Python 对象，不依赖 aiohttp / WS / HTTP
2. **适配器不感知业务逻辑** — 只做格式转换（传输帧 ↔ Python 对象），不实现配对规则/状态机/tmux 注入
3. **能力声明驱动** — 设备连接时声明自身能力，接入层按能力决定行为（无 display 则不推快照）
4. **动作最小集 + 可选扩展** — 必选动作覆盖所有设备，可选动作按设备能力实现
5. **协议对设备透明** — 现有 WS JSON 协议不变，这是网关内部重构
6. **Domain 层零改动** — 业务核心已解耦，重构只在 adapter 层

---

## 3. 整体架构

```text
设备适配器（薄传输层，只做 I/O 格式转换）
  ├── M5 WebSocket 适配器        WS JSON 帧 + 二进制音频帧
  ├── Web 模拟器适配器           同 WS 协议，独立路由
  ├── REST 适配器（未来）        HTTP POST → 接入层调用
  └── CLI 适配器（未来）         stdin/stdout → 接入层调用
         │
         ▼  统一调用接入层 API
  ┌──────────────────────────────────────────────┐
  │            DeviceAccessLayer（接入层）          │
  │                                              │
  │  ┌────────────┐  ┌────────────────────────┐ │
  │  │ Pairing    │  │ DeviceSession Registry  │ │
  │  │ Service    │  │ (在线会话生命周期)      │ │
  │  └────────────┘  └───────────┬────────────┘ │
  │                              │               │
  │    ┌─────────────┬───────────┼──────────┐   │
  │    ▼            ▼           ▼          ▼   │
  │  pair/auth   submit      ack         select │
  │              (必选)      (回执)      (可选)  │
  │                              │               │
  │  ┌──────────────────────────┼────────────┐  │
  │  │  StateProjector (可选)                 │  │
  │  │  snapshot/delta → 仅推给有 display 的设备│  │
  │  └────────────────────────────────────────┘  │
  └──────────────────┬───────────────────────────┘
                     │
                     ▼
           ┌─────────────────────────┐
           │ Gateway Core            │
           │ ├─ domain: Registry /   │
           │ │  Normalizer / Audio   │
           │ └─ infra: tmux /        │
           │    Transcription        │
           └─────────────────────────┘
```

**关键边界**：接入层是适配器和 Domain 之间的唯一桥梁。适配器 → 接入层 → Domain，方向单向，适配器不直接触碰 Registry 或 tmux。

---

## 4. 核心概念

### 4.1 DeviceSession（设备会话）

一个已认证的设备连接在接入层中的抽象表示。适配器创建它、接入层持有它。它代表"网关 → 设备"的出站通道。

- `device_id`：设备唯一标识（MAC 派生或首次启动生成）
- `capabilities`：设备能力集合（见 4.4）
- `send(message)`：向设备推送一条消息（适配器实现，转为传输格式）
- `close()`：关闭连接

### 4.2 DeviceAccessLayer（接入层）

接入层核心，组合 PairingService + 会话注册表 + 动作分发 + 状态投影。它是适配器唯一调用的对象。

### 4.3 DeviceAdapter（设备适配器）

薄传输层，只做两件事：
1. 将传输层入站消息解码后调用接入层的对应方法
2. 实现 `DeviceSession`，将接入层出站推送编码为传输格式

### 4.4 Capability（设备能力）

设备在 `device.hello` 中声明的能力集合：

| 能力 | 含义 | 默认 |
|---|---|---|
| `input` | 可提交文本指令 | 必选，始终为 true |
| `display` | 有屏幕，可接收状态推送 | 可选，缺省时按 true 处理（向后兼容） |
| `audio` | 有麦克风，可录制音频 | 可选，缺省时 false |
| `select` | 支持显式目标选择 | 可选，缺省时 false |

**向后兼容规则**：`capabilities` 字段缺失时，默认 `{"input", "display"}`（当前 M5 和 Web 模拟器都有屏幕）。

**纯输入设备示例**：一个 REST 端点或 CLI 工具只声明 `{"input"}`，接入层不会向它推送快照或增量。

---

## 5. 抽象动作定义

### 5.1 必选动作（所有设备必须支持）

| ID | 动作 | 方向 | 说明 | 协议消息 |
|---|---|---|---|---|
| A1 | **配对认证** | device→gateway | 6 位配对码换 token，建立信任；后续连接用 token 认证 | `pair.complete` → `device.hello` |
| A2 | **提交指令** | device→gateway | 向指定 `cc_code` 发送文本，触发 tmux 注入 | `message.send` |
| A3 | **回执反馈** | gateway→device | 注入结果（成功/失败/原因），设备可据此重试 | `message.ack` |

**最小设备**：只需实现 A1+A2+A3。例如一个 REST 端点收到 `POST /send {cc_code: 1, text: "允许"}` → 调用 `access_layer.submit_text()` → 返回 ack JSON。无配网、无屏幕、无音频。

### 5.2 可选动作（按设备能力实现）

| ID | 动作 | 方向 | 前置能力 | 说明 | 协议消息 |
|---|---|---|---|---|---|
| O1 | **状态订阅** | gateway→device | `display` | 接收全量快照 + 增量推送，被动提醒的基础 | `cc.snapshot` / `cc.state` |
| O2 | **选择目标** | device→gateway | `select` | 显式选择/持久化当前目标 CC | `cc.select` |
| O3 | **音频输入** | device→gateway | `audio` | 录制 → 转写 → 获得文本 → 进入提交流程 | `audio.start` / binary / `audio.end` → `transcript.result` |
| O4 | **保活心跳** | 双向 | 长连接 | 存活检测与重连后状态恢复 | `ping` / `pong` |

> **协议变更说明**：`cc.select` 是新增消息类型（当前 `protocol/messages.py` 尚未实现）。`capabilities` 是 `device.hello` 新增可选字段。详见第 8 节。

### 5.3 动作流程图

```text
                    ┌─────────────────────────────────┐
                    │         必选路径（所有设备）      │
                    └─────────────────────────────────┘

  device ──pair.complete──► [接入层] ──token──► device
  device ──device.hello───► [接入层] ──device.ready──► device
  device ──message.send───► [接入层] ──tmux inject──► [tmux]
  [接入层] ──message.ack──► device

                    ┌─────────────────────────────────┐
                    │       可选路径（按能力）          │
                    └─────────────────────────────────┘

  [display]  [接入层] ──cc.snapshot/cc.state──► device   (Hook 事件到达时推送)
  [select]   device ──cc.select──► [接入层]               (持久化目标)
  [audio]    device ──audio.start──► [接入层]
            device ──binary PCM──►  [接入层]
            device ──audio.end───►  [接入层] ──transcript.result──► device
  [长连接]   device ──ping──► [接入层] ──pong──► device
```

### 5.4 确认环节说明

确认（Confirm）不作为接入层的独立动作。确认逻辑由设备/适配器自决：

- **有屏幕的设备**（M5 / Web）：转写结果在本地展示，用户确认后设备发送最终 `message.send`
- **无屏幕的设备**（REST / CLI）：直接发送 `message.send`，无确认环节

接入层始终将 `submit` 视为最终指令。如未来需要服务端管理的两步确认（`submit_draft` → `confirm_send`），可在此基础上扩展，不影响当前设计。

---

## 6. 接入层接口定义

### 6.1 DeviceSession 协议

```python
# access/session.py

from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class DeviceSession(Protocol):
    """适配器实现的设备会话——接入层通过它向设备推送出站消息。"""

    @property
    def device_id(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[str]: ...

    async def send(self, message: dict[str, Any]) -> None:
        """向设备推送一条 JSON 消息。适配器负责转为传输格式。"""
        ...

    async def close(self) -> None:
        """关闭设备连接。"""
        ...
```

设计要点：
- **单一 `send` 方法**而非 `send_snapshot` / `send_ack` 等多个方法——接入层按能力决定发什么，适配器只管怎么发
- `capabilities` 是 `frozenset` 不可变，在认证时确定后不变
- 适配器实现 `send` 时，内部将 dict 序列化为 WS JSON 帧 / HTTP 响应 / stdout 行

### 6.2 DeviceAccessLayer 类

```python
# access/layer.py

import asyncio
import time
from typing import Optional

from adapters.pairing import PairingService
from adapters.tmux import TmuxInjector, InjectResult, InjectError
from domain.audio import RecordingService, AudioFormat, AudioValidationError
from domain.registry import SessionRegistry
from protocol.messages import PROTOCOL_VERSION
from .session import DeviceSession
from .capabilities import CAPABILITY_DISPLAY
from .messages import state_message, snapshot_message


class DeviceAccessLayer:
    """接入层核心——适配器唯一调用的对象。"""

    def __init__(
        self,
        pairing: PairingService,
        registry: SessionRegistry,
        tmux: TmuxInjector,
        recording: RecordingService,
    ):
        self._pairing = pairing
        self._registry = registry
        self._tmux = tmux
        self._recording = recording
        self._sessions: dict[str, DeviceSession] = {}
        self._active_recordings: dict[str, str] = {}  # device_id → recording_id

    # ── 生命周期 ──

    def pair(self, device_id: str, code: str) -> Optional[str]:
        """配对码换 token（10 分钟过期）。返回 token 或 None。"""
        return self._pairing.complete(device_id, code)

    def connect(self, session: DeviceSession, token: str) -> bool:
        """认证并注册设备会话。仅做认证+注册，不推送快照。

        适配器在 connect 成功后，自行检查 capabilities 并调用
        push_snapshot()（如有 display 能力）。这避免了接入层依赖
        event loop，使其可被同步适配器（CLI/REST）调用。
        """
        if not self._pairing.verify(session.device_id, token):
            return False
        self._sessions[session.device_id] = session
        return True

    def disconnect(self, device_id: str) -> None:
        """设备断线清理：取消该设备的活跃录音、注销会话。"""
        recording_id = self._active_recordings.pop(device_id, None)
        if recording_id is not None:
            self.cancel_audio(device_id, recording_id)
        self._sessions.pop(device_id, None)

    def is_online(self, device_id: str) -> bool:
        return device_id in self._sessions

    # ── 入站动作（设备 → 网关）──

    def select_target(self, device_id: str, cc_code: int) -> None:
        """可选：记录设备当前选中的目标 CC。v0.1 仅日志。"""
        pass

    def submit_text(self, device_id: str, cc_code: int, text: str) -> dict:
        """必选：提交文本 → 校验目标 → tmux 注入 → 返回 ack dict。

        适配器负责将返回的 ack dict 通过 session.send() 或 HTTP
        response 发送给设备。接入层不直接推送 ack。
        """
        if not self._registry.has_cc_code(cc_code, now=time.time()):
            result = InjectResult(ok=False, text="", error=InjectError.TARGET_UNREACHABLE)
        else:
            result = self._tmux.inject(cc_code, text)
        return self._build_ack(cc_code, result)

    def begin_audio(self, device_id: str, recording_id: str,
                    cc_code: int, fmt: AudioFormat) -> bool:
        """可选：开始录音会话。校验设备在线且无活跃录音。"""
        if device_id not in self._sessions:
            return False
        if device_id in self._active_recordings:
            return False
        try:
            self._recording.begin(recording_id, cc_code, fmt)
            self._active_recordings[device_id] = recording_id
            return True
        except AudioValidationError:
            return False

    def append_audio(self, device_id: str, recording_id: str,
                     seq: int, pcm: bytes) -> Optional[str]:
        """可选：追加 PCM 分片。校验录音属于该设备。"""
        if self._active_recordings.get(device_id) != recording_id:
            return "RECORDING_NOT_ACTIVE"
        try:
            self._recording.append(recording_id, seq, pcm)
            return None
        except AudioValidationError as e:
            return str(e)

    def finish_audio(self, device_id: str, recording_id: str) -> dict:
        """可选：结束录音 → 转写 → 返回 transcript.result dict。"""
        if self._active_recordings.get(device_id) != recording_id:
            return {"ok": False, "error": "RECORDING_NOT_ACTIVE"}
        self._active_recordings.pop(device_id, None)
        try:
            transcript = self._recording.finish(recording_id)
            return {"ok": True, "text": transcript}
        except AudioValidationError as e:
            return {"ok": False, "error": str(e)}

    def cancel_audio(self, device_id: str, recording_id: str) -> None:
        """可选：取消录音。"""
        if self._active_recordings.get(device_id) == recording_id:
            self._active_recordings.pop(device_id, None)
        try:
            self._recording.cancel(recording_id)
        except AudioValidationError:
            pass

    # ── 出站推送（网关 → 设备，仅 display 设备）──

    async def broadcast_state(self, session, revision: int) -> None:
        """Hook 事件到达后，向所有有 display 能力的设备推送增量。"""
        msg = state_message(session, revision)
        await self._fan_out(msg, require_capability=CAPABILITY_DISPLAY)

    async def push_snapshot(self, device_id: str) -> None:
        """向单个设备推送全量快照（仅 display 设备）。

        适配器在 connect 成功且设备有 display 能力时调用此方法。
        """
        session = self._sessions.get(device_id)
        if session and CAPABILITY_DISPLAY in session.capabilities:
            snapshot = self._registry.snapshot(now=time.time())
            await session.send(snapshot_message(snapshot))

    async def send_error(self, device_id: str, code: str) -> None:
        """向设备推送错误。"""
        session = self._sessions.get(device_id)
        if session:
            await session.send({
                "version": PROTOCOL_VERSION,
                "type": "device.error",
                "error": code,
            })

    # ── 内部 ──

    async def _fan_out(self, msg: dict, require_capability: str) -> None:
        targets = [s for s in self._sessions.values()
                    if require_capability in s.capabilities]
        await asyncio.gather(
            *(s.send(msg) for s in targets),
            return_exceptions=True,
        )

    @staticmethod
    def _build_ack(cc_code: int, result: InjectResult) -> dict:
        ack = {
            "version": PROTOCOL_VERSION, "type": "message.ack",
            "cc_code": cc_code, "ok": result.ok, "text": result.text,
        }
        if result.warning:
            ack["warning"] = result.warning
        if result.error:
            ack["error"] = result.error.value
        return ack
```

### 6.3 能力协商流程

```text
设备                           接入层                         PairingService
  │                              │                               │
  │── pair.complete ────────────►│── complete() ────────────────►│
  │◄── pair.complete.ok + token ─┤◄── token ─────────────────────┤
  │                              │                               │
  │── device.hello ─────────────►│── verify(token) ─────────────►│
  │   + capabilities             │◄── ok ─────────────────────────┤
  │                              │                               │
  │                              │ register session(capabilities)│
  │                              │ if "display": push snapshot   │
  │                              │                               │
  │◄── device.ready ─────────────┤                               │
  │   + negotiated capabilities  │                               │
  │◄── cc.snapshot (if display) ─┤                               │
```

`device.hello` 新增可选 `capabilities` 数组字段：

```json
{
  "version": 1,
  "type": "device.hello",
  "device_id": "rest-001",
  "token": "...",
  "capabilities": ["input"]
}
```

`device.ready` 回显协商后的能力集：

```json
{
  "version": 1,
  "type": "device.ready",
  "capabilities": ["input"]
}
```

---

## 7. 设备适配器规范

### 7.1 适配器接口契约

每个适配器必须：

1. 在设备连接时创建 `DeviceSession` 实例，调用 `access_layer.connect()`
2. 将入站消息按 `type` 分发到接入层的对应方法
3. 实现 `DeviceSession.send()` 将出站 dict 转为传输格式
4. 在断线时调用 `access_layer.disconnect()`

### 7.2 WebSocket 适配器（M5 + Web 模拟器）

重构后的 `realtime_ws.py` 从 145 行单体变为薄适配器：

```python
# adapters/realtime_ws.py（重构后骨架）

async def websocket_handler(request: web.Request) -> web.StreamResponse:
    websocket = web.WebSocketResponse(heartbeat=30.0)
    await websocket.prepare(request)
    access = request.app[ACCESS_LAYER_KEY]
    session = _WsSession(websocket)
    active_recording_id = None
    active_recording_seq = 0

    try:
        async for incoming in websocket:
            if incoming.type in {CLOSE, CLOSING, CLOSED, ERROR}:
                break
            if incoming.type == BINARY:
                if active_recording_id and session.device_id:
                    err = access.append_audio(
                        session.device_id, active_recording_id,
                        active_recording_seq, bytes(incoming.data),
                    )
                    if err:
                        await session.send(transcript_error_msg(active_recording_id, err))
                        access.cancel_audio(session.device_id, active_recording_id)
                        active_recording_id = None
                    else:
                        active_recording_seq += 1
                continue
            if incoming.type != TEXT:
                await session.send({"version": 1, "type": "device.error", "error": "INVALID_MESSAGE"})
                continue

            msg = decode_client_message(incoming.json())
            if msg["type"] == "pair.complete":
                token = access.pair(msg["device_id"], msg["code"])
                if token:
                    await websocket.send_json(pair_ok_msg(token))
                else:
                    await websocket.send_json(error_msg("PAIRING_FAILED"))
            elif msg["type"] == "device.hello":
                session.init(msg["device_id"], parse_caps(msg.get("capabilities")))
                if access.connect(session, msg["token"]):
                    await session.send(device_ready_msg(session.capabilities))
                    if CAPABILITY_DISPLAY in session.capabilities:
                        await access.push_snapshot(session.device_id)
                else:
                    await websocket.send_json(error_msg("UNAUTHORIZED"))
                    break
            elif msg["type"] == "message.send":
                ack = access.submit_text(session.device_id, msg["cc_code"], msg["text"])
                await session.send(ack)
            elif msg["type"] == "cc.select":
                access.select_target(session.device_id, msg["cc_code"])
            elif msg["type"] == "audio.start":
                ok = access.begin_audio(session.device_id, msg["recording_id"],
                                         msg["cc_code"], AudioFormat(...))
                if ok:
                    active_recording_id = msg["recording_id"]
                    active_recording_seq = 0
                    await session.send(audio_ready_msg(active_recording_id))
            elif msg["type"] == "audio.end":
                result = access.finish_audio(session.device_id, msg["recording_id"])
                await session.send(transcript_msg(msg["recording_id"], result))
                active_recording_id = None
            elif msg["type"] == "ping":
                await websocket.send_json({"version": 1, "type": "pong"})
    finally:
        if session.device_id:
            access.disconnect(session.device_id)  # 内部自动取消活跃录音
    return websocket


class _WsSession:
    """WebSocket 设备会话——将接入层出站 dict 转为 WS JSON 帧。"""
    def __init__(self, ws: web.WebSocketResponse):
        self._ws = ws
        self._device_id = ""
        self._capabilities = DEFAULT_CAPABILITIES

    def init(self, device_id: str, caps: frozenset[str]):
        self._device_id = device_id
        self._capabilities = caps

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    async def send(self, message: dict) -> None:
        if not self._ws.closed:
            await self._ws.send_json(message)

    async def close(self) -> None:
        await self._ws.close()
```

### 7.3 REST 适配器（未来规范）

一个纯输入设备，无配网无屏幕：

```text
POST /api/send
  Headers: X-Device-Id: rest-001, X-Token: <token>
  Body: {"cc_code": 1, "text": "允许"}

  → access_layer.submit_text("rest-001", 1, "允许")
  → Response: {"ok": true, "text": "允许"}
```

认证方式：请求头携带预配对 token（无配网步骤，token 预置或 API 首次配对）。能力固定 `{"input"}`，不接收任何推送。

### 7.4 CLI 适配器（未来规范）

```text
$ echo '允许' | companion-cli send --cc 1
  → access_layer.submit_text("cli-001", 1, "允许")
  → stdout: {"ok": true}

$ companion-cli select 2
  → access_layer.select_target("cli-001", 2)

$ companion-cli watch        # 如果有 display 能力
  → 订阅状态推送，stdout 实时输出 CC 状态行
```

---

## 8. 协议变更

### 8.1 新增字段

`device.hello` 新增可选 `capabilities` 数组：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `capabilities` | `string[]` | 否 | 设备能力列表，如 `["input"]`、`["input","display","audio"]` |

缺失时默认 `["input", "display"]`，保证现有固件和模拟器不受影响。

### 8.2 `device.ready` 回显

```json
{
  "version": 1,
  "type": "device.ready",
  "capabilities": ["input", "display"]
}
```

### 8.3 新增消息：`cc.select`

新增设备→网关消息，用于显式选择目标 CC：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `cc_code` | `int` | 是 | 目标 CC 编号（1-8） |

```json
{
  "version": 1,
  "type": "cc.select",
  "cc_code": 2
}
```

网关收到后调用 `access_layer.select_target()`。v0.1 仅记录日志，不返回确认消息。

### 8.4 不变的消息

以下消息完全不变：`pair.complete`、`cc.snapshot`、`cc.state`、`message.send`、`message.ack`、`audio.start`、`audio.end`、`transcript.result`、`ping`、`pong`。

### 8.5 `protocol/messages.py` 变更

`decode_client_message` 中 `device.hello` 分支新增 `capabilities` 解析：

```python
caps = payload.get("capabilities")
if caps is not None:
    if not isinstance(caps, list) or not all(
        isinstance(c, str) and c in {"input", "display", "audio", "select"}
        for c in caps
    ):
        raise ProtocolError("Invalid capabilities")
    capabilities = frozenset(caps)
else:
    capabilities = DEFAULT_CAPABILITIES
```

同时新增 `cc.select` 消息解码分支：

```python
if message_type == "cc.select":
    cc_code = payload.get("cc_code")
    if not isinstance(cc_code, int) or not 1 <= cc_code <= MAX_CC_CODE:
        raise ProtocolError("cc_code must be between 1 and 8")
    return {
        "version": PROTOCOL_VERSION,
        "type": "cc.select",
        "cc_code": cc_code,
    }
```

---

## 9. 目录结构

```text
gateway/
  access/                 ← 新增：接入层
    __init__.py
    session.py            ← DeviceSession 协议
    layer.py              ← DeviceAccessLayer 类
    capabilities.py       ← 能力常量 + 默认值
    messages.py           ← state_message / snapshot_message 消息构建
  adapters/
    hooks.py              ← 不变
    http.py               ← 不变
    pairing.py            ← 不变
    realtime_ws.py        ← 重命名（原 realtime.py），瘦身为薄 WS 适配器
    tmux.py               ← 不变
    transcription.py      ← 不变
  domain/                 ← 完全不变
  protocol/
    messages.py           ← 新增 capabilities 字段解析
  app.py                  ← 组合根注入 DeviceAccessLayer
  config.py               ← 不变
  tests/
    test_access_layer.py  ← 新增：接入层纯逻辑测试（不依赖 aiohttp）
    test_realtime_ws.py   ← 更新：WS 适配器测试
    ...（现有测试保持）
```

---

## 10. 状态管理与故障处理

### 10.1 会话生命周期

| 事件 | 接入层行为 |
|---|---|
| 设备认证成功 | 注册 session；有 display → 推送 snapshot |
| 设备断线 | 注销 session；取消该设备的活跃录音 |
| 网关重启 | 所有 session 失效；设备重连后重新认证+推送 snapshot |
| Hook 事件到达 | Registry 更新 → broadcast_state → 仅推给 display 设备 |

### 10.2 多设备并发

接入层的 `_sessions` 字典支持多设备同时在线（如 M5 + Web 模拟器 + CLI）。`broadcast_state` 向所有有 display 能力的设备扇出。无 display 的设备不收到推送，但仍然可以提交指令。

### 10.3 重连恢复

| 场景 | 处理 |
|---|---|
| 设备 WS 断开 → 重连 | 重新 `device.hello` + token 认证；有 display → 推送全量 snapshot |
| token 过期 | 配对码需重新生成；`pair.complete` 重新获取 token |
| 网关重启 | session 全部失效；设备指数退避重连；重连后走完整认证+snapshot |

### 10.4 音频故障

| 场景 | 接入层行为 |
|---|---|
| 录音太短 (<0.5s) | `finish_audio` 返回 `{"ok": false, "error": "..."}` |
| 录音超长 (>15s) | `append_audio` 返回错误，录音自动取消 |
| 分片乱序 | `append_audio` 返回错误 |
| 转写未配置 | `finish_audio` 返回 `{"ok": false, "error": "TRANSCRIPTION_NOT_CONFIGURED"}` |
| 设备断线时有活跃录音 | `disconnect` 时自动 cancel |

### 10.5 注入故障

| 场景 | 接入层行为 |
|---|---|
| cc_code 不存在 | `submit_text` 返回 `TARGET_UNREACHABLE`，不丢弃文本 |
| tmux 会话不在 | 同上 |
| 文本为空 | 返回 `EMPTY_TEXT` |
| 多行文本 | 取首行注入，返回 `MULTILINE_TRUNCATED` 警告 |

---

## 11. 安全设计

| 关注点 | 设计 |
|---|---|
| 配对码 | 6 位数字，10 分钟过期，仅网关控制台显示 |
| Token 存储 | 网关仅存 SHA-256 哈希；原始 token 只返回给设备一次 |
| Token 验证 | HMAC compare_digest 防时序攻击 |
| 设备 ID | MAC 派生或首次启动生成，1-64 字符，不可含前后空格 |
| 文本注入 | 绝不拼 shell；`tmux send-keys -l` 逐字注入 + 仅取首行 |
| Hook 转发 | 非阻塞，网关不可达时静默返回 0，不阻塞 CC |
| 纯输入设备 | REST/CLI 适配器用请求头传 token，不经 WS 配对流程（可选预置 token 模式） |

---

## 12. 改造影响面

| 文件 | 变化类型 | 说明 |
|---|---|---|
| `access/session.py` | 新增 | DeviceSession 协议定义 |
| `access/layer.py` | 新增 | DeviceAccessLayer 核心类 |
| `access/capabilities.py` | 新增 | 能力常量与默认值 |
| `access/messages.py` | 新增 | state_message / snapshot_message 消息构建（从 realtime.py 迁入） |
| `adapters/realtime.py` → `adapters/realtime_ws.py` | 重命名+瘦身 | 145 行单体 → 薄 WS 适配器 |
| `protocol/messages.py` | 小改 | `device.hello` 新增 `capabilities` 可选字段；新增 `cc.select` 消息类型 |
| `app.py` | 小改 | 组合根注入 `DeviceAccessLayer` |
| `adapters/pairing.py` | 不变 | 被接入层组合 |
| `adapters/tmux.py` | 不变 | 被接入层调用 |
| `adapters/transcription.py` | 不变 | 被接入层调用 |
| `domain/*` | 不变 | 业务核心零改动 |
| `config.py` | 不变 | |
| `cc-integration/hook.py` | 不变 | |
| 固件 C++ | 不变 | 协议兼容 |
| `gateway/simulator/` | 不变 | WS 协议不变 |

**核心收益**：Domain 层和 protocol 层完全不动，改动集中在 adapter 层的新增和重构。

---

## 13. 验证策略

### 13.1 接入层单元测试（纯逻辑，不依赖 aiohttp）

| 测试 | 覆盖 |
|---|---|
| `test_pair_and_connect` | 配对 → token → 认证成功/失败 |
| `test_submit_text_ok` | 正常文本注入 → ack ok |
| `test_submit_text_target_unreachable` | cc_code 不存在 → ack with TARGET_UNREACHABLE |
| `test_submit_text_empty` | 空文本 → EMPTY_TEXT |
| `test_submit_text_multiline` | 多行 → 首行注入 + MULTILINE_TRUNCATED |
| `test_display_device_gets_snapshot` | 有 display → 连接后收到 snapshot |
| `test_input_only_device_no_snapshot` | 无 display → 连接后无 snapshot |
| `test_broadcast_state_filters_display` | 增量只推给 display 设备 |
| `test_audio_flow` | begin → append → finish → transcript |
| `test_audio_cancel_on_disconnect` | 断线时自动取消录音 |
| `test_multi_device` | 多设备同时在线，各自独立收发 |

用 fake DeviceSession（记录所有 `send()` 调用）+ fake TmuxInjector + fake RecordingService，不启动任何 HTTP/WS 服务。

### 13.2 WS 适配器集成测试

用 aiohttp TestClient 模拟真实 WS 连接，验证：
- 配对 → 认证 → snapshot → submit → ack 完整链路
- 能力声明影响推送行为
- 断线清理

### 13.3 回归测试

现有 `tests/test_realtime.py`、`tests/test_pairing.py` 等保持通过，确保重构不破坏行为。

### 13.4 模拟器端到端

浏览器模拟器走完整链路验证协议兼容性。

---

## 14. 实施计划

| 步骤 | 内容 | 产出 |
|---|---|---|
| S1 | 创建 `access/` 目录，定义 `DeviceSession` 协议 + 能力常量 | `access/session.py`, `access/capabilities.py` |
| S2 | 实现 `DeviceAccessLayer` + 消息构建（从 `realtime.py` 提取逻辑） | `access/layer.py`, `access/messages.py` |
| S3 | `protocol/messages.py` 新增 `capabilities` 字段解析 + `cc.select` 消息解码 | 协议小改 |
| S4 | 重构 `realtime.py` → `realtime_ws.py`，改为调用接入层 | 薄 WS 适配器 |
| S5 | `app.py` 组合根注入 `DeviceAccessLayer` | 组合根根更新 |
| S6 | 新增 `test_access_layer.py` 纯逻辑测试 | 接入层测试覆盖 |
| S7 | 更新 WS 适配器测试 | 集成测试通过 |
| S8 | 运行全量测试，模拟器端到端验证 | 回归通过 |

每步可独立提交，S1-S3 不影响现有代码运行（接入层存在但未被使用），S4-S5 切换调用方，S6-S8 验证。

---

## 15. 待确认问题

| # | 问题 | 建议 |
|---|---|---|
| 1 | REST/CLI 适配器的 token 预置模式 | 建议支持 API key 预置（不走 WS 配对），首次用 `curl POST /api/pair` 获取 |
| 2 | `cc.select` 是否需要持久化到网关 | v0.1 建议仅日志记录，持久化留给设备自身；v1.1 可加服务端持久化 |
| 3 | 服务端确认流程（`submit_draft` → `confirm_send`）是否需要 | v0.1 不做，确认留给设备；如 REST 设备也需要确认可后续扩展 |
| 4 | 能力协商是否需要版本号（如 `capabilities_v2`） | 不需要，`capabilities` 数组可前向扩展，新能力对旧网关无影响 |
| 5 | 多设备同时向同一 cc_code 提交是否需要排队 | v0.1 不需要，tmux 注入是同步的；如高并发可后续加队列 |

---

## 16. 附录

### 16.1 动作 × 能力矩阵

| 动作 \ 能力 | input | display | audio | select |
|---|---|---|---|---|
| A1 配对认证 | ✅ 必选 | — | — | — |
| A2 提交指令 | ✅ 必选 | — | — | — |
| A3 回执反馈 | ✅ 必选 | — | — | — |
| O1 状态订阅 | — | ✅ 必需 | — | — |
| O2 选择目标 | — | — | — | ✅ 必需 |
| O3 音频输入 | — | — | ✅ 必需 | — |
| O4 保活心跳 | 长连接 | 长连接 | 长连接 | 长连接 |

### 16.2 设备类型 × 能力示例

| 设备类型 | capabilities | 支持的动作 |
|---|---|---|
| M5StickC S3 | `input, display, audio, select` | A1-A3 + O1-O4 全部 |
| Web 模拟器 | `input, display, select` | A1-A3 + O1, O2, O4 |
| REST 端点 | `input` | A1-A3 仅必选 |
| CLI 工具 | `input` 或 `input, display` | A1-A3；可选 O1 |

### 16.3 相关文件索引

- PRD：`PRD_claude-code-companion.md`
- 模块设计：`docs/2026-07-26-modular-design.md`
- MVP TODO：`docs/plans/2026-07-26-companion-mvp-todo.md`
- 当前网关入口：`cc-companion/gateway/app.py`
- 当前 WS handler：`cc-companion/gateway/adapters/realtime.py`
- 配对服务：`cc-companion/gateway/adapters/pairing.py`
- tmux 注入器：`cc-companion/gateway/adapters/tmux.py`
- 协议编解码：`cc-companion/gateway/protocol/messages.py`
