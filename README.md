# CC Companion

CC Companion 是一个本地 Claude Code 多实例控制系统。它通过 Claude Code Hooks 采集各个 Claude Code 会话状态，在本地网关中统一编号，然后把状态推送到浏览器终端或未来的 M5StickC S3 设备；用户也可以在终端上选择目标会话，用语音生成文本并注入到对应的 tmux 会话。

## 项目结构

```text
PRD_claude-code-companion.md       产品需求与验收标准
cc-companion/                      Claude Code Companion 主项目
  gateway/                         Python 本地网关
  firmware/                        硬件无关 C++ 固件核心
  cc-integration/                  Claude Code Hook 转发脚本
docs/                              产品、架构、模块与实施文档
gravity-pomodoro-cube/             独立的 M5StickS3 番茄钟项目
```

## 核心链路

```text
Claude Code Hooks
      |
      | HTTP POST /hook
      v
Gateway
  |- SessionRegistry: session_id -> cc_code (#1-#8)
  |- DeviceAccessLayer: 配对、认证、设备能力、动作分发
  |- tmux adapter: 安全注入文本
      |
      | WebSocket /ws
      +--> HTML 输入终端 /terminal
      +--> 浏览器模拟器 /simulator
      +--> M5StickC S3（规划中）
```

当前 MVP 已完成：

- Hook 事件接收、状态归一化和 `#1` 至 `#8` 稳定编号
- 六位配对码配对、token 哈希存储和 WebSocket 认证
- 设备能力声明，纯输入设备可不接收状态快照
- 多设备会话管理和按 `display` 能力过滤状态推送
- HTML 输入终端：唤醒、选择终端、打字输入、确认发送
- tmux 安全注入：参数数组调用、literal mode、仅注入首行
- 接入层、协议、domain、tmux、配对等 50 个单元测试

尚未完成：

- M5StickC S3 的 Wi-Fi/WebSocket、屏幕、按键、麦克风硬件适配
- 真实语音音频上行和 Whisper 转写适配
- 固件烧录与硬件端到端验证
- REST/CLI 适配器、公网穿透、OTA 和省电策略

## 快速开始

### 1. 准备环境

```sh
cd cc-companion/gateway
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

> 当前仓库实际已有的虚拟环境在 `cc-companion/.venv`。如果没有在 `gateway/` 下新建环境，可用：
>
> ```sh
> cd cc-companion/gateway
> ../.venv/bin/python -m unittest discover -s tests -v
> ```

### 2. 启动 tmux 会话

网关按 `cc_code -> tmux session` 的映射注入文本。示例：

```sh
tmux new -s cc1 'claude'
tmux new -s cc2 'claude'
```

启动网关时指定映射：

```sh
CC_COMPANION_TMUX_TARGETS='1=cc1,2=cc2' .venv/bin/python app.py
```

网关默认监听 `http://127.0.0.1:7421`，并在终端输出六位配对码。

### 3. 接入 Claude Code Hooks

将 [settings.example.json](cc-companion/cc-integration/settings.example.json) 中的 Hook 配置复制到你的 Claude Code 设置里，并把 `/absolute/path/to` 替换为项目绝对路径。

Hook 脚本默认发送到：

```text
http://127.0.0.1:7421/hook
```

网关不可用时 Hook 会静默返回成功，不会阻塞 Claude Code。

### 4. 使用 HTML 输入终端

打开：

```text
http://127.0.0.1:7421/terminal
```

操作流程：

1. 点击 **唤醒** 连接网关
2. 首次使用输入网关终端显示的六位配对码
3. 点击数字键选择目标 Claude Code 终端
4. 在输入框中输入指令
5. 点击发送或按 `Command/Ctrl + Enter`
6. 文本会注入选中的 tmux 会话

当前 HTML 终端使用打字输入，后续会在这个流程上恢复可选语音输入。

### 5. 验证 Hook 链路

```sh
curl -sS -X POST http://127.0.0.1:7421/hook \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","hook_event_name":"Notification","message":"Waiting for your permission"}'
```

预期返回：

