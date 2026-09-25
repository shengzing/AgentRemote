# M5StickS3 烧录过程记录

**日期**: 2026-09-15  
**项目**: Gravity Pomodoro Cube  
**固件版本**: v0.1.0  
**目标硬件**: M5StickS3 (K150)  
**芯片**: ESP32-S3-PICO-1 (revision v0.2)  
**MAC 地址**: 70:04:1D:D5:D4:E4  
**结果**: 烧录成功，校验通过，设备已重启运行

---

## 1. 烧录前状态

| 项目 | 状态 |
|---|---|
| 出厂固件版本 | v2.4.5 |
| 设备首次烧录 | 是（覆盖出厂固件） |
| USB 连接 | `/dev/cu.usbmodem101` |
| 开发环境 | PlatformIO 6.2.0 |
| 编译产物 | `.pio/build/m5sticks3/firmware.bin` |

### 固件编译结果

```
RAM:   6.9%  (22,640 bytes / 327,680 bytes)
Flash: 14.7% (490,505 bytes / 3,342,336 bytes)
```

---

## 2. 环境搭建

### 2.1 安装 PlatformIO

```bash
# macOS 系统 Python 3.9
pip3 install --user platformio

# 可执行文件路径（未加入 PATH 时需使用完整路径）
/Users/jiachengbin/Library/Python/3.9/bin/pio
```

### 2.2 首次编译下载工具链

首次运行 `pio run` 时，PlatformIO 自动下载以下组件：

| 组件 | 版本 |
|---|---|
| toolchain-xtensa-esp32s3 | 8.4.0+2021r2-patch5 |
| toolchain-riscv32-esp | 8.4.0+2021r2-patch5 |
| framework-arduinoespressif32 | 4.20017.260907 |
| tool-esptoolpy | 2.41100.260907 |
| M5Unified 库 | 0.2.22 |
| M5GFX 库 | >=0.2.29 |

**注意事项**：

- 磁盘空间需求约 3-5 GB（含缓存）
- 首次下载耗时 5-10 分钟（取决于网速）
- 后续编译无需重新下载

### 2.3 编译命令

```bash
cd /Users/jiachengbin/workspace/ss_claude/gravity-pomodoro-cube
pio run
```

编译产物：

- ELF 文件: `.pio/build/m5sticks3/firmware.elf`（调试用）
- BIN 文件: `.pio/build/m5sticks3/firmware.bin`（烧录用）

---

## 3. 烧录操作流程

### 3.1 连接硬件

1. 使用支持**数据传输**的 USB-C 线连接 M5StickS3 到 Mac
2. 确认 Mac 识别到串口设备：

```bash
ls /dev/cu.usbmodem*
# 应输出: /dev/cu.usbmodem101
```

### 3.2 进入下载模式（关键步骤）

M5StickS3 使用 ESP32-S3 原生 USB，没有 USB 转串口芯片。软件 DTR/RTS 复位无法触发下载模式，必须使用物理按键。

#### 方法 A：按键组合进入

1. 保持 USB 线连接 Mac
2. **按住正面大按键 BtnA 不放**
3. 按住 BtnA 的同时，**短按一下左侧电源键**（不超过 0.5 秒）
4. **继续按住 BtnA 等 1 秒**
5. **松开 BtnA**

#### 方法 B：长按电源键（本次成功使用的方法）

1. 保持 USB 线连接 Mac
2. **长按左侧电源键 5-6 秒**（不要松手）
3. 等待**绿灯开始闪烁**（不是常亮）
4. 松开电源键
5. 屏幕完全熄灭

**成功标志**：

- 屏幕完全黑（无任何显示内容）
- 绿灯**闪烁**（不是常亮）
- Mac 能稳定识别到 `/dev/cu.usbmodem101`

**失败标志**：

- 绿灯常亮 = 设备正常运行
- 屏幕显示任何内容（如 v2.4.5）= 正常启动，不在下载模式
- 串口反复出现消失 = USB CDC 不稳定

### 3.3 执行烧录

设备成功进入下载模式后，执行：

```bash
/Users/jiachengbin/Library/Python/3.9/bin/pio run -t upload --upload-port /dev/cu.usbmodem101
```

---

## 4. 烧录详细日志

### 4.1 设备识别信息

