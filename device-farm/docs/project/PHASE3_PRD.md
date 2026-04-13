# Device Farm Phase 3 - Product Requirements Document

## Project Overview

**Project Name:** Device Farm Phase 3 - 核心功能完善与 AI 智能化
**Branch Name:** phase3-features
**Version:** 1.0.0
**Created:** 2026-04-10

## Background

Phase 1 完成了 Android 设备管理和 WebRTC 投屏核心功能。Phase 2 完成了 iOS 和鸿蒙设备支持。Phase 3 将完善企业级功能并引入 AI 智能化能力。

## Goals

1. 实现设备预约和调度系统，支持多用户协作
2. 支持定时任务和并行执行，提升测试效率
3. 实现用户认证和权限管理
4. 引入 AI 能力，支持智能用例生成和元素定位

## User Stories

### RESERVATION-001: 设备预约数据模型

**Priority:** 1
**Acceptance Criteria:**
- 创建 DeviceReservation 数据库模型
- 包含字段：device_id, user_id, start_time, end_time, status, purpose
- 支持预约状态：pending, active, completed, cancelled
- 添加数据库索引优化查询性能

**Files:**
- `services/device-svc/app/models/reservation.py`
- `services/device-svc/app/database.py`

---

### RESERVATION-002: 设备预约 API

**Priority:** 2
**Acceptance Criteria:**
- POST /api/v1/devices/{id}/reserve - 创建预约
- DELETE /api/v1/devices/{id}/reserve - 取消预约
- GET /api/v1/reservations - 获取预约列表
- 验证设备可用性（不能重复预约）
- 支持预约时间冲突检测

**Files:**
- `services/device-svc/app/routes/reservations.py`
- `services/device-svc/app/services/reservation_service.py`

---

### RESERVATION-003: 预约队列与自动释放

**Priority:** 3
**Acceptance Criteria:**
- 实现预约队列逻辑（先到先得）
- 预约到期自动释放设备
- 预约开始前 5 分钟提醒用户
- 支持预约续期（最多延长 1 小时）

**Files:**
- `services/device-svc/app/services/reservation_service.py`
- `services/device-svc/app/tasks/reservation_tasks.py`

---

### SCHEDULE-001: Celery Beat 定时任务配置

**Priority:** 4
**Acceptance Criteria:**
- 配置 Celery Beat 作为任务调度器
- 支持 Cron 表达式定义执行时间
- 支持间隔执行（每隔 N 秒/分钟/小时）
- 支持一次性定时任务

**Files:**
- `services/test-svc/app/tasks/scheduler.py`
- `services/test-svc/app/config.py`

---

### SCHEDULE-002: 定时任务管理 API

**Priority:** 5
**Acceptance Criteria:**
- POST /api/v1/schedules - 创建定时任务
- GET /api/v1/schedules - 获取定时任务列表
- PUT /api/v1/schedules/{id} - 更新定时任务
- DELETE /api/v1/schedules/{id} - 删除定时任务
- POST /api/v1/schedules/{id}/enable - 启用/禁用

**Files:**
- `services/test-svc/app/api/schedules.py`
- `services/test-svc/app/models/schedule.py`

---

### PARALLEL-001: 多设备并行执行

**Priority:** 6
**Acceptance Criteria:**
- 支持选择多个设备同时执行同一脚本
- 实现任务分发逻辑
- 并发数可配置（默认 5 个并行）
- 支持设备选择策略（全部/随机/指定）

**Files:**
- `services/test-svc/app/services/parallel_executor.py`
- `services/test-svc/app/api/tasks.py`

---

### PARALLEL-002: 并行结果聚合

**Priority:** 7
**Acceptance Criteria:**
- 聚合多设备执行结果
- 生成汇总报告（通过率、失败设备列表）
- 支持按设备维度查看详细日志
- 前端展示并行执行进度

**Files:**
- `services/test-svc/app/services/result_aggregator.py`
- `services/report-svc/app/services/aggregator.py`

---

### AUTH-001: 用户数据模型与 JWT

**Priority:** 8
**Acceptance Criteria:**
- 创建 User 数据库模型（username, email, role, password_hash）
- 实现 JWT Token 生成和验证
- 支持 Access Token（2小时）和 Refresh Token（7天）
- 密码使用 bcrypt 加密存储

**Files:**
- `services/test-svc/app/models/user.py`
- `services/test-svc/app/services/jwt_service.py`
- `services/test-svc/app/services/password_service.py`

---

### AUTH-002: 用户认证 API

**Priority:** 9
**Acceptance Criteria:**
- POST /api/v1/auth/register - 用户注册
- POST /api/v1/auth/login - 用户登录
- POST /api/v1/auth/refresh - 刷新 Token
- POST /api/v1/auth/logout - 用户登出
- GET /api/v1/auth/me - 获取当前用户信息

