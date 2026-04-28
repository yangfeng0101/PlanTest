# 服务启动常见问题排查指南

## 1. 服务启动前检查清单

### 必须先启动的服务
```bash
# 1. PostgreSQL
brew services start postgresql@15

# 2. Redis (如果使用)
brew services start redis
```

### 环境变量配置
```bash
# 所有服务启动时需要设置 PYTHONPATH
export PYTHONPATH=/Users/admin/Desktop/PlanTest/device-farm/services
```

## 2. 数据库问题

### 问题: password authentication failed for user "admin"
**原因**: PostgreSQL 未启动或密码错误

**解决方案**:
```bash
# 启动 PostgreSQL
brew services start postgresql@15

# 如果密码错误，重置密码
psql -U admin -d device_farm -c "ALTER USER admin WITH PASSWORD '新密码';"
```

### 问题: relation "xxx" does not exist
**原因**: 数据库表不存在

**解决方案**:
```bash
# 检查现有表
psql -U admin -d device_farm -c "\dt"

# 根据需要创建缺失的表（参考各服务的 models）
```

### 问题: column "xxx" does not exist
**原因**: 数据库表结构与模型定义不匹配

**解决方案**:
```bash
# 检查表结构
psql -U admin -d device_farm -c "\d users"

# 添加缺失的列
psql -U admin -d device_farm -c "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(256);"
```

### 问题: permission denied for table "xxx"
**原因**: 数据库用户权限不足

**关键**: 检查 .env 文件中配置的数据库用户！

**解决方案**:
```bash
# 查看实际使用的数据库用户
cat services/test-svc/.env | grep DATABASE_URL

# 给正确的用户授权 (注意是 devicefarm，不是 admin)
psql -U admin -d device_farm -c "
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO devicefarm;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO devicefarm;
GRANT USAGE ON SCHEMA public TO devicefarm;
"
```

## 3. 服务配置

### 各服务数据库配置文件位置
| 服务 | 配置文件 | 数据库用户 |
|------|----------|------------|
| device-svc | `services/device-svc/app/config.py` | admin (默认) |
| test-svc | `services/test-svc/.env` | devicefarm |
| report-svc | `services/report-svc/app/config.py` | admin (默认) |

### test-svc 数据库连接字符串
文件: `services/test-svc/.env`
```
DATABASE_URL=postgresql+asyncpg://devicefarm:devicefarm123@localhost:5432/device_farm
```

## 4. 端口配置

### 服务端口分配
| 服务 | 端口 | 启动命令 |
|------|------|----------|
| device-svc | 8001 | `uvicorn app.main:app --host 0.0.0.0 --port 8001` |
| test-svc | 8083 | `uvicorn app.main:app --host 0.0.0.0 --port 8083` |
| report-svc | 8085 | `uvicorn app.main:app --host 0.0.0.0 --port 8085` |
| frontend | 3000 | `npm run dev -- --port 3000 --host` |

### 前端代理配置
文件: `frontend/vite.config.ts`
```typescript
server: {
  port: 3000,
  proxy: {
    '/api/v1/auth': { target: 'http://localhost:8083' },
    '/api/v1/scripts': { target: 'http://localhost:8083' },
    '/api/v1/tasks': { target: 'http://localhost:8083' },
    '/api/v1/reports': { target: 'http://localhost:8085' },
    '/api/v1/statistics': { target: 'http://localhost:8085' },
    '/api': { target: 'http://localhost:8001' },
  },
}
```

### 清理被占用的端口
```bash
# 清理单个端口
lsof -ti :3000 | xargs kill -9

# 清理所有服务端口
lsof -ti :3000,:8001,:8083,:8085 | xargs kill -9
```

## 5. Python 依赖问题

### 问题: No module named 'psycopg2'
```bash
pip3 install psycopg2-binary
```

### 问题: No module named 'asyncpg'
```bash
pip3 install asyncpg
```

