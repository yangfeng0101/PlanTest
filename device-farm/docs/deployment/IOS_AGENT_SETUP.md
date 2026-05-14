# iOS Agent Local Setup

Device Farm 的 iOS 脚本执行 v1 需要把 Xcode、WebDriverAgent 和
Appium XCUITest 放在 Mac 宿主机上运行。Docker 内的 `device-svc` /
`test-svc` 只通过 HTTP 访问宿主机服务。

## 目标拓扑

```text
iPhone --USB--> Mac host
                |- Appium XCUITest: http://127.0.0.1:4724
                |- iOS Agent:       http://127.0.0.1:8015
Docker services
                |- IOS_AGENT_URL=http://host.docker.internal:8015
                |- IOS_APPIUM_HOST=http://host.docker.internal:4724
```

iOS 当前开放脚本自动化、静态控件树调试、静态点按、滑动、长按、
文本输入、清空输入和默认关闭的自动刷新截图预览能力。iOS MJPEG 直连预览
只在实验开关开启后显示；连续触控流和系统键暂不通过 iOS Agent 开放。

## 本机前置条件

- Mac 宿主机已安装完整 Xcode，不是 Command Line Tools。
- iPhone 已通过 USB 连接、解锁、信任本机，并开启 Developer Mode。
- Xcode 已登录 Apple ID，具备可用于真机调试的 Team。
- Appium 已安装 XCUITest driver。
- iOS Agent 的 Python 依赖已安装。
- WebDriverAgent 已在目标 iPhone 上真机跑通过一次。

## 快速配置

项目提供了辅助脚本，会创建 Python 虚拟环境并安装依赖。默认虚拟环境在
`${XDG_CACHE_HOME:-$HOME/.cache}/device-farm/ios-agent-venv`，避免项目目录检查时误扫第三方包。

```bash
bash device-farm/scripts/setup-ios-agent.sh
```

如需自定义虚拟环境位置：

```bash
IOS_AGENT_VENV=/path/to/ios-agent-venv bash device-farm/scripts/setup-ios-agent.sh
```

如果要顺手生成 LaunchAgent，让 Appium 和 iOS Agent 后台常驻：

```bash
INSTALL_LAUNCH_AGENTS=true bash device-farm/scripts/setup-ios-agent.sh
```

生成后会写入：

- `~/Library/LaunchAgents/com.devicefarm.appium-ios.plist`
- `~/Library/LaunchAgents/com.devicefarm.ios-agent.plist`

如果希望脚本生成后立刻启动：

```bash
INSTALL_LAUNCH_AGENTS=true START_LAUNCH_AGENTS=true bash device-farm/scripts/setup-ios-agent.sh
```

## 手动启动

安装 XCUITest driver：

```bash
npm install -g appium
appium driver install xcuitest
```

启动宿主机 Appium：

```bash
appium --address 127.0.0.1 --port 4724 --base-path /
```

启动 iOS Agent：

```bash
cd device-farm/services/ios-agent
python3 -m venv "${XDG_CACHE_HOME:-$HOME/.cache}/device-farm/ios-agent-venv"
. "${XDG_CACHE_HOME:-$HOME/.cache}/device-farm/ios-agent-venv/bin/activate"
pip install -r requirements.txt
IOS_APPIUM_HOST=http://127.0.0.1:4724 \
IOS_AGENT_PYTHON="${XDG_CACHE_HOME:-$HOME/.cache}/device-farm/ios-agent-venv/bin/python" \
IOS_XCODE_ORG_ID=<apple-team-id> \
IOS_XCODE_SIGNING_ID="Apple Development" \
IOS_WDA_BUNDLE_ID=<unique-wda-bundle-id> \
IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION=true \
IOS_AGENT_AUTOMATION_READY_UDIDS=<verified-udid> \
uvicorn app:app --host 0.0.0.0 --port 8015
```

如需调整静态调试 session 的保活时间：

