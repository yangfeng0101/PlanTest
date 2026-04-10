# 统一真机自动化测试平台 Phase 2 实施计划

## Context

Phase 1 已完成核心功能开发，包括 WebRTC 投屏、前端投屏控制台、test-svc 数据持久化。Phase 2 重点解决代码质量问题、扩展平台支持范围、完善自动化执行能力。

**Phase 1 遗留问题：**
1. 安全漏洞：代码执行无沙箱隔离、API 无认证
2. 稳定性问题：内存泄漏、错误处理不完善
3. 功能缺失：iOS/鸿蒙不支持、Appium 未真实连接

**Phase 2 目标：**
- 修复所有 Critical 缺陷
- 完成 iOS 设备接入
- 完成鸿蒙设备接入
- 实现 Appium 真实驱动连接
- 性能优化和稳定性提升

---

## 实施步骤

### Step 0: 代码缺陷修复 (Week 1) - 必须先完成

#### 0.1 安全漏洞修复

**DEF-001: Python exec() 代码注入**

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/tasks/executor.py` |
| 优先级 | P0-Critical |

修复方案：
```python
# 方案 1: 使用受限 builtins
safe_builtins = {
    'print': print,
    'len': len,
    'range': range,
    'str': str,
    'int': int,
    'float': float,
    'bool': bool,
    'list': list,
    'dict': dict,
    'tuple': tuple,
    'None': None,
    'True': True,
    'False': False,
}

# 方案 2: 在 Docker 容器中执行 (推荐)
# 创建独立的执行容器，限制网络和文件系统访问
```

**修改文件:**
- `services/test-svc/app/tasks/executor.py` - 添加安全执行环境
- `services/test-svc/Dockerfile.executor` - 新建独立执行容器
- `infra/docker/docker-compose.yml` - 添加执行容器配置

---

**DEF-002: JavaScript 代码注入**

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/executors/javascript.py` |
| 优先级 | P0-Critical |

修复方案：
```python
# 方案 1: 使用 isolated-vm (推荐)
import ivm

async def execute_sandboxed_js(code: str):
    isolate = ivm.Isolate()
    context = await isolate.create_context()
    result = await context.eval(code)
    return result

# 方案 2: 在 Node.js 子进程 + 限制参数
# node --disable-proc --disable-os-module script.js
```

**修改文件:**
- `services/test-svc/app/executors/javascript.py` - 集成 isolated-vm
- `services/test-svc/requirements.txt` - 添加 `isolated-vm`

---

**DEF-003: Go 类型断言 Panic**

| 属性 | 值 |
|------|-----|
| 文件 | `services/screen-svc/internal/handler/manager.go` |
| 行号 | 184-203 |
| 优先级 | P0-Critical |

修复方案：
```go
// 创建输入验证辅助函数
func validateTouchMessage(msg map[string]interface{}) (x, y int, action string, err error) {
    xVal, ok := msg["x"].(float64)
    if !ok {
        return 0, 0, "", errors.New("invalid or missing x coordinate")
    }
    yVal, ok := msg["y"].(float64)
    if !ok {
        return 0, 0, "", errors.New("invalid or missing y coordinate")
    }
    action, ok = msg["action"].(string)
    if !ok {
        return 0, 0, "", errors.New("invalid or missing action")
    }
    return int(xVal), int(yVal), action, nil
}
```

---

**DEF-018: API 认证缺失**

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/api/tasks.py` 及其他 API |
| 优先级 | P0-Critical |

修复方案：
```python
# 创建认证中间件
from fastapi import Depends, HTTPException, Header
from app.services.auth import verify_token

async def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await verify_token(authorization)

# 在路由中使用
@router.post("", dependencies=[Depends(get_current_user)])
async def create_task(...):
    ...
```

**新建文件:**
- `services/test-svc/app/services/auth.py` - 认证服务
- `services/test-svc/app/middleware/auth.py` - 认证中间件

---

#### 0.2 稳定性问题修复

**DEF-004: MinIO 同步阻塞**

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/services/storage.py` |
| 优先级 | P1-Important |

修复方案：
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)

async def upload_screenshot_bytes(self, task_id: str, data: bytes, index: int):
    loop = asyncio.get_event_loop()
    object_name = f"screenshots/{task_id}/screen_{index}.png"
    
    def _upload():
        self.client.put_object(
            self.bucket_name,
            object_name,
            io.BytesIO(data),
            len(data),
            content_type="image/png"
        )
        return object_name
    
    result = await loop.run_in_executor(executor, _upload)
    return result, self.get_presigned_url(result)
