# 统一真机自动化测试平台 (Device Farm)

## 1. 项目简介
Device Farm 是一套企业级的真机自动化测试管理平台，支持 Android、iOS 和鸿蒙 (HarmonyOS) 设备的远程控制、投屏管理以及自动化测试执行。

## 2. 核心技术栈 (Technology Stack)
*   **前端 (Frontend)**: React + Vite + TypeScript + jessibuca/WebRTC 播放器
*   **设备管理 (`device-svc`)**: Python + FastAPI/Uvicorn (处理设备连接、状态、预约、分组)
*   **投屏与视频流 (`screen-svc`)**: Go (WebRTC 核心) + Node.js (辅助触控、Shell 交互)
*   **自动化引擎 (`test-svc`)**: Python + Celery + Appium/Node.js (任务调度与执行)
*   **数据统计 (`report-svc`)**: Python (报表生成、告警、导出)
*   **AI 智能化 (`ai-svc`)**: Python + UI-TARS + PaddleOCR (元素定位、用例生成)
*   **基础设施**: PostgreSQL, Redis, MinIO, Nginx, Docker

## 3. 项目架构目录树 (Architecture)
```text
device-farm/
├── frontend/                 # Web 前端应用 (React + Vite)
├── services/                 # 后端微服务群
│   ├── device-svc/           # 设备管理服务 (Port: 8001)
│   ├── screen-svc/           # WebRTC 核心投屏服务 (Port: 8002)
│   ├── screen-svc-simple/    # 投屏辅助/备用流服务
│   ├── test-svc/             # 测试执行与调度引擎 (Port: 8003)
│   ├── report-svc/           # 报表与告警服务
│   ├── ai-svc/               # AI 智能化服务
│   └── shared/               # 服务间共享组件
├── infra/                    # 基础设施 (Docker, Nginx, SQL 脚本, API 规范)
├── docs/                     # 项目详细文档 (Architecture, API, Troubleshooting)
├── ralph/                    # 代码生成与开发辅助工具
└── dev.sh                    # 开发者一键启动脚本
```

## 4. 服务端口分配 (Development Environment)
| 服务 | 端口 | 处理路径 |
|------|------|----------|
| **device-svc** | `8001` | `/api/v1/devices`, `/api/v1/groups` |
| **screen-svc** | `8002` | `/ws`, `/api/v1/devices/:id/screen` |
| **test-svc** | `8003` | `/api/v1/auth`, `/api/v1/scripts`, `/api/v1/tasks` |
| **frontend** | `3000` | (Vite 开发服务器) |

## 5. 快速开始 (Quick Start)
1.  **配置环境变量**: `cp .env.example .env` (可选，`./dev.sh` 会自动创建)
2.  **启动开发环境**: 运行根目录下的 `./dev.sh start` 脚本。脚本会自动探测本机局域网 IP，并写入 `LIVEKIT_PUBLIC_HOST`，用于手机端访问 WebRTC 视频流。
3.  **手动启动 Docker**: 如果不用脚本，请先在 `infra/docker/.env` 中设置当前局域网 IP，例如 `LIVEKIT_PUBLIC_HOST=192.168.3.74`，再执行 `cd infra/docker && docker compose up -d`。

## 6. 详细文档
*   [API 文档](./docs/api.md)
*   [实施执行文档](./docs/project/IMPLEMENTATION.md)
*   [故障排查指南](./docs/TROUBLESHOOTING.md)