```bash
IOS_AGENT_DEBUG_SESSION_TTL_SECONDS=300
```

首次启动 WDA 可能需要编译、安装和等待设备响应，创建 Appium session 的超时单独由
`IOS_AGENT_SESSION_CREATE_TIMEOUT` 控制，默认 90 秒。普通 Appium 命令仍使用
`IOS_AGENT_COMMAND_TIMEOUT`，默认 20 秒。

## Docker 环境变量

在 `device-farm/infra/docker/.env` 里配置 Docker 服务访问宿主机服务：

```dotenv
IOS_AGENT_URL=http://host.docker.internal:8015
IOS_APPIUM_HOST=http://host.docker.internal:4724
IOS_XCODE_ORG_ID=<apple-team-id>
IOS_XCODE_SIGNING_ID=Apple Development
IOS_WDA_BUNDLE_ID=<unique-wda-bundle-id>
IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION=true
IOS_AGENT_REQUEST_TIMEOUT=90
IOS_ENABLE_EXPERIMENTAL_SCREEN=false
IOS_SCREEN_DRIVER=mjpeg-direct
```

说明：

- `IOS_XCODE_ORG_ID` 是 Apple Developer Team ID。
- `IOS_WDA_BUNDLE_ID` 必须全局唯一，例如 `com.company.devicefarm.WebDriverAgentRunner`。
- `IOS_AGENT_REQUEST_TIMEOUT` 控制 Docker 内服务等待 iOS Agent 的时间；首次启动 WDA 可能较慢，建议不低于 90 秒。
- `IOS_ENABLE_EXPERIMENTAL_SCREEN=true` 会让已验证的 iOS 设备在投屏页进入
  MJPEG 直连预览，默认保持 `false`。
- `IOS_SCREEN_DRIVER=mjpeg-direct` 是当前已验证的 iOS 实验投屏 driver。
- 这些签名变量由 `test-svc` / `test-worker` 和宿主机 iOS Agent 传给 Appium，不要写进脚本内容。

修改后重建相关容器：

```bash
cd device-farm/infra/docker
docker compose up -d --build device-svc test-svc test-worker
```

## WDA 验证和设备放开

iOS Agent 默认很保守：Appium `/status` 可达不代表每台 iPhone 的 WDA 都可用。
真机 WDA smoke 成功后，再把已验证的 UDID 加到宿主机 iOS Agent 环境变量：

```bash
IOS_AGENT_AUTOMATION_READY_UDIDS=<verified-udid>
```

如果用 LaunchAgent 启动 iOS Agent：

```bash
IOS_AGENT_AUTOMATION_READY_UDIDS=<verified-udid> \
INSTALL_LAUNCH_AGENTS=true \
START_LAUNCH_AGENTS=true \
bash device-farm/scripts/setup-ios-agent.sh
```

验证 Agent：

```bash
curl http://127.0.0.1:8015/health
curl http://127.0.0.1:8015/devices
```

期望 `/devices` 中目标 iPhone 返回：

- `os=ios`
- `status=online`
- `automation_ready=true`
- `automation_status=verified_ready`

然后在脚本管理页选择该 iPhone 运行 iOS 脚本。

## 静态控件树与操作调试

WDA smoke 验证通过并设置 `IOS_AGENT_AUTOMATION_READY_UDIDS` 后，投屏页会对
iOS 设备开启静态调试模式：

- 不启动 LiveKit，也不开放实时投屏或连续触控流。
- 可以点击“刷新截图”获取当前屏幕静态截图。
- 可以点击“获取控件”拉取 Appium page source，并在截图上高亮控件范围。
- 可以开启“点按模式”后点击截图坐标，或选择控件后点击控件中心点。
- 可以开启“滑动模式”后在截图上拖动，执行一次性 WDA swipe。
- 可以选择控件后点击控件中心点，或对控件中心点执行长按。
- 可以使用键盘输入面板向当前焦点输入文本，也可以清空当前焦点输入框；
  输入和清空前都需要先点按目标输入框。
