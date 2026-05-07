# AGENTS.md - Device Farm Agent Guide

本文件是 Codex/通用编码 Agent 的项目入口。Gemini 专用约束仍保留在 `GEMINI.md`。

## 1. 沟通与接手

- 默认使用中文和用户沟通。
- 新会话先读 `device-farm/docs/PROJECT_MEMORY.md`，再按任务读取相关代码和文档。
- 回答要贴近当前代码事实，不确定时先搜索、查看文件、跑非破坏性检查。
- 做 code review 时先列问题，按严重程度排序，并带文件/行号。

## 2. 项目概览

Device Farm 是企业级移动设备管理与自动化测试平台。

- 前端：React + Vite + TypeScript。
- 设备管理：`device-farm/services/device-svc/`，FastAPI，负责设备、控件树、占用释放。
- 投屏服务：`device-farm/services/screen-svc/`，Go + scrcpy + LiveKit。
- 测试执行：`device-farm/services/test-svc/`，FastAPI + Celery + Appium。
- 容器编排：`device-farm/infra/docker/docker-compose.yml`。

## 3. 工作原则

- 修改前先定位根因，说明为什么改这里能解决问题。
- 保持最小改动，不做无关重构，不替换既有架构。
- 尊重用户未提交改动：不要 reset、checkout 或覆盖非本次任务相关文件。
- 不提交 `.env`、密钥、token、Cookie、账号密码或本机私有配置。
- 修复完成后说明影响范围和验证结果。

## 4. 关键入口

- 项目记忆：`device-farm/docs/PROJECT_MEMORY.md`
- 脚本 SDK 文档：`device-farm/docs/SCRIPTING_GUIDE.md`
- 项目说明：`device-farm/README.md`
- 投屏页：`device-farm/frontend/src/pages/screen/`
- 脚本管理页：`device-farm/frontend/src/pages/scripts/`
- WebRTC 播放器：`device-farm/frontend/src/components/WebrtcPlayer/`
- 任务 API：`device-farm/services/test-svc/app/api/tasks.py`
- 脚本 API：`device-farm/services/test-svc/app/api/scripts.py`
- 执行器：`device-farm/services/test-svc/app/tasks/executor.py`
- 控件树服务：`device-farm/services/device-svc/app/services/ui_hierarchy_service.py`

## 5. 当前脚本约定

- 平台当前只支持 Python 自动化脚本，JavaScript 执行器已移除。
- 创建任务只选择设备；启动哪个 App、何时退出 App，由脚本内容控制。
- 推荐统一使用 `app.xxx` SDK，例如 `app.activate_app()`、`app.click()`、`app.screenshot()`、`app.terminate_app()`。
- 定位优先级建议：稳定 `resource-id` > `accessibility-id` > 精确文本 > XPath > 坐标兜底。

## 6. 常用验证

按改动范围选择验证命令：

```bash
git diff --check
python3 -m compileall -q device-farm/services/test-svc/app device-farm/services/device-svc/app
cd device-farm/frontend && npm run build
cd device-farm/infra/docker && docker compose config
```

前端构建可能出现 chunk 体积 warning，当前不视为阻塞问题。

## 7. 运行环境注意

- WiFi 切换后需要更新本地 ignored 配置里的 `LIVEKIT_PUBLIC_HOST`，否则手机端可能连不上 LiveKit。
- `device-farm/.env` 和 `device-farm/infra/docker/.env` 是本地环境文件，不应提交。
- 直播、动画或持续刷新的页面可能导致 UIAutomator 无法获取 idle 状态，控件树获取会失败；这时优先考虑等待页面稳定、Midscene AI 定位、图像匹配、坐标或 Appium 直接定位兜底。

## 8. 记忆文件维护

- `device-farm/docs/PROJECT_MEMORY.md` 只记录当前有效事实，不写成长流水账。
- 每次重要提交后优先更新三块：最新提交/分支状态、最近完成内容、已知问题。
- 准备 commit 前必须做一次记忆同步检查：
  - 本次改动是否改变功能、接口、脚本方法、运行流程或部署方式。
  - 本次改动是否新增/解决已知问题或排查结论。
  - 如果任一答案为“是”，先更新 `PROJECT_MEMORY.md`，再提交。
  - 如果不需要更新，在最终回复里简短说明“本次无需更新项目记忆”的原因。
- 历史流水账继续保留在 `device-farm/docs/project/progress.txt`，新会话不优先读取它。
