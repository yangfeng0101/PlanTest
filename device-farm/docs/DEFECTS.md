# Phase 1 代码缺陷报告

> 评审日期: 2026-04-09
> 评审范围: Phase 1 实施的所有代码变更
> 评审状态: 待修复

---

## 一、缺陷统计

| 严重程度 | 数量 | 说明 |
|----------|------|------|
| Critical (严重) | 6 | 必须在生产部署前修复 |
| Important (重要) | 12 | 建议尽快修复 |
| Suggestion (建议) | 8 | 可在后续迭代修复 |
| **总计** | **26** | |

---

## 二、严重缺陷 (Critical)

### DEF-001: Python exec() 代码注入漏洞

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/tasks/executor.py` |
| 行号 | 217-232 |
| 类型 | 安全漏洞 |
| 影响 | 远程代码执行 |

**问题描述:**

用户提供的 Python 脚本通过 `exec()` 直接执行，无任何沙箱隔离。恶意脚本可以：
- 读取环境变量（包括密钥）
- 访问文件系统
- 执行系统命令

```python
# 当前代码
exec(compile(f.read(), temp_path, "exec"), namespace)

# namespace 提供了 __builtins__，可访问危险函数
```

**修复建议:**

1. 使用 RestrictedPython 或类似库限制可用函数
2. 在 Docker 容器中执行脚本，限制资源访问
3. 移除 `__builtins__` 或提供白名单版本

```python
# 推荐方案
safe_builtins = {
    'print': print,
    'len': len,
    'range': range,
    # 只添加安全的内置函数
}
namespace = {'__builtins__': safe_builtins, ...}
```

---

### DEF-002: JavaScript 代码注入漏洞

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/executors/javascript.py` |
| 行号 | 38, 63-162 |
| 类型 | 安全漏洞 |
| 影响 | 远程代码执行 |

**问题描述:**

用户提供的 JavaScript 代码直接嵌入执行包装器，无任何限制。恶意脚本可以：
- 通过 `require('child_process')` 执行系统命令
- 读取环境变量 `process.env`
- 访问文件系统 `require('fs')`

```python
# 当前代码 (line 132)
{test_code}

# 直接嵌入，无任何过滤
```

**修复建议:**

1. 使用 `isolated-vm` 创建沙箱环境
2. 在受限 Docker 容器中执行
3. 限制 Node.js 模块访问

```python
# 推荐方案：使用 isolated-vm
# 或在 Kubernetes Pod 中执行，配置安全上下文
```

---

### DEF-003: Go 类型断言 Panic

| 属性 | 值 |
|------|-----|
| 文件 | `services/screen-svc/internal/handler/manager.go` |
| 行号 | 184-186, 190-191, 195-196, 198-203 |
| 类型 | 程序崩溃 |
| 影响 | 服务拒绝 |

**问题描述:**

JSON 解析后的值直接类型断言，无检查。畸形输入会导致 panic。

```go
// 当前代码
x := int(msg["x"].(float64))  // 如果 x 不存在或不是 float64，panic
y := int(msg["y"].(float64))
action := msg["action"].(string)
```

**修复建议:**

```go
// 修复后
xVal, ok := msg["x"].(float64)
if !ok {
    m.logger.Warnf("Invalid or missing x coordinate")
    return
}
x := int(xVal)

yVal, ok := msg["y"].(float64)
if !ok {
    m.logger.Warnf("Invalid or missing y coordinate")
    return
}
y := int(yVal)

action, ok := msg["action"].(string)
if !ok {
    m.logger.Warnf("Invalid or missing action")
    return
}
```

---

### DEF-004: MinIO 同步操作阻塞异步事件循环

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/services/storage.py` |
| 行号 | 63-76, 114-122 |
| 类型 | 性能问题 |
| 影响 | 服务阻塞 |

**问题描述:**

MinIO Python SDK 的 `put_object` 是同步方法，但在 async 函数中直接调用，会阻塞整个事件循环。

```python
# 当前代码
async def upload_screenshot_bytes(self, ...):
    self.client.put_object(...)  # 阻塞！
```

**修复建议:**

```python
import asyncio

async def upload_screenshot_bytes(self, ...):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: self.client.put_object(...)
    )