### 问题: No module named 'shared'
```bash
# 启动服务时设置 PYTHONPATH
PYTHONPATH=/Users/admin/Desktop/PlanTest/device-farm/services uvicorn app.main:app --port 8083
```

## 6. 用户认证问题

### 问题: 登录失败 / Internal Server Error
**排查步骤**:

1. 检查 test-svc 是否运行
```bash
curl http://localhost:8083/health
```

2. 检查数据库连接
```bash
psql -U devicefarm -d device_farm -c "SELECT 1"
```

3. 检查用户表结构
```bash
psql -U admin -d device_farm -c "\d users"
```

4. 检查 admin 用户密码是否设置
```bash
psql -U admin -d device_farm -c "SELECT username, password_hash FROM users WHERE username='admin';"
```

### 重置 admin 密码
```bash
# 生成密码哈希
python3 -c "
import bcrypt
print(bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode())
"

# 更新数据库
psql -U admin -d device_farm -c "UPDATE users SET password_hash = '生成的哈希值' WHERE username='admin';"
```

## 7. 完整启动流程

### 一键启动脚本
```bash
#!/bin/bash
set -e

# 设置环境变量
export PYTHONPATH=/Users/admin/Desktop/PlanTest/device-farm/services

# 启动数据库
brew services start postgresql@15

# 清理旧进程
lsof -ti :3000,:8001,:8083,:8085 | xargs kill -9 2>/dev/null || true

# 启动后端服务
cd /Users/admin/Desktop/PlanTest/device-farm/services/device-svc
nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/device-svc.log 2>&1 &

cd /Users/admin/Desktop/PlanTest/device-farm/services/test-svc
nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8083 > /tmp/test-svc.log 2>&1 &

cd /Users/admin/Desktop/PlanTest/device-farm/services/report-svc
nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8085 > /tmp/report-svc.log 2>&1 &

# 等待后端启动
sleep 3

# 启动前端
cd /Users/admin/Desktop/PlanTest/device-farm/frontend
npm run dev -- --port 3000 --host > /tmp/frontend.log 2>&1 &

echo "所有服务已启动"
echo "前端: http://localhost:3000"
echo "登录: admin / admin123"
```

### 验证服务状态
```bash
# 检查所有服务
curl http://localhost:8001/health  # device-svc
curl http://localhost:8083/health  # test-svc
curl http://localhost:8085/health  # report-svc
curl http://localhost:3000/        # frontend

# 测试登录
curl -X POST http://localhost:8083/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

## 8. 前端设备列表问题

### 问题: 设备列表为空，但后端 API 有数据
**原因**: `deviceStore.ts` 字段解析错误

**解决方案**:
检查 `frontend/src/stores/deviceStore.ts`，API 返回 `{ devices: [...], total: N }`，不是 `{ data: [...] }`

```typescript
// 错误写法
const { data } = await fetch('/api/v1/devices').then((res) => res.json())

