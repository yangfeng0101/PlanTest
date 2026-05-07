# 项目目录说明

最后更新：2026-05-06

## 当前目录

```text
device-farm/
├── frontend/                 # React/Vite 前端，构建产物输出到 dist/
├── services/                 # 后端服务
│   ├── device-svc/           # 设备发现、状态、预约、分组
│   ├── screen-svc/           # scrcpy + LiveKit 投屏和远程控制
│   ├── test-svc/             # 自动化测试、脚本、任务调度
│   ├── report-svc/           # 报告、统计、导出
│   ├── midscene-runner/      # Midscene Android AI 操作执行器
│   └── shared/               # Python 服务共享组件
├── infra/                    # Docker Compose、Nginx、SQL、OpenAPI
├── docs/                     # 项目文档
├── e2e_tests/                # 端到端测试
└── dev.sh                    # 本地一键启动脚本
```

## 清理原则

保留运行和开发必需内容：
* `.env`、`infra/docker/.env`：本地环境配置，包含当前 LiveKit 局域网地址。
* `frontend/dist/`：Nginx 当前服务的前端静态资源。
* `node_modules/`：本地依赖目录，不提交到仓库，但本机开发构建需要。

可以随时清理的内容：
* `.pytest_cache/`
* `__pycache__/`
* `*.pyc`
* `.DS_Store`
* 过期的原型服务或没有 Compose/代码引用的备用实现。

## 本次整理

已移除旧的 `services/screen-svc-simple/` 原型服务。当前投屏链路统一走 `services/screen-svc/`，由 Go 服务启动 scrcpy，发布 H.264 到 LiveKit，浏览器通过 LiveKit 播放并用 DataChannel 发送控制事件。

同时清理了空的 `ralph/` 预留目录、旧分支状态文件 `docs/project/.last-branch`、Python 测试缓存和根目录下过期的独立投屏方案草稿，避免后续误判当前架构。

旧 Python `services/ai-svc/` 已移除。当前 AI 能力通过 `services/midscene-runner/` 提供，只服务于 Python 脚本 SDK 的 `app.ai_xxx()` 方法；前端不再保留独立 AI 工具入口。