```

---

### DEF-005: asyncio.run() 在同步上下文调用

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/api/tasks.py` |
| 行号 | 299-306 |
| 类型 | 运行时错误 |
| 影响 | 任务执行失败 |

**问题描述:**

`asyncio.run()` 会创建新的事件循环，如果当前已有事件循环（如 Celery Worker），会失败。

```python
# 当前代码
def update_task_status(task_id: str, status: TaskStatus, **kwargs):
    return asyncio.run(update_task_status_db(...))

def get_task_by_id(task_id: str):
    return asyncio.run(_get_task_by_id_async(task_id))
```

**修复建议:**

```python
import nest_asyncio
nest_asyncio.apply()

# 或者使用 Celery 的异步支持
from celery.contrib.asyncio import async_to_sync

@async_to_sync
async def update_task_status(task_id: str, status: TaskStatus, **kwargs):
    ...
```

---

### DEF-006: SQL 注入风险

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/database.py` |
| 行号 | 77 |
| 类型 | 安全漏洞 |
| 影响 | 潜在 SQL 注入 |

**问题描述:**

健康检查使用原始字符串执行 SQL，虽然当前无用户输入，但不符合最佳实践。

```python
# 当前代码
await conn.execute("SELECT 1")
```

**修复建议:**

```python
from sqlalchemy import text

await conn.execute(text("SELECT 1"))
```

---

## 三、重要缺陷 (Important)

### DEF-007: RTP 序列号溢出未处理

| 属性 | 值 |
|------|-----|
| 文件 | `services/screen-svc/internal/video/rtp_packer.go` |
| 行号 | 79, 140 |
| 类型 | 逻辑错误 |
| 影响 | 视频流中断 |

**问题描述:**

RTP 序列号是 uint16，达到 65535 后应回绕，但当前实现只是简单递增。

```go
// 当前代码
p.sequenceNumber++
```

**修复建议:**

```go
p.sequenceNumber = (p.sequenceNumber + 1) & 0xFFFF
```

---

### DEF-008: WebRTC 空指针引用

| 属性 | 值 |
|------|-----|
| 文件 | `services/screen-svc/internal/webrtc/webrtc.go` |
| 行号 | 207 |
| 类型 | 程序崩溃 |
| 影响 | 服务崩溃 |

**问题描述:**

`videoTrack.WriteRTP` 调用前未检查 `videoTrack` 是否为 nil。

**修复建议:**

```go
func (m *Manager) SendVideo(data []byte) error {
    m.mutex.RLock()
    defer m.mutex.RUnlock()

    if m.videoTrack == nil {
        return errors.New("video track not initialized")
    }
    // ...
}
```

---

### DEF-009: WebRTC 信令错误未处理

| 属性 | 值 |
|------|-----|
| 文件 | `services/screen-svc/internal/webrtc/webrtc.go` |
| 行号 | 392 |
| 类型 | 错误处理缺失 |
| 影响 | 客户端状态不一致 |

**问题描述:**

`conn.WriteJSON(response)` 错误被忽略。

**修复建议:**

```go
if err := conn.WriteJSON(response); err != nil {
    m.logger.Errorf("Failed to send response: %v", err)
    return
}
```

---

### DEF-010: 硬编码 STUN 服务器

| 属性 | 值 |
|------|-----|
| 文件 | `services/screen-svc/internal/webrtc/webrtc.go` |
| 行号 | 288 |
| 类型 | 配置问题 |
| 影响 | 生产部署困难 |

**问题描述:**

STUN 服务器地址硬编码，无法配置。

```go
URLs: []string{"stun:stun.l.google.com:19302"}
```

**修复建议:**

从配置文件读取 STUN/TURN 服务器列表。

---

### DEF-011: Goroutine 泄漏

| 属性 | 值 |
|------|-----|
| 文件 | `services/screen-svc/internal/handler/manager.go` |
| 行号 | 71 |
| 类型 | 资源泄漏 |
| 影响 | 内存泄漏 |

**问题描述:**

`go m.streamVideo(...)` 启动的协程无取消机制。

**修复建议:**

使用 `context.Context` 控制协程生命周期。

```go
ctx, cancel := context.WithCancel(context.Background())
go m.streamVideo(ctx, ...)