```

---

**DEF-005: asyncio.run() 问题**

| 属性 | 值 |
|------|-----|
| 文件 | `services/test-svc/app/api/tasks.py` |
| 优先级 | P1-Important |

修复方案：
```python
import nest_asyncio
nest_asyncio.apply()

# 或者重构为异步 Celery 任务
from celery import Celery
from celery.contrib.asyncio import async_task

@async_task
async def update_task_status_async(task_id: str, status: TaskStatus, **kwargs):
    ...
```

---

**DEF-007: RTP 序列号溢出**

| 属性 | 值 |
|------|-----|
| 文件 | `services/screen-svc/internal/video/rtp_packer.go` |
| 优先级 | P1-Important |

修复方案：
```go
// 正确处理 uint16 溢出
func (p *RTPPacker) nextSequenceNumber() uint16 {
    p.sequenceNumber = (p.sequenceNumber + 1) & 0xFFFF
    return p.sequenceNumber
}
```

---

**DEF-008: WebRTC 空指针**

| 属性 | 值 |
|------|-----|
| 文件 | `services/screen-svc/internal/webrtc/webrtc.go` |
| 优先级 | P1-Important |

修复方案：
```go
func (m *Manager) SendVideo(data []byte) error {
    m.mutex.RLock()
    defer m.mutex.RUnlock()

    if m.videoTrack == nil {
        return errors.New("video track not initialized")
    }
    if m.rtpSender == nil {
        return errors.New("rtp sender not initialized")
    }
    // ... 继续处理
}
```

---

**DEF-011: Goroutine 泄漏**

| 属性 | 值 |
|------|-----|
| 文件 | `services/screen-svc/internal/handler/manager.go` |
| 优先级 | P1-Important |

修复方案：
```go
type Session struct {
    // ... existing fields
    ctx    context.Context
    cancel context.CancelFunc
}

func (m *ScreenManager) StartSession(deviceID string) (*Session, error) {
    ctx, cancel := context.WithCancel(context.Background())
    session := &Session{
        ctx:    ctx,
        cancel: cancel,
        // ...
    }
    
    go m.streamVideo(ctx, deviceID, session)
    return session, nil
}

func (m *ScreenManager) streamVideo(ctx context.Context, deviceID string, session *Session) {
    for {
        select {
        case <-ctx.Done():
            return
        default:
            // 处理视频帧
        }
    }
}

func (m *ScreenManager) StopSession(deviceID string) error {
    session := m.sessions[deviceID]
    if session != nil {
        session.cancel() // 取消 goroutine
    }
    // ...
}
```

---

**DEF-012: WebRTC 播放器内存泄漏**

| 属性 | 值 |
|------|-----|
| 文件 | `frontend/src/components/WebrtcPlayer/index.tsx` |
| 优先级 | P1-Important |

修复方案：
```typescript
// 1. 修复 useEffect 依赖
useEffect(() => {
  startConnection()
  return () => {
    stopConnection()
  }
}, [deviceId, wsUrl]) // 添加正确的依赖

// 2. 清理定时器和事件监听
useEffect(() => {
  return () => {
    if (statsInterval.current) {
      clearInterval(statsInterval.current)
    }
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
    }
  }
}, [])
```

---

### Step 1: iOS 设备接入 (Week 2-3)

#### 1.1 usbmuxd 服务集成

**新建文件:** `services/device-svc/app/services/ios_service.py`

实现内容：
- `IOSDeviceService` 类
- `discover_devices()` - 通过 usbmuxd 发现 iOS 设备
- `get_device_info(udid)` - 获取设备信息
- `pair_device(udid)` - 设备配对
- `mount_developer_image(udid)` - 挂载开发者镜像

依赖安装：
```bash
pip install pymobiledevice3
```

#### 1.2 WebDriverAgent 集成

**新建文件:** `services/device-svc/app/drivers/wda_driver.py`

实现内容：
- `WDADriver` 类
- `start_wda(udid)` - 启动 WebDriverAgent
- `get_session(udid)` - 获取 WDA session
- `tap(x, y)` - 点击操作
- `swipe(x1, y1, x2, y2)` - 滑动操作
- `screenshot()` - 截图
- `find_element(by, value)` - 元素查找

#### 1.3 iOS 投屏适配

**修改文件:** `services/screen-svc/internal/handler/manager.go`

实现内容：
- 添加 iOS 投屏方法 `startIOSStream(deviceID string)`
- 集成 `ios-deploy` 或 `libimobiledevice` 进行屏幕镜像
- 支持 MJPEG 和 WebRTC 输出

**新建文件:** `services/screen-svc/internal/ios/mirror.go`

```go
package ios

