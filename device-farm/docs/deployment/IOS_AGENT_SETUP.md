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
- 可以打开“自动刷新”，每约 1 秒刷新一次静态截图；执行操作或获取控件树时会跳过本轮刷新。
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
