# 设备接入层实施 TODO

基于 [Device Access Layer Design](../2026-09-24-device-access-layer-design.md)，按步骤逐项实施。

## S1：定义 DeviceSession 协议 + 能力常量

- [ ] 创建 `cc-companion/gateway/access/__init__.py`
- [ ] 创建 `cc-companion/gateway/access/session.py`，定义 `DeviceSession` Protocol：
  - `device_id` property（`str`）
  - `capabilities` property（`frozenset[str]`）
  - `async send(message: dict) -> None`
  - `async close() -> None`
- [ ] 创建 `cc-companion/gateway/access/capabilities.py`：
  - `CAPABILITY_INPUT = "input"`
  - `CAPABILITY_DISPLAY = "display"`
  - `CAPABILITY_AUDIO = "audio"`
  - `CAPABILITY_SELECT = "select"`
  - `DEFAULT_CAPABILITIES = frozenset({CAPABILITY_INPUT, CAPABILITY_DISPLAY})`
- [ ] 验证：`python -c "from access.session import DeviceSession; from access.capabilities import DEFAULT_CAPABILITIES"` 无报错

**产出**：`access/__init__.py`、`access/session.py`、`access/capabilities.py`

## S2：实现 DeviceAccessLayer + 消息构建

- [ ] 创建 `cc-companion/gateway/access/messages.py`：
  - `state_message(session, revision) -> dict`（从 `realtime.py` 迁入）
  - `snapshot_message(snapshot) -> dict`（从 `realtime.py` 迁入）
  - `_session_payload(session) -> dict`（从 `realtime.py` 迁入）
- [ ] 创建 `cc-companion/gateway/access/layer.py`，实现 `DeviceAccessLayer`：
  - `__init__(pairing, registry, tmux, recording)`
  - `pair(device_id, code) -> Optional[str]`
  - `connect(session, token) -> bool`（仅认证+注册，不推快照）
  - `disconnect(device_id)`（自动取消该设备活跃录音）
  - `is_online(device_id) -> bool`
  - `select_target(device_id, cc_code)`
  - `submit_text(device_id, cc_code, text) -> dict`（返回 ack，不推送）
  - `begin_audio(device_id, recording_id, cc_code, fmt) -> bool`
  - `append_audio(device_id, recording_id, seq, pcm) -> Optional[str]`
  - `finish_audio(device_id, recording_id) -> dict`
  - `cancel_audio(device_id, recording_id)`
  - `broadcast_state(session, revision)`（async，仅推 display 设备）
  - `push_snapshot(device_id)`（async，仅推 display 设备）
  - `send_error(device_id, code)`（async）
  - 内部 `_sessions: dict[str, DeviceSession]`
  - 内部 `_active_recordings: dict[str, str]`（device_id → recording_id）
- [ ] 验证：接入层可被实例化，不依赖 aiohttp

**产出**：`access/messages.py`、`access/layer.py`

## S3：协议新增 capabilities + cc.select

- [ ] 修改 `cc-companion/gateway/protocol/messages.py`：
  - `device.hello` 分支新增 `capabilities` 可选字段解析
  - 校验值必须为 `input` / `display` / `audio` / `select` 的列表
  - 缺失时返回 `DEFAULT_CAPABILITIES`
  - 新增 `cc.select` 消息类型解码（校验 `cc_code` 1-8）
- [ ] 更新 `cc-companion/gateway/tests/test_protocol.py`：
  - 测试 `device.hello` 带 `capabilities` 字段
  - 测试 `device.hello` 不带 `capabilities`（默认值）
  - 测试非法 `capabilities` 值被拒绝
  - 测试 `cc.select` 有效消息
  - 测试 `cc.select` 无效 cc_code 被拒绝
- [ ] 运行：`cd cc-companion/gateway && .venv/bin/python -m unittest tests.test_protocol -v`

**产出**：`protocol/messages.py` 更新、`tests/test_protocol.py` 更新

## S4：重构 realtime.py → realtime_ws.py

- [ ] 将 `cc-companion/gateway/adapters/realtime.py` 重命名为 `realtime_ws.py`
- [ ] 删除 `WebSocketHub` 类（由 `DeviceAccessLayer._sessions` + `_fan_out` 替代）
- [ ] 重写 `websocket_handler` 为薄 WS 适配器：
  - 创建 `_WsSession` 类（实现 `DeviceSession` 协议）
  - `pair.complete` → `access.pair()`
  - `device.hello` → `session.init()` + `access.connect()` + 可选 `access.push_snapshot()`
  - `message.send` → `access.submit_text()` + `session.send(ack)`
  - `cc.select` → `access.select_target()`
  - `audio.start` → `access.begin_audio()`
  - 二进制帧 → `access.append_audio()` + 序号跟踪
  - `audio.end` → `access.finish_audio()` + `session.send(transcript)`
  - `ping` → 直接回复 `pong`
  - finally → `access.disconnect()`（内部自动取消录音）