type IOSMirror struct {
    deviceID string
    output   chan []byte
}

func (m *IOSMirror) Start() error {
    // 使用 ios-deploy 或 libimobiledevice 实现屏幕镜像
}

func (m *IOSMirror) Stop() error {
    // 停止镜像
}
```

#### 1.4 iOS 输入注入

**修改文件:** `services/screen-svc/internal/handler/manager.go`

实现内容：
- 添加 iOS 触摸事件处理 `handleIOSTouch(session, msg)`
- 集成 WebDriverAgent 进行输入注入

---

### Step 2: 鸿蒙设备接入 (Week 3-4)

#### 2.1 HDC 服务集成

**新建文件:** `services/device-svc/app/services/harmony_service.py`

实现内容：
- `HarmonyDeviceService` 类
- `discover_devices()` - 通过 HDC 发现鸿蒙设备
- `get_device_info(serial)` - 获取设备信息
- `install_app(serial, hap_path)` - 安装 HAP
- `uninstall_app(serial, bundle_id)` - 卸载应用

依赖安装：
```bash
pip install hdc-python  # 如果有第三方库
# 或者直接调用 hdc 命令行工具
```

#### 2.2 HOScrcpy 集成

**新建文件:** `services/screen-svc/internal/harmony/mirror.go`

实现内容：
- `HarmonyMirror` 结构体
- `Start(deviceID string)` - 启动 HOScrcpy
- `Stop()` - 停止镜像
- 视频帧输出到 WebRTC 管道

```go
package harmony

type HarmonyMirror struct {
    deviceID string
    output   chan []byte
    cmd      *exec.Cmd
}

func (m *HarmonyMirror) Start() error {
    // 调用 HOScrcpy 进行屏幕镜像
    m.cmd = exec.Command("hmoscrpy", "-s", m.deviceID)
    // 处理视频流输出
}
```

#### 2.3 鸿蒙输入注入

**新建文件:** `services/screen-svc/internal/harmony/input.go`

实现内容：
- `InputInjector` 结构体
- `Tap(x, y int)` - 点击
- `Swipe(x1, y1, x2, y2 int)` - 滑动
- `Key(keycode string)` - 按键

---

### Step 3: Appium 真实连接 (Week 4)

#### 3.1 Appium 服务部署

**新建文件:** `infra/docker/appium-docker.yml`

```yaml
version: '3.8'
services:
  appium-android:
    image: appium/appium:latest
    ports:
      - "4723:4723"
    environment:
      - PLATFORM_NAME=Android
    volumes:
      - /dev/bus/usb:/dev/bus/usb
    privileged: true

  appium-ios:
    image: appium/appium:latest
    ports:
      - "4724:4724"
    environment:
      - PLATFORM_NAME=iOS
