#!/bin/bash

# 设备农场开发环境启动脚本
# 用于一键启动所有服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

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
}

# 启动基础设施服务
start_infra() {
    echo -e "${GREEN}Starting infrastructure services...${NC}"
    cd "$PROJECT_ROOT/infra/docker"

    # 使用 docker compose 或 docker-compose
    if docker compose version &> /dev/null; then
        docker compose up -d
    else
        docker-compose up -d
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
    echo -e "${GREEN}Starting Mock server...${NC}"
    cd "$PROJECT_ROOT/infra/mock"

    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}Installing dependencies...${NC}"
        npm install
    fi

    # 检查是否已经在运行
    if lsof -i :3000 &> /dev/null; then
        echo -e "${YELLOW}Port 3000 is already in use${NC}"
    else
        npm start &
        MOCK_PID=$!
        echo "Mock server PID: $MOCK_PID"
        sleep 2
    fi

    echo -e "${GREEN}  Mock server is running on port 3000${NC}"
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
    echo "  Mock API:    http://localhost:3000"
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
        docker compose down
    else
        docker-compose down
    fi

    # 停止 Mock 服务
    if lsof -i :3000 &> /dev/null; then
        kill $(lsof -t -i :3000) 2>/dev/null || true
    fi

    echo -e "${GREEN}All services stopped${NC}"
}

# 查看日志
show_logs() {
    cd "$PROJECT_ROOT/infra/docker"

    if docker compose version &> /dev/null; then
        docker compose logs -f
    else
        docker-compose logs -f
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
