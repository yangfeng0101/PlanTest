# 统一真机自动化测试平台 Phase 1 实施计划

## Context

用户需要开发一个稳定且高性能的真机自动化测试平台，严格按照产品文档和执行文档的技术方案实施，不允许使用简易版或降级方案。

**核心问题：**
1. screen-svc 的 WebRTC 视频发送未实现（SendVideo 方法为空）
2. 前端投屏组件缺失触摸事件处理、WebRTC 播放器
3. test-svc 数据未持久化、截图/视频未真正存储

**性能目标：**
- Android 投屏延迟 < 50ms
- 触控响应 < 50ms
- 支持 50+ 并发设备

---

## 实施步骤

### Step 1: screen-svc WebRTC 完整实现 (Week 1-2)

#### 1.1 创建 H.264 NAL 解析器

**新建文件:** `services/screen-svc/internal/video/nal_parser.go`

实现内容：
- `NALParser` 结构体，包含 SPS/PPS 缓存
- `Parse(data []byte) ([]NALUnit, error)` - 解析 Scrcpy 输出的 H.264 流
- `ExtractSPSPPS(units []NALUnit)` - 提取并缓存 SPS/PPS
- 支持 NAL 类型识别：SPS(7), PPS(8), IDR(5), Non-IDR(1)

#### 1.2 创建 RTP 打包器

**新建文件:** `services/screen-svc/internal/video/rtp_packer.go`

实现内容：
- `RTPPacker` 结构体，管理序列号、SSRC、PayloadType
- `Pack(nalUnit []byte, timestamp uint32) []*rtp.Packet`
- Single NAL Unit Packet（<= 1200 字节）
- FU-A 分片（> 1200 字节）
- 时钟率 90000 (H.264 标准)

#### 1.3 修改 WebRTC Manager

**修改文件:** `services/screen-svc/internal/webrtc/webrtc.go`

关键修改：
1. 添加字段：
```go
type Manager struct {
    // ... existing fields ...
    rtpPacker    *video.RTPPacker
    nalParser    *video.NALParser
    rtpSender    *webrtc.RTPSender
    onICECandidate func(*webrtc.ICECandidate)
}
```

2. 实现 `SendVideo` 方法（第 115-126 行）：
```go
func (m *Manager) SendVideo(data []byte) error {
    // 1. 解析 NAL 单元
    nalUnits, err := m.nalParser.Parse(data)
    // 2. 提取 SPS/PPS
    m.nalParser.ExtractSPSPPS(nalUnits)
    // 3. 打包为 RTP
    // 4. 通过 rtpSender.SendRTPPacket 发送
}
```

3. 修改 `initializePeerConnection`（第 139-212 行）：
- 初始化 rtpPacker 和 nalParser
- 添加 `pc.OnICECandidate` 回调通知客户端

#### 1.4 修改 ScreenManager

**修改文件:** `services/screen-svc/internal/handler/manager.go`

修改 `streamVideo` 方法（第 347-361 行）：
- 添加设备屏幕尺寸获取
- 添加错误处理和重连逻辑
- 添加帧率统计

---

### Step 2: 前端投屏组件完善 (Week 2-3)

#### 2.1 安装依赖

```bash
cd frontend
npm install jessibuca-pro
```

#### 2.2 创建 WebRTC 播放器组件

**新建文件:** `frontend/src/components/WebrtcPlayer/index.tsx`

实现内容：
- RTCPeerConnection 管理
- WebSocket 信令通道
- offer/answer/candidate 消息交换
- 视频流绑定到 video 元素
- 连接状态监控

#### 2.3 创建 jessibuca 播放器组件（备选）

**新建文件:** `frontend/src/components/JessibucaPlayer/index.tsx`

实现内容：
- jessibuca 实例管理
- WebSocket 流地址配置
- 播放/暂停/销毁生命周期

#### 2.4 创建触摸事件处理器

**新建文件:** `frontend/src/components/TouchHandler/index.tsx`

实现内容：
- `useTouchHandler` Hook
- `mapCoordinates` - 动态坐标映射（从设备信息获取分辨率）
- `handlePointerDown/Move/Up` - 触摸事件处理
- 长按检测（800ms）
- 滑动检测（距离 > 10px）
- 手势支持（上下左右滑动）

#### 2.5 重构 ScreenPage

**修改文件:** `frontend/src/pages/screen/index.tsx`

关键修改：
1. 删除硬编码坐标映射（第 141-142 行）
2. 从设备信息动态获取屏幕分辨率
3. 集成 WebRTC 播放器
4. 应用 TouchHandler
5. 添加播放器切换（WebRTC/jessibuca）

---

### Step 3: test-svc 数据持久化 (Week 3-4)

#### 3.1 创建数据库模型

**新建文件:** `services/test-svc/app/models/database.py`

定义 SQLAlchemy 模型：
- `ScriptDB` - 脚本表
- `TaskDB` - 任务表
- `TaskLogDB` - 日志表
- `ScreenshotDB` - 截图表
- `VideoDB` - 视频表

#### 3.2 创建数据库连接管理

**新建文件:** `services/test-svc/app/database.py`

实现内容：
- `create_async_engine` 异步引擎
- `AsyncSessionLocal` 会话工厂
- `get_db` 依赖注入
- `init_db` 初始化函数

#### 3.3 创建 MinIO 存储服务