```

#### 3.2 驱动初始化重构

**修改文件:** `services/test-svc/app/drivers/appium.py`

```python
class AppiumDriver:
    def __init__(self, platform: str, device_id: str, capabilities: dict):
        self.platform = platform
        self.device_id = device_id
        self.capabilities = capabilities
        self.driver = None

    async def initialize(self) -> bool:
        """初始化真实 Appium 连接"""
        from appium import webdriver
        
        server_url = f"http://{settings.APPIUM_HOST}:{settings.APPIUM_PORT}"
        
        caps = {
            "platformName": self.platform,
            "deviceName": self.device_id,
            "automationName": "UiAutomator2" if self.platform == "android" else "XCUITest",
            **self.capabilities
        }
        
        try:
            self.driver = webdriver.Remote(server_url, caps)
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Appium driver: {e}")
            return False

    def quit(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
```

#### 3.3 连接池管理

**新建文件:** `services/test-svc/app/services/driver_pool.py`

```python
class DriverPool:
    """Appium 驱动连接池"""
    
    def __init__(self, max_size: int = 10):
        self.pool: Dict[str, AppiumDriver] = {}
        self.max_size = max_size
        self.lock = asyncio.Lock()
    
    async def acquire(self, device_id: str, platform: str) -> AppiumDriver:
        async with self.lock:
            if device_id in self.pool:
                return self.pool[device_id]
            
            if len(self.pool) >= self.max_size:
                raise RuntimeError("Driver pool exhausted")
            
            driver = AppiumDriver(platform, device_id, {})
            await driver.initialize()
            self.pool[device_id] = driver
            return driver
    
    async def release(self, device_id: str):
        async with self.lock:
            if device_id in self.pool:
                self.pool[device_id].quit()
                del self.pool[device_id]
```

---

### Step 4: 功能完善 (Week 5)

#### 4.1 WebRTC 重连机制

**修改文件:** `frontend/src/components/WebrtcPlayer/index.tsx`

```typescript
const reconnect = useCallback(() => {
  if (reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
    onConnectionStateChange?.('failed')
    return
  }
  
  reconnectAttempts.current++
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000)
  
  reconnectTimer.current = setTimeout(() => {
    startConnection()
  }, delay)
}, [startConnection])
```

#### 4.2 FPS 正确计算

**修改文件:** `frontend/src/components/WebrtcPlayer/index.tsx`

```typescript
const updateStats = useCallback(async () => {
  if (!pc.current) return
  
  const stats = await pc.current.getStats()
  stats.forEach(report => {
    if (report.type === 'inbound-rtp' && report.kind === 'video') {
      setFps(report.framesPerSecond || 0)
    }
  })
}, [])
```

#### 4.3 触摸坐标修复

**修改文件:** `frontend/src/components/TouchOverlay/index.tsx`

```typescript
const containerRef = useRef<HTMLDivElement>(null)

const handlePointerDown = (e: React.PointerEvent) => {
  if (!containerRef.current) return
  
  const rect = containerRef.current.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  
  // 计算设备坐标
  const deviceX = Math.round((x / rect.width) * screenWidth)
  const deviceY = Math.round((y / rect.height) * screenHeight)
  
  onInput('tap', deviceX, deviceY)
}

return (
  <div ref={containerRef} {...props}>
    {children}
  </div>
)
```

#### 4.4 环境变量配置

**新建文件:** `frontend/.env.example`

```env
VITE_DEVICE_SVC_URL=http://localhost:8081
VITE_SCREEN_WS_URL=ws://localhost:8082
VITE_SCREEN_HTTP_URL=http://localhost:8082
VITE_TEST_SVC_URL=http://localhost:8083
```

**修改文件:** `frontend/src/pages/screen/index.tsx`

```typescript
const SCREEN_WS_URL = import.meta.env.VITE_SCREEN_WS_URL || 'ws://localhost:8082'
const SCREEN_HTTP_URL = import.meta.env.VITE_SCREEN_HTTP_URL || 'http://localhost:8082'
```

---

## 关键文件清单

### 安全修复

| 文件路径 | 操作 | 说明 |
|----------|------|------|
| `services/test-svc/app/tasks/executor.py` | 修改 | 沙箱执行 |
| `services/test-svc/app/executors/javascript.py` | 修改 | isolated-vm |
| `services/test-svc/app/services/auth.py` | 新建 | 认证服务 |
| `services/test-svc/app/middleware/auth.py` | 新建 | 认证中间件 |
| `services/screen-svc/internal/handler/manager.go` | 修改 | 输入验证 |

### iOS 接入

| 文件路径 | 操作 | 说明 |
|----------|------|------|
| `services/device-svc/app/services/ios_service.py` | 新建 | iOS 设备服务 |
| `services/device-svc/app/drivers/wda_driver.py` | 新建 | WDA 驱动 |
| `services/screen-svc/internal/ios/mirror.go` | 新建 | iOS 镜像 |
| `services/screen-svc/internal/handler/manager.go` | 修改 | iOS 支持 |

### 鸿蒙接入

| 文件路径 | 操作 | 说明 |
|----------|------|------|
| `services/device-svc/app/services/harmony_service.py` | 新建 | 鸿蒙设备服务 |
| `services/screen-svc/internal/harmony/mirror.go` | 新建 | 鸿蒙镜像 |
| `services/screen-svc/internal/harmony/input.go` | 新建 | 鸿蒙输入 |

### Appium 连接

| 文件路径 | 操作 | 说明 |
|----------|------|------|
| `services/test-svc/app/drivers/appium.py` | 重构 | 真实连接 |
| `services/test-svc/app/services/driver_pool.py` | 新建 | 连接池 |
| `infra/docker/appium-docker.yml` | 新建 | Appium 部署 |

---

## 验证方法

### Step 0 验证：安全修复

```bash
# 1. 测试 Python 沙箱
curl -X POST http://localhost:8083/api/v1/tasks \
  -d '{"script_id": "malicious", "content": "import os; os.system(\"rm -rf /\")"}'