// 在 StopSession 中调用 cancel()
```

---

### DEF-012: WebRTC 播放器内存泄漏

| 属性 | 值 |
|------|-----|
| 文件 | `frontend/src/components/WebrtcPlayer/index.tsx` |
| 行号 | 260-263 |
| 类型 | 内存泄漏 |
| 影响 | 浏览器内存增长 |

**问题描述:**

useEffect 依赖数组为空，但 `startConnection` 依赖多个 props。

**修复建议:**

```typescript
useEffect(() => {
  startConnection()
  return stopConnection
}, [deviceId, wsUrl]) // 添加依赖
```

---

### DEF-013: FPS 计算错误

| 属性 | 值 |
|------|-----|
| 文件 | `frontend/src/components/WebrtcPlayer/index.tsx` |
| 行号 | 239-241 |
| 类型 | 逻辑错误 |
| 影响 | FPS 显示不准确 |

**问题描述:**

FPS 从总字节数估算，不是有效测量。

```typescript
const fps = Math.round(bytesReceived / 10000) // 无意义
```

**修复建议:**

使用 WebRTC `getStats()` 获取真实帧率。

```typescript
const stats = await pc.getStats()
stats.forEach(report => {
  if (report.type === 'inbound-rtp' && report.kind === 'video') {
    setFps(report.framesPerSecond || 0)
  }
})
```

---

### DEF-014: WebRTC 缺少重连逻辑

| 属性 | 值 |
|------|-----|
| 文件 | `frontend/src/components/WebrtcPlayer/index.tsx` |
| 行号 | 全文件 |
| 类型 | 功能缺失 |
| 影响 | 连接断开需刷新页面 |

**问题描述:**

连接失败后无自动重连机制。

**修复建议:**

实现指数退避重连策略。

---

### DEF-015: 触摸坐标计算错误

| 属性 | 值 |
|------|-----|
| 文件 | `frontend/src/components/TouchOverlay/index.tsx` |
| 行号 | 93-95 |
| 类型 | 逻辑错误 |
| 影响 | 触摸位置偏移 |

**问题描述:**

使用 `e.target` 获取边界，但 target 可能是子元素。

**修复建议:**

```typescript
const containerRef = useRef<HTMLDivElement>(null)

const handlePointerDown = (e: React.PointerEvent) => {
  if (!containerRef.current) return
  const rect = containerRef.current.getBoundingClientRect()
  // ...
}
```

---

### DEF-016: 长按定时器内存泄漏

| 属性 | 值 |
|------|-----|
| 文件 | `frontend/src/components/TouchOverlay/index.tsx` |
| 行号 | 113-120 |
| 类型 | 内存泄漏 |
| 影响 | 组件卸载后定时器仍触发 |

**问题描述:**

长按定时器在组件卸载时未清理。

**修复建议:**

```typescript
useEffect(() => {
  return () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current)
    }
  }
}, [])
```

---

### DEF-017: 前端 URL 硬编码

| 属性 | 值 |
|------|-----|
| 文件 | `frontend/src/pages/screen/index.tsx` |
| 行号 | 18-20 |
| 类型 | 配置问题 |
| 影响 | 环境切换困难 |

**问题描述:**

服务 URL 硬编码为 localhost。

```typescript
const SCREEN_WS_URL = 'ws://localhost:8082'
const SCREEN_HTTP_URL = 'http://localhost:8082'
```

**修复建议:**

```typescript
const SCREEN_WS_URL = import.meta.env.VITE_SCREEN_WS_URL || 'ws://localhost:8082'
const SCREEN_HTTP_URL = import.meta.env.VITE_SCREEN_HTTP_URL || 'http://localhost:8082'
```

---

### DEF-018: API 缺少认证

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/api/tasks.py` |
| 行号 | 全文件 |
| 类型 | 安全漏洞 |
| 影响 | 未授权访问 |

**问题描述:**

所有 API 端点无认证保护。

**修复建议:**

添加 JWT 或 API Key 认证中间件。

---

## 四、建议改进 (Suggestion)

### DEF-019: NAL 解析器缺少长度上限

| 文件 | `services/screen-svc/internal/video/nal_parser.go` |
| 行号 | 131-137 |
| 问题 | 无 NAL 长度上限检查，可能导致内存耗尽 |

