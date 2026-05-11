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
文本输入、清空输入和默认关闭的自动刷新截图预览能力。实时投屏、
连续触控流和 LiveKit 实时流暂不通过 iOS Agent 开放。

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
```

说明：

- `IOS_XCODE_ORG_ID` 是 Apple Developer Team ID。
- `IOS_WDA_BUNDLE_ID` 必须全局唯一，例如 `com.company.devicefarm.WebDriverAgentRunner`。
- `IOS_AGENT_REQUEST_TIMEOUT` 控制 Docker 内服务等待 iOS Agent 的时间；首次启动 WDA 可能较慢，建议不低于 90 秒。
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

## 静态预览 Benchmark 与投屏方案验证

Phase 2.4 仍不把 iOS 标记为实时投屏设备。要评估后续 Phase 3 是否能复用
Appium/WDA 截图轮询接入 `screen-svc -> LiveKit`，先用本地脚本对真实 iPhone
连续采样：

```bash
IOS_AGENT_URL=http://127.0.0.1:8015 \
IOS_DEVICE_ID=<verified-udid> \
python3 device-farm/scripts/ios_preview_benchmark.py --duration 30
```

脚本会通过 iOS Agent 的 `source`、`screenshot` 和 `debug-session` 接口测量：

- 平均 FPS、首帧耗时、P50/P95 截图耗时。
- 成功/失败次数、前几条失败原因。
- 截图尺寸、逻辑屏幕尺寸。
- debug session 是否新建或因 WDA 断开而重建。

如需仅探测 WDA/MJPEG 或 WDA 直接流是否可达，可以额外传入：

```bash
IOS_WDA_MJPEG_URL=http://127.0.0.1:<mjpeg-port>/ \
python3 device-farm/scripts/ios_preview_benchmark.py --duration 30
```

当前决策边界：Appium `/screenshot` 轮询仍作为静态预览的稳定主链路；
WDA/MJPEG 或 Mac 端采集只作为 Phase 3 实时投屏候选路线，不在本阶段进入前端产品入口。

当前实测结论：`du-iPhone` 通过 iOS Agent 跑 30 秒采样时，Appium
`/screenshot` 轮询成功 11/11、失败 0 次、平均约 0.35 FPS、首帧约 3.2 秒、
P50 约 2.8 秒、P95 约 3.2 秒。结论是：这条链路稳定，适合作为静态预览；
不适合作为 Phase 3 的实时 LiveKit 投屏主链路。Phase 3 应优先验证
WDA/MJPEG 或 Mac 端采集方案。

## WDA/MJPEG 视频源 Probe

Phase 3.1 使用独立 Appium probe session 验证 WDA/MJPEG 是否能作为实时投屏
视频源，不改变 Device Farm 产品入口，也不把 iOS 标记为实时投屏设备：

```bash
export IOS_XCODE_ORG_ID=<apple-team-id>
export IOS_XCODE_SIGNING_ID="Apple Development"
export IOS_WDA_BUNDLE_ID=<unique-wda-bundle-id>
export IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION=true

IOS_APPIUM_HOST=http://127.0.0.1:4724 \
IOS_AGENT_URL=http://127.0.0.1:8015 \
python3 device-farm/scripts/ios_stream_source_probe.py --duration 30
```

默认情况下，probe 要求当前 shell 已导出 `IOS_XCODE_ORG_ID`、
`IOS_XCODE_SIGNING_ID`、`IOS_WDA_BUNDLE_ID`，避免 probe session 与 iOS Agent
静态预览 session 使用不同 WDA bundle。只有明确需要验证默认 WDA bundle 时，
才使用 `--allow-default-wda-signing`。

probe 会创建一个临时 XCUITest session，并设置：

- `appium:mjpegServerPort=9100`
- `mjpegServerFramerate=10`
- `mjpegScalingFactor=50`
- `mjpegServerScreenshotQuality=40`

输出会包含：

- WDA/MJPEG 首帧耗时、平均 FPS、P50/P95 帧间隔、帧尺寸和帧大小。
- Appium `/screenshot` 短基线，便于和 MJPEG 结果对比。
- `recommendation.next_phase_source`，用于决定 Phase 3.2 走 WDA/MJPEG 还是转向 Mac 端采集。
- probe session 是否创建和删除成功；报告只展示签名变量是否已配置，不展示具体值。
- 开始前是否已释放 iOS Agent 静态 debug session；如需跳过可传 `--skip-ios-agent-release`。

如果 WDA 安装后立刻消失，probe 支持预编译 WDA 信任引导：

```bash
IOS_APPIUM_HOST=http://127.0.0.1:4724 \
IOS_AGENT_URL=http://127.0.0.1:8015 \
python3 device-farm/scripts/ios_stream_source_probe.py --trust-preinstall-wda --duration 3
```

这会使用 Appium 已构建出的
`Build/Products/Debug-iphoneos/WebDriverAgentRunner-Runner.app` 创建
`usePreinstalledWDA` session。即使 iOS 因证书未信任而拒绝启动，Appium 也不会走普通
session 的 WDA 卸载清理路径，WDA Runner 会留在手机上。随后进入 iPhone
“设置 > 通用 > VPN 与设备管理”信任对应开发者证书，再重新运行普通 probe 或静态截图。
如果预编译 WDA 路径不同，可传 `--prebuilt-wda-path <path-to-WebDriverAgentRunner-Runner.app>`。

当前实测结论：`du-iPhone` 通过 `ios_stream_source_probe.py --duration 30`
采样时，WDA/MJPEG 成功输出 285 帧，平均约 9.49 FPS，首帧约 224ms，
P50 帧间隔约 105ms，P95 帧间隔约 116ms，JPEG 逻辑尺寸 414x896；
Appium `/screenshot` 同 session 短基线约 3.4 FPS。结论是：
WDA/MJPEG 达到 Phase 3.2 阈值，可优先作为 `screen-svc -> LiveKit`
实时投屏视频源候选。

注意：probe session 结束时会删除自己的 Appium session，可能会让 WDA 退出。
如果运行 probe 时没有使用与 iOS Agent 相同的自定义 WDA 签名配置，后续 iOS
Agent 重启 WDA 时可能出现 `xcodebuild failed with code 65`。遇到时优先检查
当前 shell 的签名变量、自定义 WDA bundle、Team、证书信任和 Appium 日志，而
不是把它当作 Device Farm 投屏链路问题。

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