**Files:**
- `services/test-svc/app/api/auth.py`
- `services/test-svc/app/services/auth_service.py`

---

### AUTH-003: 权限控制与前端登录

**Priority:** 10
**Acceptance Criteria:**
- 实现基于角色的权限控制（admin, user, viewer）
- 前端登录页面实现
- Token 存储在 localStorage
- 路由守卫保护需要认证的页面
- 登录状态持久化

**Files:**
- `services/test-svc/app/middleware/rbac.py`
- `frontend/src/pages/auth/Login.tsx`
- `frontend/src/stores/authStore.ts`
- `frontend/src/components/AuthGuard.tsx`

---

### GROUP-001: 设备分组管理

**Priority:** 11
**Acceptance Criteria:**
- 创建 DeviceGroup 数据模型
- 支持创建、编辑、删除分组
- 设备可以属于多个分组
- 支持按分组筛选设备

**Files:**
- `services/device-svc/app/models/group.py`
- `services/device-svc/app/routes/groups.py`

---

### STATS-001: 使用统计报表

**Priority:** 12
**Acceptance Criteria:**
- 记录设备使用时长
- 统计任务执行次数和成功率
- 生成日报、周报、月报
- 支持按设备、用户、时间范围筛选

**Files:**
- `services/report-svc/app/services/statistics.py`
- `services/report-svc/app/api/statistics.py`

---

### STATS-002: 趋势分析图表

**Priority:** 13
**Acceptance Criteria:**
- 前端实现趋势图表组件
- 支持任务成功率趋势
- 支持设备使用率趋势
- 支持响应时间分布图
- 使用 ECharts 或 Recharts 绑定

**Files:**
- `frontend/src/components/TrendChart/index.tsx`
- `frontend/src/pages/reports/Trend.tsx`

---

### ALERT-001: 告警通知系统

**Priority:** 14
**Acceptance Criteria:**
- 创建 Alert 数据模型
- 支持告警规则配置（设备离线、任务失败率超阈值）
- 支持飞书/钉钉 Webhook 通知
- 支持邮件通知
- 告警历史记录

**Files:**
- `services/report-svc/app/services/alert.py`
- `services/report-svc/app/models/alert.py`
- `services/report-svc/app/api/alerts.py`

---

### EXPORT-001: 数据导出功能

**Priority:** 15
**Acceptance Criteria:**
- 支持导出测试报告为 PDF
- 支持导出执行日志为 Excel
- 支持导出统计数据为 CSV
- 支持批量导出

**Files:**
- `services/report-svc/app/services/export.py`
- `services/report-svc/app/api/export.py`

---

### AI-001: OCR 引擎集成

**Priority:** 16
**Acceptance Criteria:**
- 集成 PaddleOCR 或 Tesseract
- 实现 OCR API（图片 -> 文本）
- 支持中英文识别
- 返回文本位置坐标

**Files:**
- `services/ai-svc/app/main.py`
- `services/ai-svc/app/services/ocr.py`
- `services/ai-svc/requirements.txt`

---

### AI-002: AI 元素定位

**Priority:** 17
**Acceptance Criteria:**
- 实现基于描述的元素定位
- 支持自然语言查询（如"点击登录按钮"）
- 返回元素坐标和置信度
- 支持相似元素匹配

**Files:**
- `services/ai-svc/app/services/element_locator.py`
- `services/ai-svc/app/api/locate.py`

---

### AI-003: 智能用例生成

**Priority:** 18
**Acceptance Criteria:**
- 支持自然语言描述生成测试用例
- 生成的用例可直接执行
- 支持用例模板库
- 支持用例优化建议

**Files:**
- `services/ai-svc/app/services/test_generator.py`
- `services/ai-svc/app/api/generate.py`

---

## Dependencies

```
RESERVATION-001 ──> RESERVATION-002 ──> RESERVATION-003
SCHEDULE-001 ──> SCHEDULE-002
PARALLEL-001 ──> PARALLEL-002
AUTH-001 ──> AUTH-002 ──> AUTH-003
GROUP-001 (独立)
STATS-001 ──> STATS-002
ALERT-001 (独立)
EXPORT-001 (独立)
AI-001 ──> AI-002 ──> AI-003
```

## Technical Notes

### 数据库迁移
- 使用 Alembic 管理数据库迁移
- 新增表：users, device_groups, reservations, schedules, alerts

### 认证方案
- JWT RS256 签名（生产环境）
- API Key 用于服务间调用

### AI 服务部署
- 需要 GPU 资源
- 支持 Docker 部署
- 模型：UI-TARS / Qwen-VL

## Testing Strategy

1. 单元测试覆盖核心业务逻辑
2. 集成测试验证 API 端点
3. E2E 测试验证前端流程
4. 性能测试验证并发能力