### DEF-020: RTP Packer 缺少线程安全

| 文件 | `services/screen-svc/internal/video/rtp_packer.go` |
| 问题 | `RTPPacker` 可变字段无同步保护 |

### DEF-021: 触摸移动事件未防抖

| 文件 | `frontend/src/components/TouchOverlay/index.tsx` |
| 问题 | `handlePointerMove` 每像素触发，性能差 |

### DEF-022: 数据库缺少索引

| 文件 | `services/test-svc/app/models/database.py` |
| 问题 | `started_at`、`finished_at` 字段缺少索引 |

### DEF-023: UUID 默认值问题

| 文件 | `services/test-svc/app/models/database.py` |
| 行号 | 42 |
| 问题 | `default=lambda: str(uuid.uuid4())` 应使用 `default_factory` |

### DEF-024: WebSocket 错误未日志

| 文件 | `services/test-svc/app/api/tasks.py` |
| 行号 | 77-79 |
| 问题 | WebSocket 异常被静默捕获 |

### DEF-025: Python 脚本缺少超时

| 文件 | `services/test-svc/app/tasks/executor.py` |
| 问题 | Python 脚本执行无超时限制 |

### DEF-026: 缺少单元测试

| 范围 | 全项目 |
| 问题 | Phase 1 实现缺少单元测试覆盖 |

---

## 五、修复计划

### Phase 1: 安全修复 (本周)

| 缺陷编号 | 描述 | 负责人 | 状态 |
|----------|------|--------|------|
| DEF-001 | Python exec 代码注入 | - | ✅ 已修复 |
| DEF-002 | JavaScript 代码注入 | - | ✅ 已修复 |
| DEF-003 | Go 类型断言 panic | - | ✅ 已修复 |
| DEF-018 | API 认证缺失 | - | ✅ 已修复 |

### Phase 2: 稳定性修复 (下周)

| 缺陷编号 | 描述 | 负责人 | 状态 |
|----------|------|--------|------|
| DEF-004 | MinIO 同步阻塞 | - | ✅ 已修复 |
| DEF-005 | asyncio.run 问题 | - | ✅ 已修复 |
| DEF-007 | RTP 序列号溢出 | - | ✅ 已修复 |
| DEF-008 | WebRTC 空指针 | - | ✅ 已修复 |
| DEF-011 | Goroutine 泄漏 | - | ✅ 已修复 |

### Phase 3: 功能完善 (后续)

| 缺陷编号 | 描述 | 负责人 | 状态 |
|----------|------|--------|------|
| DEF-010 | STUN 服务器硬编码 | - | ✅ 已修复 |
| DEF-012 | WebRTC 内存泄漏 | - | ✅ 已修复 |
| DEF-013 | FPS 计算错误 | - | ✅ 已修复 |
| DEF-014 | WebRTC 重连 | - | ✅ 已修复 |
| DEF-015 | 触摸坐标错误 | - | ✅ 已修复 |
| DEF-016 | 长按定时器泄漏 | - | ✅ 已修复 |
| DEF-017 | URL 硬编码 | - | ✅ 已修复 |

---

## 六、测试建议

修复后需添加以下单元测试：

### Go 测试

```
services/screen-svc/internal/video/nal_parser_test.go
services/screen-svc/internal/video/rtp_packer_test.go
services/screen-svc/internal/webrtc/webrtc_test.go
```

### Python 测试

```
services/test-svc/tests/test_database.py
services/test-svc/tests/test_storage.py
services/test-svc/tests/test_executors.py
```

### 前端测试

```
frontend/src/components/WebrtcPlayer/index.test.tsx
frontend/src/components/TouchOverlay/index.test.tsx
```

---

## 七、附录

### A. 代码扫描工具建议

- Go: `golangci-lint`
- Python: `pylint`, `bandit` (安全扫描)
- TypeScript: `eslint`, `tslint`

### B. CI/CD 集成建议

1. 代码提交时运行 linter
2. PR 时运行单元测试
3. 合并前进行安全扫描
4. 部署前运行集成测试

### C. 安全审计建议

1. 第三方安全审计
2. 渗透测试
3. 依赖漏洞扫描 (`npm audit`, `pip-audit`)
