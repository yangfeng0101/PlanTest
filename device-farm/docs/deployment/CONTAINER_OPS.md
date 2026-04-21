# 容器化环境运维指南 (Containerized Environment Ops Guide)

本指南总结了 Device Farm 平台在 Docker 容器化环境下的启动、部署及常见问题排查流程。

## 1. 快速启动 (Quick Start)

### 1.1 前置条件
*   **Docker & Docker Compose**: 已安装并启动。
*   **ADB (重要)**: 若需连接真机，宿主机必须运行全局模式的 ADB Server：
    ```bash
    adb kill-server
    adb -a nodaemon server
    ```

### 1.2 一键部署
在项目根目录下执行以下命令：
```bash
# 进入部署目录
cd device-farm/infra/docker

# 构建并启动全量服务 (Nginx, 4个微服务, 3个数据库/中间件)
docker-compose up -d --build
```

### 1.3 访问信息
*   **前端入口**: [http://localhost:3000](http://localhost:3000)
*   **默认管理员**: `admin` / `admin123`
*   **MinIO 控制台**: [http://localhost:9001](http://localhost:9001) (minioadmin / minioadmin123)

---

## 2. 服务架构 (Service Map)

| 服务名称 | 端口 (容器内) | 端口 (映射) | 核心职责 |
| :--- | :--- | :--- | :--- |
| `nginx` | 80 | 3000 | 反向代理、静态资源服务、WebSocket 转发 |
| `test-svc` | 8001 | 8003 | 身份鉴权、脚本管理、任务调度 |
| `device-svc`| 8001 | 8001 | 宿主机 ADB 桥接、真机状态监控、WebSocket 推送 |
| `report-svc`| 8002 | 8004 | 测试报告存储、数据统计、告警通知 |
| `screen-svc`| 8002 | 8002 | WebRTC/MJPEG 低延迟投屏逻辑 |
| `ai-svc`    | 8005 | 8005 | OCR 识别、UI 元素定位、测试用例生成 |

---

## 3. 常见问题排查 (Troubleshooting)

### 3.1 页面显示 "Failed to fetch" 或 502
*   **原因**: Nginx 找不到后端上游，或后端容器正在启动中。
*   **检查**: 
    ```bash
    docker-compose ps
    ```
    确保所有服务处于 `Up` 状态。
*   **解决**: Nginx 已配置动态 DNS 解析，通常等待 30 秒即可自动恢复。若长时间 502，请检查 `test-svc` 日志是否有数据库连接报错。

### 3.2 登录失败 (Invalid Password)
*   **修复**: 若 `init.sql` 未生效，可手动重置管理员密码哈希：
    ```bash
    docker exec -it device-farm-postgres psql -U devicefarm -d device_farm -c "UPDATE users SET password_hash = '\$2b$12\$JRPfP2Gn088pnmuuKnKFceuHE1tv7iqsk.OAXwt9q3H1GPcMzrNYi' WHERE username = 'admin';"
    ```

### 3.3 设备列表为空
*   **原因**: 容器无法连接宿主机 ADB。
*   **检查**: 
    1. 宿主机是否执行了 `adb -a nodaemon server`。
    2. 执行 `docker exec device-farm-device-svc adb devices` 看容器内是否有输出。
*   **解决**: 检查 `docker-compose.yml` 中的 `extra_hosts` 是否包含 `host.docker.internal:host-gateway`。

### 3.4 WebSocket 连接断开
*   **现象**: 监控曲线不跳动或投屏黑屏。
*   **解决**: 检查 Nginx 配置文件中 `Upgrade` 和 `Connection` 头的设置。系统已默认配置扁平化路由以保障长连接稳定性。

---

## 4. 进阶维护 (Maintenance)

### 4.1 清理并彻底重启
若系统出现严重的 Schema 不匹配或网络缓存问题：
```bash
cd device-farm/infra/docker
docker-compose down -v  # 删除所有容器和数据卷 (慎用: 会清空数据库)
docker-compose up -d --build
```

### 4.2 查看实时日志
```bash
# 查看所有服务
docker-compose logs -f --tail 100

# 查看指定服务 (如真机管理)
docker-compose logs -f device-svc
```

### 4.3 数据库初始化
数据库初始化脚本位于 `device-farm/infra/sql/init.sql`。每次 `docker-compose up` 时，若数据卷为空，该脚本会自动执行。

---

## 5. 开发建议 (Developer Tips)
*   **前端修改**: 必须执行 `npm run build` 后重启 Nginx 容器才能生效。
*   **后端修改**: 重启对应容器即可：`docker-compose restart <service-name>`。
*   **依赖更新**: 修改 `requirements.txt` 后必须加 `--build` 参数重新启动。
