# 统一真机自动化测试平台 (Device Farm)

## 1. 项目简介
Device Farm 是一套企业级的真机自动化测试管理平台，支持 Android、iOS 和鸿蒙 (HarmonyOS) 设备的远程控制、投屏管理以及自动化测试执行。

## 2. 核心技术栈 (Technology Stack)
*   **前端 (Frontend)**: React + Vite + TypeScript + LiveKit WebRTC 播放器
*   **设备管理 (`device-svc`)**: Python + FastAPI/Uvicorn (处理设备连接、状态、预约、分组)
*   **投屏与视频流 (`screen-svc`)**: Go + scrcpy + LiveKit SFU + WebRTC DataChannel
*   **自动化引擎 (`test-svc`)**: Python + Celery + Appium/Node.js (任务调度与执行)
*   **数据统计 (`report-svc`)**: Python (报表生成、告警、导出)
*   **AI 操作 Runner (`midscene-runner`)**: Node.js + Midscene Android (脚本内自然语言操作、定位、等待、断言)
*   **基础设施**: PostgreSQL, Redis, MinIO, Nginx, Docker

## 3. 项目架构目录树 (Architecture)
```text
device-farm/
├── frontend/                 # Web 前端应用 (React + Vite)
├── services/                 # 后端微服务群
│   ├── device-svc/           # 设备管理服务 (Port: 8001)
│   ├── screen-svc/           # LiveKit/scrcpy 投屏与远程控制服务 (Port: 8002)
│   ├── test-svc/             # 测试执行与调度引擎 (Port: 8003)
│   ├── report-svc/           # 报表与告警服务
│   ├── midscene-runner/      # Midscene AI 操作执行器
│   └── shared/               # 服务间共享组件
├── infra/                    # 基础设施 (Docker, Nginx, SQL 脚本, API 规范)
├── docs/                     # 项目详细文档 (Architecture, API, Troubleshooting)
└── dev.sh                    # 开发者一键启动脚本
```

## 4. 服务端口分配 (Development Environment)
| 服务 | 端口 | 处理路径 |
|------|------|----------|
| **device-svc** | `8001` | `/api/v1/devices`, `/api/v1/groups` |
| **screen-svc** | `8002` | `/api/v1/health`, `/api/v1/sessions/:device_id/*` |
| **livekit** | `7880`, `7881`, `50000-50100/udp` | WebRTC 信令、TCP/UDP 媒体传输 |
| **test-svc** | `8003` | `/api/v1/auth`, `/api/v1/scripts`, `/api/v1/tasks` |
| **midscene-runner** | `8005` | Docker 内网服务，不映射宿主机端口 |
| **frontend** | `3000` | (Vite 开发服务器) |

## 5. 快速开始 (Quick Start)
1.  **配置环境变量**: `cp .env.example .env` (可选，`./dev.sh` 会自动创建)
2.  **启动开发环境**: 运行 `./dev.sh start`。脚本会自动探测本机局域网 IP，并写入 `LIVEKIT_PUBLIC_HOST`，用于手机端访问 WebRTC 视频流。
3.  **切换 Wi-Fi 后重启**: 重新执行 `./dev.sh start`，让 `LIVEKIT_PUBLIC_HOST` 更新为当前网段 IP。
4.  **手动启动 Docker**: 如果不用脚本，请先在 `infra/docker/.env` 中设置当前局域网 IP，例如 `LIVEKIT_PUBLIC_HOST=192.168.3.74`，再执行 `cd infra/docker && docker compose up -d`。
5.  **启用 AI 脚本能力**: 在 `.env` / `infra/docker/.env` 中配置 `MIDSCENE_MODEL_NAME`、`MIDSCENE_MODEL_BASE_URL`、`MIDSCENE_MODEL_API_KEY`、`MIDSCENE_MODEL_FAMILY` 后重建 `midscene-runner` 和 `test-worker`。模型密钥只在后端容器内使用，不会暴露到前端。

## 6. 详细文档
*   [API 文档](./docs/api.md)
*   [项目目录说明](./docs/PROJECT_STRUCTURE.md)
*   [iOS Agent 本机配置](./docs/deployment/IOS_AGENT_SETUP.md)
*   [实施执行文档](./docs/project/IMPLEMENTATION.md)
*   [故障排查指南](./docs/TROUBLESHOOTING.md)
