#!/bin/bash

# 设备农场开发环境启动脚本
# 用于一键启动所有服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

echo "=========================================="
echo "   Device Farm Development Environment"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed${NC}"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        echo -e "${RED}Error: Docker is not running${NC}"
        exit 1
    fi
}

# 检查 Docker Compose
check_docker_compose() {
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo -e "${RED}Error: Docker Compose is not installed${NC}"
        exit 1
    fi
}

# 创建环境变量文件
setup_env() {
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        echo -e "${YELLOW}Creating .env file from template...${NC}"
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    fi

    local livekit_host
    livekit_host="${LIVEKIT_PUBLIC_HOST:-$(detect_lan_ip)}"
    if [ -z "$livekit_host" ]; then
        echo -e "${RED}Error: unable to detect LAN IP for LiveKit${NC}"
        echo "Set LIVEKIT_PUBLIC_HOST in $PROJECT_ROOT/infra/docker/.env and run again."
        exit 1
    fi

    upsert_env "$PROJECT_ROOT/.env" "LIVEKIT_PUBLIC_HOST" "$livekit_host"
    upsert_env "$PROJECT_ROOT/infra/docker/.env" "LIVEKIT_PUBLIC_HOST" "$livekit_host"
    echo -e "${GREEN}LiveKit public host: ${livekit_host}${NC}"
}

detect_lan_ip() {
    local iface ip

    iface="$(route get default 2>/dev/null | awk '/interface:/{print $2; exit}')"
    if [ -n "$iface" ]; then
        ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
        if [ -n "$ip" ]; then
            echo "$ip"
            return 0
        fi
    fi

    for iface in en0 en1 bridge100; do
        ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
        if [ -n "$ip" ]; then
            echo "$ip"
            return 0
        fi
    done

    hostname -I 2>/dev/null | awk '{print $1}'
}

upsert_env() {
    local file="$1"
    local key="$2"
    local value="$3"

    touch "$file"
    if grep -q "^${key}=" "$file"; then
        sed -i.bak "s|^${key}=.*|${key}=${value}|" "$file"
        rm -f "${file}.bak"
    else
        {
            if [ -s "$file" ]; then
                echo ""
            fi
            echo "# Auto-detected by dev.sh. Override when testing from another network."
            echo "${key}=${value}"
        } >> "$file"
    fi
}

# 启动基础设施服务
start_infra() {
    echo -e "${GREEN}Starting infrastructure services...${NC}"
    cd "$PROJECT_ROOT/infra/docker"

    # 使用 docker compose 或 docker-compose
    if docker compose version &> /dev/null; then
        docker compose --env-file "$PROJECT_ROOT/infra/docker/.env" up -d
    else
        docker-compose --env-file "$PROJECT_ROOT/infra/docker/.env" up -d
    fi

    echo -e "${GREEN}Waiting for services to be ready...${NC}"
    sleep 5

    # 检查 PostgreSQL
    echo -e "${YELLOW}Checking PostgreSQL...${NC}"
    until docker exec device-farm-postgres pg_isready -U devicefarm -d device_farm &> /dev/null; do
        echo "  Waiting for PostgreSQL..."
        sleep 2
    done
    echo -e "${GREEN}  PostgreSQL is ready${NC}"

    # 检查 Redis
    echo -e "${YELLOW}Checking Redis...${NC}"
    until docker exec device-farm-redis redis-cli -a redis123 ping &> /dev/null; do
        echo "  Waiting for Redis..."
        sleep 2
    done
    echo -e "${GREEN}  Redis is ready${NC}"

    # 检查 MinIO
    echo -e "${YELLOW}Checking MinIO...${NC}"
    until curl -s http://localhost:9000/minio/health/live &> /dev/null; do
        echo "  Waiting for MinIO..."
        sleep 2
    done
    echo -e "${GREEN}  MinIO is ready${NC}"
}

# 启动 Mock 服务
start_mock() {
    echo -e "${GREEN}Checking Mock server...${NC}"
    if docker ps --format '{{.Names}}' | grep -q '^device-farm-mock$'; then
        echo -e "${GREEN}  Mock server is running on port 3001${NC}"
    else
        echo -e "${YELLOW}  Mock server container is not running${NC}"
    fi
}

# 显示服务状态
show_status() {
    echo ""
    echo -e "${GREEN}=========================================="
    echo "   Services Status"
    echo -e "==========================================${NC}"
    echo ""
    echo "  PostgreSQL:  localhost:5432"
    echo "  Redis:       localhost:6379"
    echo "  MinIO:       localhost:9000 (API)"
    echo "               localhost:9001 (Console)"
    echo "  Frontend:    http://localhost:3000"
    echo "  Mock API:    http://localhost:3001"
    echo ""
    echo -e "${GREEN}=========================================="
    echo "   Quick Links"
    echo -e "==========================================${NC}"
    echo ""
    echo "  MinIO Console:    http://localhost:9001"
    echo "                    User: minioadmin"
    echo "                    Pass: minioadmin123"
    echo ""
    echo "  API Documentation: $PROJECT_ROOT/docs/api.md"
    echo "  OpenAPI Spec:      $PROJECT_ROOT/infra/api/api-spec.yaml"
    echo ""
}

# 主函数
main() {
    echo "Checking prerequisites..."
    check_docker
    check_docker_compose

    echo ""
    setup_env
    start_infra
    start_mock
    show_status

    echo -e "${GREEN}All services are up and running!${NC}"
    echo ""
}

# 帮助信息
show_help() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start     Start all services (default)"
    echo "  stop      Stop all services"
    echo "  status    Show service status"
    echo "  logs      Show logs"
    echo "  help      Show this help message"
    echo ""
}

# 停止服务
stop_services() {
    echo -e "${YELLOW}Stopping all services...${NC}"
    cd "$PROJECT_ROOT/infra/docker"

    if docker compose version &> /dev/null; then
        docker compose --env-file "$PROJECT_ROOT/infra/docker/.env" down
    else
        docker-compose --env-file "$PROJECT_ROOT/infra/docker/.env" down
    fi

    echo -e "${GREEN}All services stopped${NC}"
}

# 查看日志
show_logs() {
    cd "$PROJECT_ROOT/infra/docker"

    if docker compose version &> /dev/null; then
        docker compose --env-file "$PROJECT_ROOT/infra/docker/.env" logs -f
    else
        docker-compose --env-file "$PROJECT_ROOT/infra/docker/.env" logs -f
    fi
}

# 解析命令
case "${1:-start}" in
    start)
        main
        ;;
    stop)
        stop_services
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
