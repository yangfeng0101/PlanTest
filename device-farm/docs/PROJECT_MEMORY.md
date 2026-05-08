# Device Farm Project Memory

> 新会话接手时先读本文件，再按任务读取 `SCRIPTING_GUIDE.md`、相关服务代码和页面代码。
>
> 维护规则：每次重要提交前都要检查本文件是否需要同步；只记录当前有效事实，不记录敏感信息或临时调试噪声。

## 当前状态

- 当前远程状态：`main` 已合并并推送 iOS 脚本执行 v1；`dev-reboot` 保留对应功能提交。
- 前端当前展示品牌名为“云测”，登录页副标题为“移动设备云测试平台”。
- 最近一次功能改动：iOS 脚本执行 v1 接入，新增 Mac 宿主机 `ios-agent`、设备 automation 能力、iOS Appium host 分流和脚本管理页 iOS 设备选择。
- 最近一次文档/示例补充：新增 iOS Agent 本机配置文档、`scripts/setup-ios-agent.sh` 辅助脚本、`scripts/examples/ios_settings_smoke.py` 设置页 smoke 示例和 `scripts/ios_smoke_task_flow.py` 一键任务链路 smoke。
- 最近验证通过：
  - `git diff --check`
  - Python `compileall`
  - `docker compose config`
  - 前端 `npm run build`
  - `midscene-runner` 本地 `/health` 和未配置模型错误返回检查
  - Midscene 真机端到端验证：Docker 内网 runner 可通过宿主机 ADB 连接华为 P50 Pro，`ai_locate` / `ai_tap` / `ai_input` / `ai_clear` / `ai_key` / `ai_scroll` / `ai_long_press` / `ai_double_tap` / `ai_act` / `ai` / `ai_wait` / `ai_assert` 均已真实调用；Python SDK 任务通过 test-svc + Celery worker 执行成功并返回 `script_line` 行号事件
  - `test-svc` / `device-svc` 运行期 import 检查
  - 当前 Postgres 表结构可兼容 `python`、`pending` 等 value 字符串
  - iOS 脚本执行 v1 静态验证：Python `compileall`、设备能力单测、`docker compose config`、前端 `npm run build`

## 最近完成的改动

- 自动化脚本只保留 Python，JavaScript 脚本支持和执行器已移除。
- 新增 Python 脚本 SDK，推荐统一使用 `app.xxx`：
  - App 控制：`app.activate_app()`、`app.terminate_app()`、`app.restart_app()`
  - 元素能力：`app.find()`、`app.click()`、`app.exists()`、`app.click_text()`
  - 辅助能力：`app.log()`、`app.wait()`、`app.screenshot()`、`app.source()`
- 创建任务流程改为只选择设备；App 包名和启动/退出逻辑由脚本内容自行控制。
- 任务执行支持取消：
  - 前端运行按钮会展示 pending/running 状态。
  - 可以取消 pending/running 任务。
  - 后端取消后会尽力释放设备。
- 投屏页新增脚本编写入口：
  - 工作区包含“控件检查 / 编写脚本 / Logcat”。
  - 可以一边投屏一边获取控件树、查看属性、插入定位脚本片段。
  - 保存脚本时再填写名称、标签、描述，脚本保存到脚本管理。
- 投屏页体验优化：
  - 控件检查页不再重复展示脚本片段，脚本片段只在“编写脚本”页底部辅助面板展示。
  - 控件属性区域取消固定表格高度，自动化选择器区域压缩高度，尽量展示更多属性。
  - “编写脚本”页使用深色 Monaco 代码工作台，支持 `vs-dark` 主题且保留脚本行数状态栏。
- 投屏页支持脚本运行调试：
  - “编写脚本”页可自动保存调试草稿并在当前设备上创建任务。
  - 脚本工具栏支持打开脚本选择弹窗，弹窗顶部可新建脚本并填入与脚本管理页一致的 App 冒烟示例，也可选择已保存脚本载入编辑器；运行中“运行调试”切换为“停止调试”。
  - 调试任务会通过结构化任务日志返回 `script_line` 行号事件，前端实时高亮当前执行行。
  - 调试任务失败后，前端会把最后执行行显示为红色失败行，并在运行日志和编辑器状态栏提示行号。
  - 行号事件在执行器侧做节流并在任务结束前补最后执行行，避免循环脚本刷爆任务日志。
  - 调试任务状态、普通日志和截图在脚本编辑器下方的内嵌运行日志面板展示，不再依赖弹窗查看。
  - `task_logs` 表新增 nullable `event_type` 和 `line_number` 字段，服务启动时会对旧库做兼容性补列。