**新建文件:** `services/test-svc/app/services/storage.py`

实现内容：
- `StorageService` 类
- `upload_screenshot(task_id, data, index)` - 上传截图
- `upload_video(task_id, data)` - 上传视频
- `get_presigned_url(object_name)` - 获取签名 URL

#### 3.4 重构 Tasks API

**修改文件:** `services/test-svc/app/api/tasks.py`

关键修改：
1. 删除内存存储 `_tasks_db: dict = {}`
2. 使用 `Depends(get_db)` 注入数据库会话
3. 所有 CRUD 操作改为数据库操作
4. 添加分页查询

#### 3.5 修改任务执行器

**修改文件:** `services/test-svc/app/tasks/executor.py`

关键修改：
1. `take_screenshot` - 调用 storage_service 上传到 MinIO
2. 添加 `start_recording` / `stop_recording` 函数
3. 在 `execute_test_task` 开始时启动录制，结束时停止

#### 3.6 实现 JavaScript 执行器

**新建文件:** `services/test-svc/app/executors/javascript.py`

实现内容：
- 创建临时 JS 文件
- 使用 Node.js 子进程执行
- 解析执行结果

#### 3.7 配置 Celery Worker

**新建文件:** `services/test-svc/worker.py`

```python
celery_app.worker_main(['worker', '--loglevel=info', '--concurrency=4'])
```

**新建文件:** `services/test-svc/beat.py`

```python
celery_app.beat_main(['beat', '--loglevel=info'])
```

#### 3.8 更新 Docker Compose

**修改文件:** `infra/docker/docker-compose.yml`

添加服务：
- `test-svc-worker` - Celery Worker
- `test-svc-beat` - Celery Beat 调度器

---

## 关键文件清单

| 文件路径 | 操作 | 说明 |
|----------|------|------|
| `services/screen-svc/internal/video/nal_parser.go` | 新建 | H.264 NAL 解析 |
| `services/screen-svc/internal/video/rtp_packer.go` | 新建 | RTP 打包 |
| `services/screen-svc/internal/webrtc/webrtc.go` | 修改 | 实现 SendVideo |
| `services/screen-svc/internal/handler/manager.go` | 修改 | 视频流管道 |
| `frontend/src/components/WebrtcPlayer/index.tsx` | 新建 | WebRTC 播放器 |
| `frontend/src/components/JessibucaPlayer/index.tsx` | 新建 | jessibuca 播放器 |
| `frontend/src/components/TouchHandler/index.tsx` | 新建 | 触摸事件处理 |
| `frontend/src/pages/screen/index.tsx` | 重构 | 集成新组件 |
| `services/test-svc/app/models/database.py` | 新建 | 数据库模型 |
| `services/test-svc/app/database.py` | 新建 | 数据库连接 |
| `services/test-svc/app/services/storage.py` | 新建 | MinIO 存储 |
| `services/test-svc/app/api/tasks.py` | 重构 | 数据库持久化 |
| `services/test-svc/app/tasks/executor.py` | 修改 | 集成存储服务 |
| `services/test-svc/app/executors/javascript.py` | 新建 | JS 执行器 |
| `services/test-svc/worker.py` | 新建 | Worker 启动 |
| `services/test-svc/beat.py` | 新建 | Beat 启动 |

---

## 验证方法

### Step 1 验证：WebRTC 视频流

```bash
# 1. 启动 screen-svc
cd services/screen-svc && go run cmd/main.go

# 2. 连接 Android 设备
adb devices

# 3. 使用 Chrome 访问 chrome://webrtc-internals
# 4. 验证视频流传输、延迟测量
# 目标: Android < 50ms
```

### Step 2 验证：前端投屏

```bash
# 1. 启动前端
cd frontend && npm run dev

# 2. 访问 http://localhost:5173/screen?deviceId=<device_id>

# 3. 测试项：
# - 点击四角验证坐标映射准确
# - 滑动手势响应
# - 长按识别
# 目标: 触控响应 < 50ms
```

### Step 3 验证：数据持久化

```bash
# 1. 启动所有服务
docker-compose up -d

# 2. 创建测试任务
curl -X POST http://localhost:8083/api/v1/tasks -d '{"script_id":"test"}'

# 3. 重启服务后检查数据
docker-compose restart test-svc
curl http://localhost:8083/api/v1/tasks

# 4. 检查 MinIO
# 访问 http://localhost:9001 验证截图/视频上传
```

---

## 依赖关系

```
Step 1 (screen-svc WebRTC)
    |
    v
Step 2 (前端投屏) ──依赖── Step 1 WebRTC 接口
    |
    v
Step 3 (test-svc 持久化) ──独立── 可并行开发
```

---

## 不允许的降级方案

1. **禁止使用 screencap + MJPEG** - 必须使用 Scrcpy + WebRTC
2. **禁止使用内存存储** - 必须使用 PostgreSQL 持久化
3. **禁止使用占位符存储** - 截图/视频必须真正上传到 MinIO
4. **禁止硬编码坐标** - 必须动态获取设备分辨率

---

## 风险与应对

| 风险 | 应对措施 |
|------|----------|
| WebRTC ICE 穿透问题 | 配置 TURN 服务器 |
| H.264 编码兼容性 | 支持多种 profile-level-id |
| 高并发性能 | 连接池 + 流复用 |
| 数据库连接泄漏 | 使用 async context manager |