```
Chip is ESP32-S3-PICO-1 (LGA56) (revision v0.2)
Features: WiFi, BLE, Embedded Flash 8MB (GD), Embedded PSRAM 8MB (AP_3v3)
Crystal is 40MHz
USB mode: USB-Serial/JTAG
MAC: 70:04:1d:d5:d4:e4
```

### 4.2 烧录分区和地址

| 分区 | Flash 地址 | 压缩后大小 | 说明 |
|---|---|---|---|
| Bootloader | 0x00000000 | 10,430 bytes | 引导加载程序 |
| Partition Table | 0x00008000 | 146 bytes | 分区表 |
| OTA Data | 0x0000E000 | 47 bytes | OTA 配置 |
| Application | 0x00010000 | 284,261 bytes | 主固件 |

### 4.3 烧录速度

| 分区 | 有效速度 |
|---|---|
| Bootloader | 468.3 kbit/s |
| Partition Table | 403.0 kbit/s |
| OTA Data | 682.0 kbit/s |
| Application | 1184.9 kbit/s |

**总耗时**: 11.38 秒

### 4.4 校验结果

```
Writing at 0x00000000... (100 %) -> Hash of data verified. PASS
Writing at 0x00008000... (100 %) -> Hash of data verified. PASS
Writing at 0x0000E000... (100 %) -> Hash of data verified. PASS
Writing at 0x00010000... (100 %) -> Hash of data verified. PASS

Leaving...
Hard resetting via RTS pin...
```

所有分区写入后均通过 SHA 校验。烧录完成后通过 RTS 引脚触发硬复位，设备自动重启进入新固件。

---

## 5. 遇到的问题和解决方案

### 5.1 磁盘空间不足（已解决）

**问题**: 首次尝试编译时磁盘剩余仅 283 MB，PlatformIO 工具链下载到 72% 时触发 `No space left on device`。

**解决**: 用户清理磁盘后恢复到 6.7 GB 可用，重新编译成功。

**教训**: ESP32-S3 开发环境需要预留至少 5 GB 磁盘空间。

### 5.2 USB CDC 串口无法配置（已解决）

**问题**: 设备未进入下载模式时，esptool 报错：

```
A serial exception error occurred: Could not configure port: (6, 'Device not configured')
```

**原因**:

- M5StickS3 使用 ESP32-S3 原生 USB（USB CDC），不是传统 USB 转串口芯片
- 正常运行模式下，应用固件占用 USB CDC 接口
- esptool 的 DTR/RTS 软件复位对原生 USB 无效
- 设备必须通过物理按键进入 ROM Bootloader 才能烧录

**尝试过但失败的方法**：

| 方法 | 结果 |
|---|---|
| `--before default_reset` | 串口断开，报 errno 6 |
| `--before no_reset` | 串口稳定但设备不在 bootloader，无响应 |
| `--before usb_reset` | 同上 |
| Python 手动 DTR/RTS 序列 | 无效，原生 USB 不支持 |
| Python 预热串口再烧录 | 串口能打开但 esptool flush 时断开 |

**有效解决方法**:

使用**方法 B（长按电源键 5-6 秒）**进入 ROM 下载模式。此时 USB 枚举为 `USB-Serial/JTAG` 模式，esptool 可以直接通信和烧录。

### 5.3 设备反复断连（已解决）

**问题**: 在未进入下载模式时，`/dev/cu.usbmodem101` 反复出现和消失。

**原因**: 设备正常运行时，出厂固件的 USB CDC 实现不稳定，或系统驱动与应用竞争串口。

**解决**: 进入 ROM 下载模式后，USB 连接稳定，烧录顺利完成。

---

## 6. 成功烧录的关键条件

1. **USB-C 线必须支持数据传输**（纯充电线无法通信）
2. **设备必须进入 ROM 下载模式**（长按电源键 5-6 秒，绿灯闪烁）
3. **屏幕完全熄灭**是进入下载模式的视觉判定标准
4. **绿灯闪烁**（非常亮）是成功进入下载模式的 LED 指示
5. 下载模式下 Mac 能稳定识别 `/dev/cu.usbmodem101`

---

## 7. 烧录后验证

### 7.1 启动画面

烧录成功后，设备自动重启，应显示：

```
   Pomodoro
     Cube
    v0.1.0
```

1.5 秒后自动进入 READY 状态。

### 7.2 功能验证清单