- 脚本管理页支持按脚本查看运行记录：
  - 操作列新增“运行记录”入口。
  - 前端通过现有 `GET /tasks?script_id=...` 拉取最近任务，无需新增后端表或 API。
  - 运行记录中的任务可继续打开原任务详情弹窗查看状态、日志、截图和耗时。
- Python 脚本 SDK 接入 Midscene AI 操作能力：
  - SDK 版本升级为 `1.2.0`。
  - 新增 `app.ai()`、`app.ai_act()`、`app.ai_locate()`、`app.ai_tap()`、`app.ai_input()`、`app.ai_clear()`、`app.ai_key()`、`app.ai_scroll()`、`app.ai_long_press()`、`app.ai_double_tap()`、`app.ai_wait()`、`app.ai_assert()`。
  - `test-worker` 通过 `MIDSCENE_RUNNER_URL=http://midscene-runner:8005` 调用 Docker 内网 Node runner。
  - `midscene-runner` 使用 `@midscene/android` 直连宿主机 ADB/scrcpy，缓存设备 Agent，不映射宿主机端口。
  - Midscene 模型通过环境变量配置：`MIDSCENE_MODEL_NAME`、`MIDSCENE_MODEL_BASE_URL`、`MIDSCENE_MODEL_API_KEY`、`MIDSCENE_MODEL_FAMILY`、`MIDSCENE_CACHE`。
- iOS 脚本执行 v1：
  - 新增 `services/ios-agent/`，作为 Mac 宿主机服务发现 iPhone 并检查 Appium XCUITest 状态。
  - 本机配置入口：`docs/deployment/IOS_AGENT_SETUP.md`；辅助脚本：`scripts/setup-ios-agent.sh`，默认把 venv 放在 `${XDG_CACHE_HOME:-$HOME/.cache}/device-farm/ios-agent-venv`，避免整目录验证误扫第三方包。
  - iOS smoke 示例：`scripts/examples/ios_settings_smoke.py`，可复制到脚本管理页运行。
  - iOS 任务链路 smoke：`API_BASE=http://localhost:8003/api/v1 DEVICE_ID=<ios-udid> python3 device-farm/scripts/ios_smoke_task_flow.py`。
  - `ios-agent` 默认不会把 Appium `/status` 可达直接等同为单机 WDA 可用；真机 WDA 验证通过后，用 `IOS_AGENT_AUTOMATION_READY_UDIDS=<udid>[,<udid>]` 按设备放开脚本执行。
  - Docker 内 `device-svc` 通过 `IOS_AGENT_URL` 合并 iOS 设备；`test-svc` / `test-worker` 通过 `IOS_APPIUM_HOST` 连接 Mac Appium。
  - iOS WDA 签名可通过 `IOS_XCODE_ORG_ID`、`IOS_XCODE_SIGNING_ID`、`IOS_WDA_BUNDLE_ID`、`IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION` 传入 Appium capabilities。
  - `test-svc` 会在合并任务 `device_capabilities` 后强制覆盖平台、UDID、automationName、ADB host 和 iOS WDA 签名等服务端所有 caps，避免脚本任务绕过设备占用。
  - 设备能力新增 `automation`；iOS v1 只开放脚本执行，默认不开放投屏、触控、控件树和设备详情截图。
  - 脚本 SDK 版本升级为 `1.3.0`，`app.click_text()` 在 iOS 上按 `label/name/value` 查询，并保留非 ASCII 文本用于中文 label 定位。
- 旧 Python `services/ai-svc/`、前端 AI 工具菜单/页面、Vite/Nginx 的旧 `/ocr`、`/locate`、`/generate` 代理已移除；历史 `docs/project/*` 中的旧记录仍作为归档保留。
- 控件树获取增强：
  - 前端增加超时处理。
  - 后端对 UIAutomator idle/timeout/killed 错误返回更明确的中文提示。
- Appium 执行链路增强：
  - Docker Compose 增加 Appium 服务和 test-worker。
  - test-svc/test-worker 安装 ADB。
  - 支持通过包名解析启动 Activity。
- 新增脚本文档：`device-farm/docs/SCRIPTING_GUIDE.md`。
- 新增冒烟脚本：`device-farm/scripts/smoke_task_flow.py`。

## 当前约定

