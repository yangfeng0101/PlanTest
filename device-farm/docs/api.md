# 设备农场 API 文档

## 概述

设备农场管理平台提供设备管理、投屏控制、自动化测试等功能。平台采用微服务架构，前端通过统一代理访问各个服务。

## 服务端口分配

在开发环境下，API 通过以下端口进行路由：

| 服务 | 端口 | 处理路径 | 描述 |
|------|------|----------|------|
| **device-svc** | `8001` | `/api/v1/devices`, `/api/v1/groups` | 设备注册、状态管理、预约、分组 |
| **screen-svc** | `8002` | `/ws`, `/api/v1/devices/:id/screen` | WebRTC/MJPEG 投屏、远程控制、文件传输 |
| **test-svc** | `8003` | `/api/v1/auth`, `/api/v1/scripts`, `/api/v1/tasks` | 用户认证、脚本管理、任务执行、报告 |

## 核心 API 端点

### 1. 用户认证 (Auth)
*   `POST /api/v1/auth/login`: 用户登录
*   `POST /api/v1/auth/register`: 用户注册
*   `GET /api/v1/auth/me`: 获取当前用户信息

### 2. 设备管理 (Devices)
*   `GET /api/v1/devices`: 获取设备列表
*   `POST /api/v1/devices/:id/acquire`: 占用设备
*   `POST /api/v1/devices/:id/release`: 释放设备
*   `POST /api/v1/devices/:id/reserve`: 预约设备

### 3. 投屏与控制 (Screen)
*   `WS /ws/screen/:id`: WebRTC/MJPEG 视频流
*   `POST /api/v1/devices/:id/screen/input`: 发送点击/滑动事件
*   `POST /api/v1/devices/:id/screen/shell`: 执行 Adb Shell 命令

### 4. 自动化测试 (Tasks)
*   `POST /api/v1/tasks`: 创建测试任务
*   `GET /api/v1/tasks/:id/log`: 获取实时执行日志
*   `GET /api/v1/reports/:id`: 获取测试报告详情

## 数据模型

### Device
```json
{
  "id": "device-001",
  "serial": "ABC123456789",
  "platform": "android",
  "model": "Pixel 6",
  "status": "online"
}
```

## 完整 API 规范
详细的 OpenAPI 规范请参考项目中的 `infra/api/api-spec.yaml`。