- [ ] 删除 `state_message`、`_snapshot_message`、`_session_payload`（已迁至 `access/messages.py`）
- [ ] 更新 `configure_routes` 保持路由 `/ws` 不变
- [ ] 验证：`cd cc-companion/gateway && .venv/bin/python -m unittest discover -s tests -v` 全部通过

**产出**：`adapters/realtime_ws.py`（原 `realtime.py` 删除）

## S5：组合根注入 DeviceAccessLayer

- [ ] 修改 `cc-companion/gateway/app.py`：
  - 新增 `ACCESS_LAYER_KEY = web.AppKey("access_layer", DeviceAccessLayer)`
  - 在 `create_app()` 中构造 `DeviceAccessLayer(pairing_service, registry, tmux_injector, recording_service)`
  - 将 `DeviceAccessLayer` 注入 app
  - Hook 的 `on_session_updated` 回调改为调用 `access.broadcast_state()`
  - 移除对旧 `WebSocketHub`、`PAIRING_SERVICE_KEY`、`TMUX_INJECTOR_KEY`、`RECORDING_SERVICE_KEY` 的直接注入（保留 `HOOK_SERVICE_KEY`）
- [ ] 验证：`cd cc-companion/gateway && .venv/bin/python -c "from app import create_app; app = create_app(); print('ok')"`

**产出**：`app.py` 更新

## S6：新增接入层单元测试

- [ ] 创建 `cc-companion/gateway/tests/test_access_layer.py`，用 fake 对象（不依赖 aiohttp）：
  - `FakeDeviceSession`：记录所有 `send()` 调用
  - `FakeTmuxInjector`：可配置注入结果
  - `FakeRecordingService`：可配置转写结果
- [ ] 编写测试用例：
  - `test_pair_and_connect_success`
  - `test_pair_and_connect_wrong_token`
  - `test_submit_text_ok`
  - `test_submit_text_target_unreachable`
  - `test_submit_text_empty`
  - `test_submit_text_multiline_truncated`
  - `test_display_device_gets_snapshot`
  - `test_input_only_device_no_snapshot`
  - `test_broadcast_state_filters_display`
  - `test_begin_append_finish_audio`
  - `test_audio_cancel_on_disconnect`
  - `test_audio_wrong_device_rejected`
  - `test_multi_device_concurrent`
- [ ] 运行：`cd cc-companion/gateway && .venv/bin/python -m unittest tests.test_access_layer -v`

**产出**：`tests/test_access_layer.py`

## S7：更新 WS 适配器集成测试

- [ ] 重命名 `tests/test_realtime.py` → `tests/test_realtime_ws.py`（如适用）
- [ ] 更新现有测试使用新的 `ACCESS_LAYER_KEY`
- [ ] 新增测试：
  - `test_device_hello_with_capabilities`
  - `test_device_hello_without_capabilities_defaults`
  - `test_input_only_device_receives_no_snapshot`
  - `test_display_device_receives_snapshot`
  - `test_cc_select_message`
- [ ] 运行：`cd cc-companion/gateway && .venv/bin/python -m unittest tests.test_realtime_ws -v`

**产出**：`tests/test_realtime_ws.py`

## S8：全量回归 + 模拟器验证

- [ ] 运行全量单元测试：`cd cc-companion/gateway && .venv/bin/python -m unittest discover -s tests -v`
- [ ] 启动网关：`cd cc-companion/gateway && CC_COMPANION_TMUX_TARGETS='1=cc1' .venv/bin/python app.py`
- [ ] 用 curl 模拟 Hook：`curl -sS -X POST http://127.0.0.1:7421/hook -H 'Content-Type: application/json' -d '{"session_id":"test-1","hook_event_name":"Notification","message":"Permission needed"}'`
- [ ] 打开 `http://127.0.0.1:7421/simulator`，验证：
  - 配对码连接成功
  - 收到 snapshot（模拟器有 display 能力）
  - 状态列表正确显示
  - 发送文本走 `message.send` → `message.ack` 路径
- [ ] 验证无 `capabilities` 字段的连接（向后兼容）：模拟器不传 capabilities 应默认有 display
- [ ] 更新 `cc-companion/README.md` 如有接口变化

**产出**：全量测试通过 + 模拟器端到端验证通过

---

## 依赖关系

```text
S1 ──► S2 ──► S3 ──► S4 ──► S5 ──► S6 ──► S7 ──► S8
      │                    │
      └── S2 不依赖 S3 ────┘  （可并行）
```

S1 → S2 是顺序依赖（接入层需要 session 协议）。S3（协议改动）可与 S2 并行。S4 依赖 S2+S3。S5 依赖 S4。S6 依赖 S2（可提前写）。S7 依赖 S4+S5。S8 是最终验收。

## 风险提示

| 风险 | 缓解 |
|---|---|
| S4 重构范围较大，可能破坏现有 WS 行为 | 先跑现有 `test_realtime.py` 确认基线；重构后逐个恢复 |
| `app.py` 组合根改动可能影响 hook 推送路径 | S5 单独提交，验证 Hook → broadcast 链路 |
| 模拟器可能依赖旧协议细节 | S8 用模拟器做端到端回归 |