- 用户编写脚本时只关心“有哪些方法可用”，不要暴露不必要的平台内部概念。
- 脚本示例以 `app.xxx` 为主，旧全局函数仅兼容历史脚本。
- AI 兜底推荐走 `app.ai_xxx()`。第一版只支持 Android/Harmony 这类可通过 ADB 控制的设备，不提供前端 AI 面板，也不暴露数据提取类 `ai_query/ai_string/ai_number/ai_boolean/ai_ask`；iOS v1 暂不支持 Midscene AI。
- 定位推荐：
  - 首选稳定 `resource-id`，如 `app.click(AppiumBy.ID, "...", timeout=10)`。
  - 其次用 `accessibility-id`、精确文本、XPath。
  - 坐标点击只作为兜底。
- `app.click_text()` 只适合目标文本或 `content-desc` 本身可被 Appium 定位并点击的场景；如果文本在不可点击子控件上，应优先点击可点击父级的 `resource-id`。

## 已知限制

- 直播、动画或持续刷新页面可能导致 UIAutomator 无法获取 idle 状态，表现为控件树获取失败或一直转圈；这是 Android UIAutomator 的稳定性限制，不代表投屏失败。
- 获取动态页面控件时，可考虑等待页面稳定、使用 Appium 直接定位、Midscene AI 定位、图像匹配或坐标兜底。
- 投屏页的 Logcat tab 目前仍是占位能力。
- Midscene AI 脚本能力依赖模型环境变量和宿主机全局 ADB；未配置模型时，`app.ai_xxx()` 会在任务日志中返回明确错误。
- `MIDSCENE_MODEL_FAMILY` 需要填写 Midscene 支持的模型系列，例如 `qwen3-vl`，不要填具体模型名 `qwen3-vl-plus`；具体模型名应放在 `MIDSCENE_MODEL_NAME`。
- `@midscene/android` 当前最新版本为 `1.7.9`；`npm audit --omit=dev --registry=https://registry.npmjs.org` 会报告其传递依赖中的漏洞，自动修复建议降级到旧版 `0.13.1`，当前不采用。`midscene-runner` 保持 Docker 内网服务、不映射宿主机端口，后续跟踪上游版本修复。
- Midscene 第一版未接入 HTML 报告、断点/单步调试、pinch、数据提取方法，也未复用 screen-svc 的截图/触控链路。
- iOS v1 只支持脚本执行闭环；投屏、远程触控、控件树和设备详情截图待后续基于 WDA/独立 session 链路接入。
- 前端生产构建有 chunk 体积 warning，当前不阻塞功能，后续可通过动态 import 或 manualChunks 优化。
- WiFi 切换后需要更新本地 ignored 配置中的 `LIVEKIT_PUBLIC_HOST`，否则手机端可能无法连接 LiveKit。

## 下次接手建议

- 处理脚本执行问题时优先看：
  - `device-farm/docs/SCRIPTING_GUIDE.md`
  - `device-farm/services/test-svc/app/tasks/executor.py`
  - `device-farm/services/test-svc/app/api/tasks.py`
  - `device-farm/services/test-svc/app/drivers/appium.py`
- 处理 Midscene AI 脚本能力时优先看：
  - `device-farm/services/midscene-runner/src/server.js`
  - `device-farm/services/test-svc/app/tasks/executor.py`
  - `device-farm/infra/docker/docker-compose.yml`
  - `device-farm/docs/SCRIPTING_GUIDE.md`
- 处理脚本管理/运行 UI 时优先看：
  - `device-farm/frontend/src/pages/scripts/index.tsx`
  - `device-farm/frontend/src/services/api.ts`
  - `device-farm/frontend/src/types/index.ts`
- 处理投屏页和控件检查时优先看：
  - `device-farm/frontend/src/pages/screen/index.tsx`
  - `device-farm/frontend/src/pages/screen/ScreenPage.css`
  - `device-farm/services/device-svc/app/services/ui_hierarchy_service.py`
- 处理 LiveKit/WiFi 问题时优先确认：
  - `device-farm/.env`
  - `device-farm/infra/docker/.env`
  - `device-farm/infra/docker/docker-compose.yml`
  - `livekit` 和 `screen-svc` 容器日志

## 维护检查清单

提交前检查本次改动是否命中以下任一项：

- 改变了用户可见功能、API、脚本 SDK 方法或任务执行流程。
- 改变了部署、容器、环境变量、端口或本地运行方式。
- 新增、解决或确认了重要已知问题。
- 产生了下次会话必须知道的排查结论。

命中时，先更新本文件的“当前状态”“最近完成的改动”或“已知限制”，再提交。未命中时无需更新，避免把本文件写成流水账。