// 正确写法
const response = await fetch('/api/v1/devices').then((res) => res.json())
const devices = response.devices || []
```

### 问题: 系统版本、屏幕分辨率等字段显示为空
**原因**: 后端返回 snake_case（如 `os_version`），前端期望 camelCase（如 `osVersion`）

**解决方案**:
在 `deviceStore.ts` 中做字段名转换：
```typescript
const devices = (response.devices || []).map((d) => ({
  osVersion: d.os_version,
  screenResolution: d.screen_resolution,
  screenSize: d.screen_size,
  batteryLevel: d.battery_level,
  // ...
}))
```

### 问题: 设备名称显示为型号代码（如 V2254A）
**原因**: ADB 无法获取市场名称，只能获取型号代码

**解决方案**:
使用型号映射表 `services/device-svc/app/models/device_model_map.py`，添加新机型映射：
```python
DEVICE_MODEL_MAP = {
    "V2254A": "iQOO 11 Pro",
    # 添加更多机型...
}
```

### 问题: HarmonyOS 显示后监控或控件获取不可用
**原因**: HarmonyOS 手机通过 ADB 接入时仍然是 Android-compatible 能力链路。如果业务逻辑直接用 `os === "android"` 判断能力，显示为 `harmony` 后会误判为不支持。

**解决方案**:
使用设备响应中的运行时能力字段，而不是直接判断 `os`：
```typescript
device.displayOs           // 展示名称，如 HarmonyOS
device.connectionType      // 接入方式，如 adb
device.drivers.metrics     // 采集驱动，如 adb
device.capabilities.uiHierarchy
device.capabilities.screenMirror
```

后端能力判断也应基于 `drivers/capabilities`。当前通过 ADB 接入的 HarmonyOS 手机应显示为 `HarmonyOS`，但监控、投屏、触控和 UIAutomator 控件树仍走 ADB/scrcpy/uiautomator。

### 问题: 监控页面显示 "WebSocket 断开"
**原因**: Vite 代理未启用 WebSocket 支持

**解决方案**:
在 `frontend/vite.config.ts` 的代理配置中添加 `ws: true`：
```typescript
'/api': {
  target: 'http://localhost:8001',
  changeOrigin: true,
  ws: true,  // 启用 WebSocket 代理
},
```

重启前端服务生效。

### 问题: 监控图表时间显示不正确（显示 UTC 时间）
**原因**: 后端返回的时间戳无 `Z` 后缀，JavaScript 将其解析为本地时间而非 UTC

**解决方案**:
在解析时间戳时添加 `Z` 后缀强制作为 UTC 处理：
```typescript
const date = new Date(m.timestamp + 'Z')  // 添加 Z 表示 UTC
return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
```

### 问题: 内存使用率始终显示 0%
**原因**: `dumpsys meminfo` 输出格式变化，旧代码匹配 `RAM: xxxK total`，实际输出为 `Total RAM: xxxK`

**解决方案**:
修改 `services/device-svc/app/services/metrics_service.py` 中的 `_parse_android_memory` 方法：
```python
# 匹配新格式
if 'Total RAM:' in line:
    match = re.search(r'(\d+(?:,\d+)*)K', line)
if 'Free RAM:' in line:
    match = re.search(r'(\d+(?:,\d+)*)K', line)
if 'Used RAM:' in line:
    match = re.search(r'(\d+(?:,\d+)*)K', line)
```

## 9. 认证相关问题

### 问题: AUTH-002 - 登录成功但页面未跳转，显示"未授权"
**原因**: `AuthMiddleware` 只检查 `Authorization` header，不支持 Cookie 方式携带 token

**解决方案**:
修改 `services/test-svc/app/middleware/auth.py`，在获取 token 时优先检查 Authorization header，其次检查 Cookie：

```python
# 从 Authorization header 或 Cookie 获取 token
auth_header = request.headers.get("Authorization", "")
if auth_header.startswith("Bearer "):
    token = auth_header[7:]
else:
    token = request.cookies.get("token", "")
```

### 问题: AUTH-001 - 登录时报错 "column 'password_hash' does not exist"
**原因**: `User` 模型使用 `password_hash` 字段，但数据库表中实际字段名为 `hashed_password`

**解决方案**:
有两种方式：
1. 修改数据库表结构（推荐，因为代码已广泛使用 `password_hash`）：
```sql
ALTER TABLE users RENAME COLUMN hashed_password TO password_hash;
```

2. 或修改模型字段名以匹配数据库：
```python
# 在 User 模型中使用别名
password_hash: str = Field(alias="hashed_password")
```

**预防措施**: 模型定义与数据库表结构应保持一致，迁移时需同步更新。

## 10. 日志位置

| 服务 | 日志文件 |
|------|----------|
| device-svc | /tmp/device-svc.log |
| test-svc | /tmp/test-svc.log |
| report-svc | /tmp/report-svc.log |
| frontend | /tmp/frontend.log |

查看日志:
```bash
tail -50 /tmp/test-svc.log
```