```json
{"accepted": true, "cc_code": 1, "state": "AWAITING_CONFIRMATION", "revision": 1}
```

## 网关配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `CC_COMPANION_HOST` | `127.0.0.1` | HTTP/WebSocket 监听地址 |
| `CC_COMPANION_PORT` | `7421` | HTTP/WebSocket 监听端口 |
| `CC_COMPANION_MAX_SESSIONS` | `8` | 最多同时跟踪的 Claude Code 会话数 |
| `CC_COMPANION_SESSION_EXPIRY` | `1800` | 会话无事件后的过期秒数 |
| `CC_COMPANION_TMUX_TARGETS` | 空 | `cc_code=tmux_session` 映射，如 `1=cc1,2=cc2` |
| `CC_COMPANION_PAIRING_STORE` | `.cc-companion-pairings.json` | 设备 token 哈希存储路径 |
| `CC_COMPANION_PAIRING_CODE` | 随机生成 | 固定六位配对码，便于测试 |

生产使用建议把 `CC_COMPANION_PAIRING_STORE` 放在仓库外。网关只保存 token 哈希，不保存原始 token。

## 测试

网关单元测试：

```sh
cd cc-companion/gateway
.venv/bin/python -m unittest discover -s tests -v
```

固件核心测试：

```sh
cd cc-companion/firmware
make test
```

当前网关纯逻辑测试 50 个用例全部通过。部分 `test_realtime` / `test_http` 集成测试需要绑定本地端口；在受限沙箱中可能因 `Operation not permitted` 失败，在普通终端运行即可。

## 设备接入层

`gateway/access/` 是所有设备接入的统一兼容层：

| 动作 | 必选 | 说明 |
|---|---|---|
| 配对认证 | 是 | 配对码换 token，后续连接用 token 认证 |
| 提交指令 | 是 | 设备选择 `cc_code` 并提交文本 |
| 回执反馈 | 是 | 返回 tmux 注入结果和失败原因 |
| 状态订阅 | 否 | 仅 `display` 能力设备接收快照/增量 |
| 目标选择 | 否 | 设备显式发送当前目标 |
| 音频输入 | 否 | 预留给麦克风设备 |
| 心跳保活 | 否 | 长连接设备使用 |

设备能力：

```text
input    可提交指令，必选
display  可接收状态推送
audio    可上传音频
select   可显式选择目标
```

设计细节见 [Device Access Layer Design](docs/2026-09-24-device-access-layer-design.md)。

## 安全边界

- 配对码 6 位、10 分钟过期，只在网关控制台显示
- 网关仅保存 token 的 SHA-256 哈希
- token 校验使用 `hmac.compare_digest`
- Hook 转发失败不影响 Claude Code 运行
- tmux 注入使用参数数组和 `send-keys -l`，不拼接 shell
- 多行文本只注入首行，并返回 `MULTILINE_TRUNCATED` 警告

## 故障排查

- **`TARGET_UNREACHABLE`**：目标 `cc_code` 没有活跃 Hook 会话，或对应的 tmux session 不存在。先发送一条 Hook 事件，再确认 `CC_COMPANION_TMUX_TARGETS` 与 `tmux ls` 中的 session 名一致。
- **`PAIRING_FAILED`**：配对码错误或已超过 10 分钟有效期。重启网关或设置 `CC_COMPANION_PAIRING_CODE` 后重新配对。
- **页面无法连接**：确认网关已启动，并访问 `http://127.0.0.1:7421/health`。
- **发送按钮不可用**：输入内容为空。填写至少一个非空字符后再发送。
- **测试绑定端口失败**：普通终端重跑；受限沙箱可能禁止本地端口绑定。

## 文档

- [产品需求 PRD](PRD_claude-code-companion.md)
- [模块化设计](docs/2026-07-26-modular-design.md)
- [设备接入层设计](docs/2026-09-24-device-access-layer-design.md)
- [设备接入层实施 TODO](docs/plans/2026-09-24-device-access-layer-todo.md)
- [Gateway 使用说明](cc-companion/README.md)
- [固件核心说明](cc-companion/firmware/README.md)