| # | 测试项 | 操作 | 预期结果 | 状态 |
|---|---|---|---|---|
| 1 | 开机启动 | 烧录完成后等待重启 | 显示 "Pomodoro Cube v0.1.0" 后进入 READY | 待验证 |
| 2 | 竖立姿态识别 | 竖直放置设备，保持 1.5 秒 | 屏幕变橙色，显示 "FOCUS 25:00" | 待验证 |
| 3 | 平放姿态识别 | 屏幕朝上平放，保持 1.5 秒 | 切换到绿色，显示 "BREAK 05:00" | 待验证 |
| 4 | 翻面暂停 | 屏幕朝下扣住，保持 1.5 秒 | 屏幕熄灭 | 待验证 |
| 5 | 恢复计时 | 从朝下状态恢复竖立 | 从剩余时间继续倒计时 | 待验证 |
| 6 | 按键 A | 短按正面大键 | 手动开始 25 分钟专注 | 待验证 |
| 7 | 按键 B | 短按右侧键 | 手动开始 5 分钟休息 | 待验证 |
| 8 | 姿态防抖 | 拿起设备查看屏幕 | 不触发模式切换（需 1.5 秒稳定） | 待验证 |
| 9 | 屏幕方向 | 查看文字是否正立 | USB 朝下时文字正立 | 待验证 |
| 10 | 提示音 | 等待计时完成 | 播放 C-E-G 三音提示 | 待验证 |

### 7.3 已知风险点

| 风险 | 影响 | 验证方法 | 修复方案 |
|---|---|---|---|
| BMI270 轴向映射 | 姿态识别可能不正确 | 竖立设备看是否显示 UPRIGHT | 修改 `orientation.h` 中 `classify()` 的轴映射 |
| ES8311 音频兼容 | `Speaker.tone()` 可能无声 | 等计时完成听是否有提示音 | 换用 `M5.Speaker.begin()` + `rawWave()` |
| `setBrightness(0)` 有效性 | 屏幕可能无法真正关背光 | 翻面后看是否全黑 | 换用 `M5.Lcd.sleep()` + PMIC 控制 |
| `setRotation(0)` 方向 | 文字可能倒置 | 开机看启动画面方向 | 调整 `setRotation()` 值 |

---

## 8. 恢复出厂固件

如需恢复 M5StickS3 出厂固件：

```bash
# 方法 1: 使用 M5Burner（推荐）
# 下载地址: https://docs.m5stack.com/en/download
# 选择 StickS3 -> 出厂固件 -> Burn

# 方法 2: 使用 esptool 命令行（需要出厂固件 bin 文件）
python3 esptool.py --chip esp32s3 --port /dev/cu.usbmodem101 \
    --baud 921600 write_flash 0x0 factory_firmware.bin
```

---

## 9. 项目文件结构

```
gravity-pomodoro-cube/
├── platformio.ini              # PlatformIO 构建配置
├── README.md                   # 项目说明
├── docs/
│   └── FLASH_LOG.md            # 本文档：烧录记录
├── .pio/
│   └── build/m5sticks3/
│       ├── firmware.elf        # 调试用 ELF 文件
│       └── firmware.bin        # 烧录用 BIN 文件
└── src/
    ├── main.cpp                # 主循环、事件分发、电源管理（183 行）
    ├── config.h                # 可调常量（时长、阈值、亮度等）
    ├── orientation.h           # BMI270 姿态识别 + 1.5 秒防抖
    ├── timer_logic.h           # 番茄钟状态机
    ├── ui.h                    # 135x240 屏幕渲染
    ├── audio.h                 # 非阻塞提示音序列器
    └── stats.h                 # NVS 持久化统计
```

---

## 10. 快速烧录命令备忘

```bash
# 进入项目目录
cd /Users/jiachengbin/workspace/ss_claude/gravity-pomodoro-cube

# 编译（不烧录）
/Users/jiachengbin/Library/Python/3.9/bin/pio run

# 编译并烧录（设备需先进入下载模式）
/Users/jiachengbin/Library/Python/3.9/bin/pio run -t upload --upload-port /dev/cu.usbmodem101

# 串口监控（查看运行时输出）
/Users/jiachengbin/Library/Python/3.9/bin/pio device monitor --port /dev/cu.usbmodem101

# 擦除整个 Flash（危险操作，会清除所有数据）
/Users/jiachengbin/Library/Python/3.9/bin/pio run -t erase
```

---

**文档创建**: 2026-09-15  
**烧录执行**: Codex（AI 助手）  
**硬件操作**: 用户手动执行进入下载模式