# 应返回错误，不允许执行

# 2. 测试 JavaScript 沙箱
curl -X POST http://localhost:8083/api/v1/tasks \
  -d '{"script_id": "malicious", "content": "require(\"child_process\").exec(\"rm -rf /\")"}'
# 应返回错误

# 3. 测试 API 认证
curl http://localhost:8083/api/v1/tasks
# 应返回 401 Unauthorized
```

### Step 1 验证：iOS 接入

```bash
# 1. 连接 iOS 设备
idevice_id -l

# 2. 启动服务
docker-compose up -d

# 3. 测试 iOS 设备发现
curl http://localhost:8081/api/v1/devices?platform=ios

# 4. 测试 iOS 投屏
# 访问 http://localhost:5173/screen?deviceId=<ios_udid>&platform=ios
```

### Step 2 验证：鸿蒙接入

```bash
# 1. 连接鸿蒙设备
hdc list targets

# 2. 测试鸿蒙设备发现
curl http://localhost:8081/api/v1/devices?platform=harmony

# 3. 测试鸿蒙投屏
# 访问 http://localhost:5173/screen?deviceId=<harmony_id>&platform=harmony
```

### Step 3 验证：Appium 连接

```bash
# 1. 启动 Appium 服务
docker-compose -f infra/docker/appium-docker.yml up -d

# 2. 创建真实测试任务
curl -X POST http://localhost:8083/api/v1/tasks \
  -d '{"script_id": "login_test", "device_id": "real_device_001"}'

# 3. 检查任务执行日志
curl http://localhost:8083/api/v1/tasks/<task_id>/logs
```

---

## 性能目标

| 指标 | Phase 1 | Phase 2 目标 |
|------|---------|--------------|
| Android 投屏延迟 | < 50ms ✅ | < 50ms |
| iOS 投屏延迟 | - | < 150ms |
| 鸿蒙投屏延迟 | - | < 100ms |
| 触控响应 | < 50ms ✅ | < 50ms |
| 并发设备 | 50+ | 100+ |
| 任务执行安全性 | ❌ 无沙箱 | ✅ 沙箱隔离 |

---

## 依赖关系

```
Step 0 (缺陷修复) ─────────────────────────────────────────┐
    │                                                      │
    v                                                      │
Step 1 (iOS 接入) ──┐                                      │
    │               │                                      │
    v               │                                      │
Step 2 (鸿蒙接入) ──┼──> Step 4 (功能完善)                 │
    │               │           │                          │
    v               │           v                          │
Step 3 (Appium) ───┘    集成测试                           │
    │                                                     │
    v                                                     │
Phase 2 完成 <─────────────────────────────────────────────┘
```

---

## 风险与应对

| 风险 | 等级 | 应对措施 |
|------|------|----------|
| iOS 投屏稳定性 | 高 | 多方案备选 (WDA/QuickTime/libimobiledevice) |
| WebDriverAgent 签名问题 | 中 | 自动化签名脚本 |
| 鸿蒙 HDC 兼容性 | 中 | 多版本测试 |
| 沙箱性能影响 | 低 | 资源隔离优化 |
| Appium 版本兼容 | 低 | 固定版本 + 版本矩阵测试 |

---

## 里程碑

| 里程碑 | 目标日期 | 验收标准 | 依赖 |
|--------|----------|----------|------|
| M2.0 缺陷修复完成 | Week 1 | 所有 Critical 缺陷修复 | - |
| M2.1 iOS 基础可用 | Week 2 | iOS 设备发现 + 投屏 | M2.0 |
| M2.2 iOS 完整可用 | Week 3 | iOS 投屏 + 触控 + 自动化 | M2.1 |
| M2.3 鸿蒙基础可用 | Week 3 | 鸿蒙设备发现 + 投屏 | M2.0 |
| M2.4 鸿蒙完整可用 | Week 4 | 鸿蒙投屏 + 触控 + 自动化 | M2.3 |
| M2.5 Appium 可用 | Week 4 | 真实驱动执行成功 | M2.0 |
| M2.6 Phase 2 完成 | Week 5 | 三端全流程可用 | M2.2, M2.4, M2.5 |
