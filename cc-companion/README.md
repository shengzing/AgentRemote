# Claude Code Companion

## 网关（M1）

当前网关通过 `POST /hook` 接收本机 Claude Code Hook 事件，为每个活动 `session_id` 分配稳定的 `#1` 至 `#8` 编号，并通过 `GET /ws` 提供已认证的 v1 WebSocket 服务。网关内部使用设备接入层（`access/`）统一管理配对认证和设备动作，适配器层仅做传输格式转换。

### 设备接入层

网关的 `access/` 模块是所有设备（M5、Web 模拟器、HTML 语音终端、未来 REST/CLI）的统一接入点：

- **必选动作**：配对认证、提交指令、回执反馈
- **可选动作**：状态订阅（仅 display 设备）、目标选择、音频输入
- 设备在 `device.hello` 中声明 `capabilities`，接入层按能力过滤推送
- 纯输入设备（如 REST 端点）声明 `["input"]` 即可，不接收状态推送

设备使用网关启动时显示的六位配对码完成配对，随后接收完整状态快照和状态增量；确认后的文本可以发送到对应的 tmux 目标。

M5 的 Wi-Fi/WebSocket 硬件适配和真实语音采集仍待实现。当前可先用浏览器模拟器复用同一套 Gateway 协议，不需要烧录或操作实体设备。

创建虚拟环境并安装 Gateway 依赖：

```sh
cd cc-companion/gateway
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

运行单元测试：

```sh
cd cc-companion/gateway
.venv/bin/python -m unittest discover -s tests -v
```

在本机启动 Gateway：

```sh
cd cc-companion/gateway
CC_COMPANION_TMUX_TARGETS='1=cc1,2=cc2' .venv/bin/python app.py
```

Hook 默认地址为 `http://127.0.0.1:7421/hook`。将 `cc-integration/settings.example.json` 的内容复制到适用的 Claude Code 设置范围中，把 `/absolute/path/to` 替换为本项目的绝对路径；Hook 转发脚本无需修改。即使 Gateway 暂时不可用，它也会向 Claude Code 返回成功，避免阻塞 Claude Code 工作流。

不启动 Claude Code 也可以用以下命令验证 Hook：

```sh
curl -sS -X POST http://127.0.0.1:7421/hook \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","hook_event_name":"Notification","message":"Waiting for your permission"}'
```

预期得到一个 HTTP `202` 的 JSON 响应，其中包含 `accepted: true`、`cc_code: 1` 与 `AWAITING_CONFIRMATION`。

正常使用时，请将 `CC_COMPANION_PAIRING_STORE` 设置为仓库外的文件路径。Gateway 仅在该文件中保存已配对设备 token 的哈希值；生成的配对码和原始 token 都不会写入该文件。

## 电脑端模拟器（无需烧录）

按上述方式启动 Gateway 后，打开 `http://127.0.0.1:7421/simulator`。首次连接时输入 Gateway 终端显示的六位配对码；后续连接会复用浏览器为该设备 ID 保存的本地 token，无需再次填写配对码。

模拟器会接收与实体设备相同的快照和状态增量。按上方示例提交 Hook 后，屏幕会出现一个 CC 状态行；使用**短按**（或键盘 `J`）选择 CC 目标，使用**长按**（或 `R`）打开“模拟转写”输入框。发送文本会走正式的 `message.send` 与 tmux 注入路径。

因此可以在不接触实体设备、麦克风或固件的前提下，完成以下完整验证：

```text
Claude Code Hook -> Gateway -> 浏览器模拟器 -> tmux 目标
```

## 输入终端（HTML 版）

启动 Gateway 后打开 `http://127.0.0.1:7421/terminal`。这是基于浏览器的输入终端，操作流程：

1. 点击 **唤醒** 按钮连接 Gateway
2. 首次使用输入网关终端显示的六位配对码
3. 点击 **数字键** 选择对应的 Claude Code 终端
4. 在输入框中输入指令
5. 点击 **发送** 或按 `Command/Ctrl + Enter`
6. 文本会注入到选中的 CC tmux 会话

当前版本使用打字输入替代语音输入，便于稳定验证完整链路；后续会恢复可选语音输入。
