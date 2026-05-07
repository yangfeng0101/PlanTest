# Device Farm Frontend

设备农场管理平台前端应用

## 技术栈

- React 18 + TypeScript
- Vite (构建工具)
- Zustand (状态管理)
- Ant Design 5.x (UI组件)
- React Router (路由)
- Monaco Editor (代码编辑器)

## 快速开始

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

应用将在 http://localhost:3000 启动

### 启动 Mock 服务

在另一个终端中：

```bash
cd infra/mock
npm install
npm start
```

Mock 服务将在 http://localhost:3000 启动

## 项目结构

```
frontend/
├── src/
│   ├── pages/              # 页面组件 (devices, screen, scripts, reports, auth 等)
│   ├── components/         # 公共组件 (WebrtcPlayer, DeviceCard, CodeEditor 等)
│   ├── services/           # API 调用 (封装 axios)
│   ├── stores/             # Zustand 状态 (authStore, deviceStore 等)
│   ├── types/              # 类型定义
│   ├── App.tsx             # 主应用路由与守卫
│   └── main.tsx            # 入口文件
├── package.json
├── vite.config.ts          # 代理配置 (8001/8002/8003)
└── tsconfig.json
```

## 功能特性

### 设备管理
- 设备列表展示 (卡片/列表视图)
- 设备详情查看
- 设备占用/释放、设备预约
- 设备分组管理

### 投屏控制
- LiveKit WebRTC 实时投屏
- 低延迟触控交互
- Android 原生控件获取、控件框叠加和选择器属性查看
- 手势模拟、截图与视频录制
- 截图与视频录制

### 脚本管理
- 脚本列表与编辑 (Monaco Editor)
- 测试任务调度 (支持并行执行、定时任务)
- Python 脚本 SDK 补全，包含 Appium 定位、投屏页运行调试和 Midscene `app.ai_xxx()` 方法

## API 代理

开发环境通过 Vite 代理访问服务，配置在 `vite.config.ts` 中：

| 模块 | 处理端口 | 代理路径 |
|------|----------|----------|
| **device-svc** | `8001` | `/api/v1/devices`, `/api/v1/groups` |
| **screen-svc** | `8002` | `/ws`, `/api/v1/devices/:id/screen` |
| **test-svc** | `8003` | `/api/v1/auth`, `/api/v1/scripts`, `/api/v1/tasks` |

## 构建生产版本

```bash
npm run build
```

构建产物将输出到 `dist` 目录
