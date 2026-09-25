# Gravity Pomodoro Cube (M5StickS3)

翻转重力番茄钟 — 用物理姿态控制的桌面专注计时器。

## 玩法

| 物理姿态 | 触发动作 |
---|---|
| 立着放（竖直立起） | 自动开启 25 分钟专注计时 |
| 横躺（屏幕朝上） | 自动开启 5 分钟休息倒计时 |
| 正面朝下扣住 | 暂停/结束（屏幕自动关闭省电） |
| 按下 A 键 | 手动开启专注模式 |
| 按下 B 键 | 手动开启休息模式 |

## 硬件要求

- [M5StickS3](https://docs.m5stack.com/en/core/StickS3) (K150)
- USB-C 数据线

## 烧录

```bash
# 安装 PlatformIO Core
pip install platformio

# 编译并烧录
pio run -t upload

# 查看串口输出（调试用）
pio device monitor
```

### 首次进入下载模式

StickS3 没有 GPIO-0 按键。如果烧录失败：

1. 插入 USB 线
2. **长按侧面电源键**直到绿色 LED 闪烁（约 3-5 秒）
3. 再执行 `pio run -t upload`

## 项目结构

```
src/
  main.cpp          — 主循环、电源管理、事件分发
  config.h          — 可调常量（时长、阈值、亮度等）
  orientation.h     — BMI270 姿态识别 + 防抖
  timer_logic.h     — 番茄钟状态机（IDLE→FOCUS→BREAK→PAUSED）
  ui.h              — 135×240 屏幕渲染（倒计时、进度条、统计）
  audio.h           — 非阻塞提示音序列器（ES8311 喇叭）
  stats.h           — NVS 持久化统计（番茄数、累计专注分钟）
```

## 状态机

```
IDLE ─(竖直立起)─→ FOCUS RUNNING ─(计时结束)─→ FOCUS DONE ─(横躺)─→ BREAK RUNNING
  │                     │                                              │
  │                (正面朝下)                                          │
  │                     ↓                                              ↓
  │               FOCUS PAUSED ←(竖直立起)→ FOCUS RUNNING        BREAK DONE
  │                     │                                    │
  │                (正面朝下)                                (竖直立起)
  │                     ↓                                    ↓
  └──────────────── IDLE ←─────────────────────────────────── FOCUS RUNNING
```

## Roadmap

- [x] 姿态识别 + 防抖
- [x] 番茄钟状态机
- [x] 屏幕渲染（倒计时、进度条、统计）
- [x] 提示音（完成时播放）
- [x] NVS 统计持久化
- [ ] WiFi 配网（BLE Provisioning 或 SmartConfig）
- [ ] 飞书多维表格同步
- [ ] Notion 同步
- [ ] Toggl 同步
- [ ] 每日自动重置（NTP 对时）

## License

MIT
