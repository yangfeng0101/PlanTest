# Device Farm Project Memory

> 新会话接手时先读本文件，再按任务读取 `SCRIPTING_GUIDE.md`、相关服务代码和页面代码。
>
> 维护规则：每次重要提交前都要检查本文件是否需要同步；只记录当前有效事实，不记录敏感信息或临时调试噪声。

## 当前状态

- 当前分支状态：本轮投屏页前端结构拆分已完成；`main` 与 `dev-reboot` 应保持在包含该结构拆分的最新提交。
- 前端当前展示品牌名为“云测”，登录页副标题为“移动设备云测试平台”。
- 前端构建已启用页面级懒加载和 Vite `manualChunks`：Screen/Scripts/Monitoring/Reports 等页面按路由加载，Monaco、LiveKit、ECharts、Ant Design 拆为独立 vendor chunk，以降低首屏主业务包体积并改善缓存复用。
- 前端路由/静态资源 smoke 可运行 `cd device-farm/frontend && npm run smoke:routes`，该命令会构建生产包、启动 Vite preview、检查关键 SPA 路由和 `dist/assets` 构建产物是否可访问。
- 最近一次结构改动：投屏页 `frontend/src/pages/screen/index.tsx` 已拆出 `DeviceStagePanel.tsx`、`WorkspacePanel.tsx`、`ScreenStage.tsx`、`InspectorPanel.tsx`、`ScriptWorkspacePanel.tsx`、`ScriptModals.tsx`、`useScreenDevices.ts`、`useScreenSession.ts`、`useIosDebugActions.ts`、`useScreenScriptWorkspace.ts`、`useScreenUiHierarchy.ts`、`useScreenLayoutMetrics.ts`、`useScreenControls.ts`、`useScreenMode.ts`、`api.ts`、`scriptWorkspace.ts`、`types.ts`、`uiHierarchy.ts`；本次仅做 UI/API/hook/helper 分层，不改变 Android/iOS 投屏、触控、控件树和脚本调试链路。
- 最近一次功能改动：投屏生命周期收敛到 device-svc 现有设备占用语义。Android/LiveKit 投屏和 iOS `mjpeg-direct` 预览启动前都会占用设备，启动失败、停止、断连或本地 session 结束时只释放 screen-svc 本次成功占用的设备；iOS MJPEG prepare 后如果 30 秒内没有真正接入 MJPEG GET，会自动释放占用；device-svc 扫描会保留已占用设备的 `busy` 状态，不再刷回 `online + occupied_by` 的半占用状态；iOS `mjpeg-direct` 投屏态的点按、滑动、长按、输入、清空和控件树获取会走 screen-svc 当前 session 代理，不再走 device-svc 静态调试接口；设备管理页投屏入口按 `online` 状态和 screen-svc session 状态禁用；脚本任务创建时不再立即占用设备，worker 真正执行前才用 `test-svc:<task_id>` 占用设备，普通任务遇到 `busy` 会保持 `pending` 并重试，投屏页调试任务会带 `screen_debug` 参数以共享当前投屏占用且结束时不释放投屏 lease；iOS Agent 增加 debug/stream session TTL 后台清理。iOS 连续实时触控仍未开放。
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
  - iOS 静态调试真机验证：iPhone 通过 WDA/Appium 完成截图、控件树、静态点按、聚焦后文本输入；LaunchAgent 以 `0.0.0.0:8015` 暴露 iOS Agent，Docker 可通过 `IOS_AGENT_URL` 访问。
  - iOS Phase 2.3 真机验证：`du-iPhone` 通过 iOS Agent 和 Docker `device-svc` 代理完成 screenshot/source/ui-hierarchy、tap、text、clear-text、swipe、long-press；并发截图/控件树/手势请求经 Agent UDID 命令锁串行后均返回 200。
  - iOS Phase 2.4 投屏方案 benchmark：`du-iPhone` 通过 iOS Agent 30 秒采样，Appium `/screenshot` 轮询成功 11/11、失败 0、平均约 0.35 FPS、首帧约 3.2 秒、P50 约 2.8 秒、P95 约 3.2 秒；结论是稳定但太慢，只适合静态预览，Phase 3 实时投屏应优先验证 WDA/MJPEG 或 Mac 端采集。
  - iOS MJPEG 直连验证：`du-iPhone` 通过 `screen-svc` 直连代理 WDA/MJPEG 到浏览器，真机体感明显比此前 `MJPEG -> ffmpeg/H264 -> LiveKit/WebRTC` 链路流畅；因此保留 `mjpeg-direct` 作为实验预览 driver，暂不再推进 iOS MJPEG 转 H264/LiveKit 方案。
  - iOS WDA 信任问题已通过 `ios_stream_source_probe.py --trust-preinstall-wda` 验证修复路径：预编译 WDA Runner 能留在手机安装列表中；用户在 iPhone 信任开发者证书后，普通 probe 成功创建 WDA session，5 秒 MJPEG 短测 47 帧、平均约 9.37 FPS、首帧约 190ms，Appium `/screenshot` 短基线成功 7/7、约 3.47 FPS；iOS Agent 静态截图接口也可正常返回并复用 debug session。
  - iOS 低延迟触控真机验证：`du-iPhone` 在 `mjpeg-direct` stream session 复用状态下，iOS Agent 热路径已绕开重复设备枚举/Appium status；10 次 tap 约 586-818ms，顺序 swipe 约 1.3s，long-press 约 1.3s，device-svc 代理 tap 约 745ms。此前 Appium `mobile: tap` 约 1.7-2.6s，主要慢点已确认在热路径重复设备校验和 Appium 动作代理；当前 WDA 8100 直连端口不稳定可用，因此 Agent 保留 WDA direct 优先、Appium `mobile:` fallback。
  - 投屏占用收敛真机验收：华为 P50 Pro Android/Harmony 投屏启动后设备保持 `busy`，投屏期间创建脚本任务返回 409，停止后恢复 `online`；`du-iPhone` iOS `mjpeg-direct` prepare 后设备保持 `busy`，投屏期间 iOS 脚本任务和静态截图调试均返回 409，MJPEG GET 可拉取约 1.4 MB 数据，GET 断开或 DELETE 停止后恢复 `online`；prepare 后不接 GET 的场景 30 秒后自动恢复 `online`。本次验收发现并修复 device-svc 扫描把已占用设备刷回 `online` 的问题。

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
  - 投屏页连接投屏后也可以运行调试脚本；调试任务通过 `screen_debug` 标记共享当前投屏占用，任务结束不会释放投屏 session 的设备占用。
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
  - 脚本管理页运行脚本时可选择 `online` 或 `busy` 且支持 automation 的设备；如果设备正忙，任务会创建为 `pending` 排队，待 worker 发现设备释放后再占用并运行。