- 可以打开“自动刷新”，选择 1 秒、2 秒或 5 秒间隔刷新静态截图；执行操作或获取控件树时会跳过本轮刷新。
- 页脚会展示最近刷新耗时、连续失败次数、最近错误和当前 iOS debug session 是否被静态预览占用。
- 截图刷新失败时，前端会释放 iOS debug session 并自动重试一次；iOS Agent 也会在典型 WDA 代理断开时重建一次 session。
- 坐标使用 Appium/WDA 的逻辑点坐标，不是 Retina 物理截图像素。
- 离开页面或切换设备时，会通过 `DELETE /devices/<udid>/debug-session` 释放
  iOS Agent 内缓存的 Appium debug session。

也可以直接验证 Agent 内部接口：

```bash
curl http://127.0.0.1:8015/devices/<verified-udid>/screenshot
curl http://127.0.0.1:8015/devices/<verified-udid>/source
curl -X POST http://127.0.0.1:8015/devices/<verified-udid>/tap \
  -H 'Content-Type: application/json' \
  -d '{"x":120,"y":240}'
curl -X POST http://127.0.0.1:8015/devices/<verified-udid>/swipe \
  -H 'Content-Type: application/json' \
  -d '{"startX":120,"startY":600,"endX":120,"endY":220,"durationMs":500}'
curl -X POST http://127.0.0.1:8015/devices/<verified-udid>/long-press \
  -H 'Content-Type: application/json' \
  -d '{"x":120,"y":240,"durationMs":800}'
curl -X POST http://127.0.0.1:8015/devices/<verified-udid>/text \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}'
curl -X POST http://127.0.0.1:8015/devices/<verified-udid>/clear-text
curl -X DELETE http://127.0.0.1:8015/devices/<verified-udid>/debug-session
```

`tap`、`swipe`、`long-press`、`text`、`clear-text` 默认 `includeScreen=false`，
响应会返回 `latency_ms`、`control_method` 和 `session_reused`，用于排查触控延迟。
静态截图调试需要同步刷新逻辑屏幕时，可在请求体里传 `includeScreen=true`；`mjpeg-direct`
投屏链路应保持默认值，避免每次触控后额外请求 `window/rect`。
`tap`、`swipe`、`long-press` 会优先直连 WDA `/actions`，默认 WDA 地址为
`IOS_WDA_BASE_URL=http://127.0.0.1:8100`；直连不可用时会自动回退到 Appium
`mobile:` 指令，再回退到 W3C actions。已有 stream/debug session 会直接复用，
不会每次触控前重复枚举设备或检查 Appium status。

## iOS MJPEG 直连预览

默认情况下 iOS 仍进入静态预览。如果要验证更流畅的 iOS 画面预览，可以显式开启
实验能力：

```dotenv
IOS_ENABLE_EXPERIMENTAL_SCREEN=true
IOS_SCREEN_DRIVER=mjpeg-direct
```

重启 `device-svc`、`screen-svc` 和 `nginx` 后，已验证的 iOS 设备会显示为支持
投屏，正式 `/screen` 页面会走：

```text
Browser POST prepare
  -> screen-svc POST /api/v1/sessions/<udid>/ios-mjpeg/prepare
  -> iOS Agent POST /devices/<udid>/stream-session
  -> 返回 WDA 逻辑屏幕尺寸，供前端坐标映射

Browser <img>
  -> screen-svc GET /api/v1/sessions/<udid>/ios-mjpeg
  -> iOS Agent POST /devices/<udid>/stream-session
  -> WDA/MJPEG multipart stream
```

