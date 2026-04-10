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
cd mock-server
npm install
npm start
```

Mock 服务将在 http://localhost:3001 启动

## 项目结构

```
frontend/
├── src/
│   ├── pages/              # 页面组件
│   │   ├── devices/        # 设备管理
│   │   ├── screen/         # 投屏控制
│   │   ├── scripts/        # 脚本管理
│   │   └── reports/        # 报告中心
│   ├── components/         # 公共组件
│   │   ├── ScreenPlayer/   # WebRTC播放器
│   │   ├── DeviceCard/     # 设备卡片
│   │   └── CodeEditor/     # 代码编辑器
│   ├── services/           # API调用
│   ├── stores/             # Zustand状态
│   ├── types/              # 类型定义
│   ├── App.tsx             # 主应用
│   └── main.tsx            # 入口文件
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## 功能特性

### 设备管理
- 设备列表展示 (卡片/列表视图)
- 设备详情查看
- 设备占用/释放
- 设备筛选和搜索

### 投屏控制
- WebRTC 实时投屏
- 触控交互
- 快捷操作
- 手势模拟

### 脚本管理
- 脚本列表
- 脚本编辑 (Monaco Editor)
- 脚本运行
- 多语言支持 (Python/JavaScript/Shell)

### 测试报告
- 报告列表
- 报告详情
- 统计分析
- 报告下载

## API 代理

开发环境 API 请求会自动代理到 Mock 服务 (http://localhost:3001)

配置在 `vite.config.ts` 中：

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:3001',
      changeOrigin: true,
    },
  },
}
```

## 构建生产版本

```bash
npm run build
```

构建产物将输出到 `dist` 目录
