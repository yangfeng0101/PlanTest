# 设备农场 API 文档

## 概述

设备农场管理平台提供设备管理、投屏控制、自动化测试等功能。

## API 端点

### 设备管理

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/v1/devices | 获取设备列表 |
| POST | /api/v1/devices | 注册新设备 |
| GET | /api/v1/devices/:id | 获取设备详情 |
| PUT | /api/v1/devices/:id | 更新设备信息 |
| DELETE | /api/v1/devices/:id | 删除设备 |
| POST | /api/v1/devices/:id/acquire | 占用设备 |
| POST | /api/v1/devices/:id/release | 释放设备 |

### 投屏控制

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/v1/devices/:id/screen/session | 创建投屏会话 |
| GET | /api/v1/devices/:id/screen/session | 获取当前会话 |
| DELETE | /api/v1/devices/:id/screen/session | 关闭会话 |
| POST | /api/v1/devices/:id/screen/input | 发送输入事件 |

### 脚本管理

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/v1/scripts | 获取脚本列表 |
| POST | /api/v1/scripts | 创建脚本 |
| GET | /api/v1/scripts/:id | 获取脚本详情 |
| PUT | /api/v1/scripts/:id | 更新脚本 |
| DELETE | /api/v1/scripts/:id | 删除脚本 |

### 测试任务

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/v1/tasks | 获取任务列表 |
| POST | /api/v1/tasks | 创建任务 |
| GET | /api/v1/tasks/:id | 获取任务详情 |
| DELETE | /api/v1/tasks/:id | 取消任务 |
| POST | /api/v1/tasks/:id/run | 执行任务 |

### 测试报告

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/v1/reports | 获取报告列表 |
| GET | /api/v1/reports/:id | 获取报告详情 |

## 数据模型

### Device

```json
{
  "id": "device-001",
  "serial": "ABC123456789",
  "platform": "android",
  "model": "Pixel 6",
  "brand": "Google",
  "osVersion": "13",
  "screenWidth": 1080,
  "screenHeight": 2400,
  "status": "online",
  "ownerId": null,
  "createdAt": "2024-01-15T08:00:00Z",
  "updatedAt": "2024-01-20T10:30:00Z"
}
```

### Script

```json
{
  "id": "script-001",
  "name": "Login Test",
  "language": "python",
  "content": "# test script...",
  "version": 1,
  "description": "Test user login flow",
  "createdBy": "user-001",
  "createdAt": "2024-01-15T08:00:00Z",
  "updatedAt": "2024-01-15T08:00:00Z"
}
```

### Task

```json
{
  "id": "task-001",
  "name": "Login Test - Pixel 6",
  "scriptId": "script-001",
  "deviceId": "device-001",
  "status": "completed",
  "priority": 0,
  "params": {},
  "startedAt": "2024-01-20T10:00:00Z",
  "finishedAt": "2024-01-20T10:01:30Z",
  "createdBy": "user-002",
  "createdAt": "2024-01-20T09:55:00Z"
}
```

### Report

```json
{
  "id": "report-001",
  "taskId": "task-001",
  "totalCases": 10,
  "passedCases": 8,
  "failedCases": 2,
  "skippedCases": 0,
  "duration": 90,
  "videoUrl": "https://minio.example.com/videos/task-001.mp4",
  "logUrl": "https://minio.example.com/logs/task-001.log",
  "reportUrl": "https://minio.example.com/reports/task-001.html",
  "summary": "Most tests passed",
  "createdAt": "2024-01-20T10:01:30Z"
}
```

## 状态枚举

### 设备状态
- `online` - 在线可用
- `offline` - 离线
- `busy` - 占用中
- `maintenance` - 维护中

### 任务状态
- `pending` - 待执行
- `running` - 执行中
- `completed` - 已完成
- `failed` - 失败
- `cancelled` - 已取消

### 测试用例状态
- `passed` - 通过
- `failed` - 失败
- `skipped` - 跳过

## 完整 API 规范

详细的 OpenAPI 规范请参考: `/infra/api/api-spec.yaml`

## Mock 服务

开发环境可使用 Mock 服务进行接口测试:

```bash
cd infra/mock
npm install
npm start
```

Mock 服务默认运行在端口 3000。