这条链路不启动 LiveKit，也不做 ffmpeg/H264 转码；Android/Harmony 投屏仍走原来的
LiveKit/WebRTC。iOS `remoteControl` 仍为 `false`，点按、滑动、长按、输入和清空
继续通过 iOS Agent 的低延迟一次性 Appium/WDA 操作接口完成；它不是 Android/scrcpy
那种连续实时触控流。

关闭页面或断开投屏时，前端会调用
`DELETE /api/v1/sessions/<udid>/ios-mjpeg`，`screen-svc` 再调用
`DELETE /devices/<udid>/stream-session` 释放 iOS Agent 内的 stream session。iOS Agent
也会按 debug session TTL 清理过期 stream session，避免异常断开后长期占用 WDA。
同一台 iPhone 同时只应打开一个投屏/调试入口，避免抢占 WDA session。

## iOS Smoke 示例

项目内提供了一个可复制到脚本管理页的 iOS 设置页 smoke：

```text
device-farm/scripts/examples/ios_settings_smoke.py
```

它会启动系统设置、截图、读取页面 source，并点击 `通用` 或 `General`。

也可以直接通过 API 创建脚本并运行任务：

```bash
API_BASE=http://localhost:8003/api/v1 \
DEVICE_ID=<ios-udid> \
python3 device-farm/scripts/ios_smoke_task_flow.py
```

## 常见问题

### `No Account for Team`

确认 Xcode 已登录 Apple ID，且 `IOS_XCODE_ORG_ID` 是正确 Team ID。可以用下面命令辅助检查本机证书：

```bash
security find-certificate -c "Apple Development" -p | openssl x509 -noout -subject
```

### WDA bundle id 不可用

换一个唯一的 `IOS_WDA_BUNDLE_ID`，例如带公司域名和个人后缀的 bundle id。

### WDA 安装后立刻消失，手机上没法信任

这是 Appium/XCUITest 的失败清理行为：WDA 构建和安装成功后，如果 iOS 因开发者证书
未信任而拒绝启动，Appium 会结束并卸载本次 WDA session，所以手机桌面或设置里可能
一闪而过，看起来“根本没安装成功”。

解决方式是用预编译 WDA 信任引导，让 WDA 留在手机上足够久：

```bash
export IOS_XCODE_ORG_ID=<apple-team-id>
export IOS_XCODE_SIGNING_ID="Apple Development"
export IOS_WDA_BUNDLE_ID=<unique-wda-bundle-id>
export IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION=true

IOS_APPIUM_HOST=http://127.0.0.1:4724 \
IOS_AGENT_URL=http://127.0.0.1:8015 \
IOS_DEVICE_ID=<ios-udid> \
python3 device-farm/scripts/ios_stream_source_probe.py --trust-preinstall-wda --duration 3
```

如果命令仍以 “not explicitly trusted” / “invalid code signature” 失败，这是预期的：
重点是 WDA Runner 已被保留在手机上。随后到 iPhone“设置 > 通用 > VPN 与设备管理”
信任开发者证书，再重新运行普通静态截图、脚本任务或 probe。

注意：Appium 的 `iosInstallPause` 只覆盖被测 App 安装后的暂停，不覆盖 WDA Runner 的
安装/启动清理路径，所以不要用它来解决 WDA 信任问题。

### iPhone 提示开发者未受信任

在 iPhone 上进入“设置 > 通用 > VPN 与设备管理”，信任对应开发者证书后重试。

### Agent 能看到设备，但 `automation_ready=false`

这通常是预期行为。先完成一次 WDA 真机 smoke，确认 Appium 能创建 iOS session，
再把该 UDID 加入 `IOS_AGENT_AUTOMATION_READY_UDIDS`。

### Docker 内访问不到宿主机 Appium

确认 Docker `.env` 使用的是 `host.docker.internal`：

```dotenv
IOS_AGENT_URL=http://host.docker.internal:8015
IOS_APPIUM_HOST=http://host.docker.internal:4724
```

如果不是 Docker Desktop 环境，可以换成 Mac 的局域网 IP。
