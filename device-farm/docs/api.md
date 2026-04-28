# 设备农场 API 文档

## 概述

设备农场管理平台提供设备管理、投屏控制、自动化测试等功能。平台采用微服务架构，前端通过统一代理访问各个服务。

## 服务端口分配

在开发环境下，API 通过以下端口进行路由：

| 服务 | 端口 | 处理路径 | 描述 |
|------|------|----------|------|
| **device-svc** | `8001` | `/api/v1/devices`, `/api/v1/groups` | 设备注册、状态管理、预约、分组 |
| **screen-svc** | `8002` | `/api/v1/sessions/:device_id/*` | LiveKit/scrcpy 投屏、远程控制会话 |
| **livekit** | `7880`, `7881`, `50000-50100/udp` | WebRTC 信令与媒体转发 |
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
*   `GET /api/v1/devices/:id/ui-hierarchy`: 获取当前屏幕控件树和自动化选择器建议

`ui-hierarchy` 基于设备 `capabilities.ui_hierarchy` 判断是否可用。Android 设备和通过 ADB 接入的 HarmonyOS 手机使用 Android UIAutomator dump 获取原生控件信息，返回 `resource_id`、`text`、`content_desc`、`class_name`、`bounds`、`center`、`xpath` 和 `selector_suggestions`。结果不持久化。

### 3. 投屏与控制 (Screen)
*   `GET /api/v1/health`: screen-svc 健康检查
*   `GET /api/v1/sessions/:device_id`: 查询设备当前投屏会话
*   `POST /api/v1/sessions/:device_id/start`: 启动投屏会话，返回 `livekit_url`、`token`、`room_name`、视频宽高
*   `POST /api/v1/sessions/:device_id/stop`: 停止投屏会话
*   LiveKit DataChannel `topic=control`: 发送远程控制事件，消息格式如下：

```json
{ "type": "touch", "action": "down", "x": 120, "y": 360 }
```

支持的控制类型：
*   `touch`: `action` 为 `down`、`move`、`up`
*   `key`: Android keycode，例如 `KEYCODE_HOME=3`、`KEYCODE_BACK=4`
*   `text`: 文本输入

### 4. 自动化测试 (Tasks)
*   `POST /api/v1/tasks`: 创建测试任务
*   `GET /api/v1/tasks/:id/log`: 获取实时执行日志
*   `GET /api/v1/reports/:id`: 获取测试报告详情

## 数据模型

### Device
```json
{
  "id": "device-001",
  "name": "华为 P50 Pro",
  "model": "JAD-AL50",
  "brand": "HUAWEI",
  "os": "harmony",
  "os_version": "4.2.0",
  "display_os": "HarmonyOS",
  "display_os_version": "4.2.0",
  "connection_type": "adb",
  "drivers": {
    "metrics": "adb",
    "screen": "scrcpy",
    "ui_hierarchy": "uiautomator",
    "control": "scrcpy"
  },
  "capabilities": {
    "screen_mirror": true,
    "remote_control": true,
    "ui_hierarchy": true,
    "metrics": true,
    "screenshot": true,
    "app_management": true
  },
  "status": "online"
}
```

`os/os_version` 保留兼容；新前端和新能力判断应优先使用 `display_os/display_os_version` 做展示，使用 `drivers/capabilities` 判断实际可用能力。通过 ADB 接入的 HarmonyOS 手机属于 Android-compatible 设备，不等同于 HDC 接入。

## 完整 API 规范
详细的 OpenAPI 规范请参考项目中的 `infra/api/api-spec.yaml`。