- Python 脚本 SDK 接入 Midscene AI 操作能力：
  - SDK 版本升级为 `1.2.0`。
  - 新增 `app.ai()`、`app.ai_act()`、`app.ai_locate()`、`app.ai_tap()`、`app.ai_input()`、`app.ai_clear()`、`app.ai_key()`、`app.ai_scroll()`、`app.ai_long_press()`、`app.ai_double_tap()`、`app.ai_wait()`、`app.ai_assert()`。
  - `test-worker` 通过 `MIDSCENE_RUNNER_URL=http://midscene-runner:8005` 调用 Docker 内网 Node runner。
  - `midscene-runner` 使用 `@midscene/android` 直连宿主机 ADB/scrcpy，缓存设备 Agent，不映射宿主机端口。
  - Midscene 模型通过环境变量配置：`MIDSCENE_MODEL_NAME`、`MIDSCENE_MODEL_BASE_URL`、`MIDSCENE_MODEL_API_KEY`、`MIDSCENE_MODEL_FAMILY`、`MIDSCENE_CACHE`。
- iOS 脚本执行与静态调试：
  - 新增 `services/ios-agent/`，作为 Mac 宿主机服务发现 iPhone 并检查 Appium XCUITest 状态。
  - 本机配置入口：`docs/deployment/IOS_AGENT_SETUP.md`；辅助脚本：`scripts/setup-ios-agent.sh`，默认把 venv 放在 `${XDG_CACHE_HOME:-$HOME/.cache}/device-farm/ios-agent-venv`，避免整目录验证误扫第三方包。
  - iOS smoke 示例：`scripts/examples/ios_settings_smoke.py`，可复制到脚本管理页运行。
  - iOS 任务链路 smoke：`API_BASE=http://localhost:8003/api/v1 DEVICE_ID=<ios-udid> python3 device-farm/scripts/ios_smoke_task_flow.py`。
  - `ios-agent` 默认不会把 Appium `/status` 可达直接等同为单机 WDA 可用；真机 WDA 验证通过后，用 `IOS_AGENT_AUTOMATION_READY_UDIDS=<udid>[,<udid>]` 按设备放开脚本执行。
  - Docker 内 `device-svc` 通过 `IOS_AGENT_URL` 合并 iOS 设备；`test-svc` / `test-worker` 通过 `IOS_APPIUM_HOST` 连接 Mac Appium。
  - iOS WDA 签名可通过 `IOS_XCODE_ORG_ID`、`IOS_XCODE_SIGNING_ID`、`IOS_WDA_BUNDLE_ID`、`IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION` 传入 Appium capabilities。
  - `device-svc` 访问 iOS Agent 的超时通过 `IOS_AGENT_REQUEST_TIMEOUT` 控制，默认 90 秒，避免首次 WDA 启动较慢时过早中断。
  - `test-svc` 会在合并任务 `device_capabilities` 后强制覆盖平台、UDID、automationName、ADB host 和 iOS WDA 签名等服务端所有 caps，避免脚本任务绕过设备占用。
  - `test-svc` 会把 `_device_snapshot` 和 `_appium_diagnostics` 写入任务 `device_capabilities` 供详情页排查；这些内部字段不会传给 Appium。
  - iOS Appium/WDA session 创建失败时会在任务错误和日志中保留原始错误，并追加中文 hint，例如 Appium host 不可达、Team 签名异常、bundle id 冲突、设备未信任或 WDA 超时。
  - 设备能力新增 `automation`；iOS 设备在 `automation_ready=true` 后开放脚本执行、静态截图、控件树调试、静态点按、滑动、长按、文本输入和清空输入，默认不开放投屏和连续触控。
  - iOS 投屏页支持实验 `mjpeg-direct` 直连预览：`device-svc` 设置 `IOS_ENABLE_EXPERIMENTAL_SCREEN=true`、`IOS_SCREEN_DRIVER=mjpeg-direct` 后，正式 `/screen` 页面先通过 `screen-svc POST /api/v1/sessions/<udid>/ios-mjpeg/prepare` 获取 WDA 逻辑屏幕尺寸，再通过 `GET /api/v1/sessions/<udid>/ios-mjpeg` 直接代理 iOS Agent WDA/MJPEG multipart 到浏览器，不启动 LiveKit、不做 ffmpeg/H264 转码；前端直连模式已收敛成接近 Android 投屏的界面，不再展示静态截图刷新/点按模式/滑动模式等额外控件，点击/拖动画面会走 `screen-svc POST /api/v1/sessions/<udid>/ios-mjpeg/debug/<action>`，控件树会走 `screen-svc GET /api/v1/sessions/<udid>/ios-mjpeg/ui-hierarchy`，由当前投屏 session owner 校验后代理到 iOS Agent 并解析 Appium source，默认不再随动作刷新 screen，并会在页脚展示最近一次触控耗时和 control method。Android/Harmony 不受影响。旧的 Go 侧 iOS MJPEG/PNG 转 H264 实验代码已移除，避免误导后续维护。
  - `screen-svc` 投屏启动统一走 device-svc 的 `occupy/release`：Android/LiveKit session 与 iOS `mjpeg-direct` session 都会让设备进入 `busy`，从而阻止脚本任务或另一个投屏入口抢同一台设备；启动失败、停止接口、iOS MJPEG 图片连接结束和 Android session done 都会按本地 lease 记录释放设备，避免释放脚本任务或其他服务占用。device-svc 后台扫描看到已占用设备仍在线时会保留 `busy`，避免扫描周期破坏占用语义。
  - 投屏页对 iOS 使用静态预览模式：不启动 LiveKit，可刷新截图、默认关闭自动刷新预览并支持 1s/2s/5s 间隔、拉取控件树、点按截图或控件中心点、拖动截图执行一次性滑动、长按控件中心点、向当前焦点输入或清空文本，并展示最近刷新耗时、连续失败次数、最近错误、iOS debug session 占用状态和 iOS selector 片段；设备列表/详情页会以“调试”入口打开该页面，切换设备或离开页面会释放 iOS Agent debug session。
  - iOS Agent 新增 `GET /devices/{udid}/screenshot`、`GET /devices/{udid}/source`、`POST /devices/{udid}/tap`、`POST /devices/{udid}/swipe`、`POST /devices/{udid}/long-press`、`POST /devices/{udid}/text`、`POST /devices/{udid}/clear-text`、`POST /devices/{udid}/stream-session`、`DELETE /devices/{udid}/stream-session`、`DELETE /devices/{udid}/debug-session`，内部按 UDID 缓存 Appium XCUITest debug/stream session，debug/stream session 均按 TTL 过期清理，并按 UDID 串行化 Appium 命令，避免并发请求打坏 WDA session；动作接口默认 `includeScreen=false` 并返回 `latency_ms`、`control_method`、`session_reused`，tap/long-press/swipe 优先直连 `IOS_WDA_BASE_URL` 的 WDA `/actions`，不可用时 fallback 到 Appium `mobile:` 指令和 W3C actions。
  - iOS Agent 创建 Appium session 使用独立 `IOS_AGENT_SESSION_CREATE_TIMEOUT`，默认 90 秒；普通命令仍使用 `IOS_AGENT_COMMAND_TIMEOUT` 默认 20 秒，避免首次 WDA 启动超过 20 秒时 Agent 过早返回 503。
  - iOS Agent 截图路径遇到典型 WDA 代理断开/连接拒绝会自动清理并重建 debug session 一次；前端截图刷新失败也会释放 debug session 后重试一次。
  - 新增 `scripts/ios_preview_benchmark.py`，通过 iOS Agent 的 source/screenshot/debug-session 接口连续采样输出平均 FPS、P50/P95 截图耗时、首帧耗时、失败次数、截图尺寸和 session 重建情况，用于 Phase 3 是否接入 `screen-svc -> LiveKit` 的方案决策。
  - 保留 `scripts/ios_stream_source_probe.py` 作为 WDA 信任引导和 MJPEG 源诊断工具；遇到 WDA 安装后被普通 Appium session 清理、手机上来不及信任开发者证书时，可用 `--trust-preinstall-wda` 走 `usePreinstalledWDA + prebuiltWDAPath` 信任引导，让 WDA Runner 留在手机上。
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
- AI 兜底推荐走 `app.ai_xxx()`。Android/Harmony 走 `@midscene/android` + ADB/scrcpy；iOS Midscene AI v1 走 iOS Agent + Appium/WDA 截图和动作接口，脚本侧方法名保持一致。不提供前端 AI 面板，也不暴露数据提取类 `ai_query/ai_string/ai_number/ai_boolean/ai_ask`；iOS `ai_key()` 暂未支持。`midscene-runner` 会尽量把模型侧认证、额度、模型不支持等错误透传到任务日志，并在 iOS AI agent 销毁时释放 iOS Agent debug session。
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
- Midscene 第一版未接入 HTML 报告、断点/单步调试、pinch、数据提取方法，也未复用 screen-svc 的截图/触控链路；iOS AI v1 复用 iOS Agent 的 debug/stream Appium session，性能取决于 WDA 截图与模型响应。若模型 provider 返回 401/403/额度耗尽等错误，runner 应优先透传模型错误摘要，而不是泛化成定位失败。
- iOS 当前支持脚本执行闭环、静态截图/控件树调试、静态点按、滑动、长按、文本输入、清空输入和准实时静态截图预览；`mjpeg-direct` 直连预览是实验能力，默认不开放，并已做低延迟一次性触控优化。连续实时触控、Home/Back/App Switch 等系统键仍未接入。
- iOS 控件树来自 Appium/WDA accessibility source；投屏页控件框会过滤不可见节点、超大无语义容器和重复同 bounds 节点，只在画面上展示更接近真实可点/可定位元素的框。右侧属性/selector 仍来自原始控件树。若 App 内存在自绘、透明覆盖层或无 accessibility 标识的元素，WDA source 本身仍可能与视觉元素不完全一致。
- iOS WDA/MJPEG probe session 结束会删除自己的 Appium session，可能导致 WDA 退出；如果 probe 与 iOS Agent 使用不同 WDA bundle，后续 iOS Agent 重启 WDA 可能出现 `xcodebuild failed with code 65`，优先检查当前 shell 的 WDA 签名环境变量、自定义 bundle、Team、证书信任和 Appium 日志。若 Appium 日志显示 WDA 已安装但 launch 因 `invalid code signature` / `not explicitly trusted` 失败，普通 session 会卸载 WDA，需先用 `ios_stream_source_probe.py --trust-preinstall-wda` 安装并保留预编译 WDA Runner，完成手机端开发者证书信任后再运行普通会话；`iosInstallPause` 只暂停被测 App 安装，不解决 WDA 信任。
- 前端生产构建仍可能提示 chunk 体积 warning，但当前主要来自稳定的大 vendor chunk（Ant Design、ECharts、LiveKit），页面级业务代码已拆分；后续如需继续压低可按需拆 AntD 按需加载、图表延迟加载或更细 manualChunks。
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
  - `device-farm/frontend/src/pages/screen/DeviceStagePanel.tsx`
  - `device-farm/frontend/src/pages/screen/WorkspacePanel.tsx`
  - `device-farm/frontend/src/pages/screen/ScreenStage.tsx`
  - `device-farm/frontend/src/pages/screen/InspectorPanel.tsx`
  - `device-farm/frontend/src/pages/screen/ScriptWorkspacePanel.tsx`
  - `device-farm/frontend/src/pages/screen/ScriptModals.tsx`
  - `device-farm/frontend/src/pages/screen/useScreenDevices.ts`
  - `device-farm/frontend/src/pages/screen/useScreenSession.ts`
  - `device-farm/frontend/src/pages/screen/useIosDebugActions.ts`
  - `device-farm/frontend/src/pages/screen/useScreenScriptWorkspace.ts`
  - `device-farm/frontend/src/pages/screen/useScreenUiHierarchy.ts`
  - `device-farm/frontend/src/pages/screen/useScreenLayoutMetrics.ts`
  - `device-farm/frontend/src/pages/screen/useScreenControls.ts`
  - `device-farm/frontend/src/pages/screen/useScreenMode.ts`
  - `device-farm/frontend/src/pages/screen/api.ts`
  - `device-farm/frontend/src/pages/screen/scriptWorkspace.ts`
  - `device-farm/frontend/src/pages/screen/types.ts`
  - `device-farm/frontend/src/pages/screen/uiHierarchy.ts`
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
