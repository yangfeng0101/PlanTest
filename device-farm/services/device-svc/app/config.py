# Device Service Configuration
import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""
    # Service info
    SERVICE_NAME: str = "device-svc"
    SERVICE_VERSION: str = "1.0.0"

    # Server config
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    DEBUG: bool = True

    # API config
    API_PREFIX: str = "/api/v1"

    # Database (use asyncpg for async SQLAlchemy)
    DATABASE_URL: str = "postgresql+asyncpg://admin@localhost:5432/device_farm"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # ADB config
    ADB_PATH: str = "adb"
    ADB_SERVER_HOST: str = "localhost"
    ADB_SERVER_PORT: int = 5037

    # HDC config (HarmonyOS Device Connector)
    HDC_PATH: str = "hdc"

    # Device scan interval (seconds)
    DEVICE_SCAN_INTERVAL: int = 30

    # WebSocket config
    WS_HEARTBEAT_INTERVAL: int = 30  # seconds between heartbeats
    WS_CONNECTION_TIMEOUT: int = 60  # seconds before connection is considered stale
    WS_PING_TIMEOUT: int = 10  # seconds to wait for pong response
    WS_CLEANUP_INTERVAL: int = 60  # seconds between cleanup runs

    # Metrics collection config
    METRICS_COLLECTION_INTERVAL: int = 10  # seconds between metrics collection
    METRICS_HISTORY_RETENTION_HOURS: int = 24  # hours to retain metrics history
    METRICS_PUSH_INTERVAL: int = 5  # seconds between WebSocket metrics push

    # Service URLs
    REPORT_SVC_URL: str = os.getenv("REPORT_SVC_URL", "http://localhost:8004")
    IOS_AGENT_URL: str = os.getenv("IOS_AGENT_URL", "")
    IOS_AGENT_REQUEST_TIMEOUT: float = float(os.getenv("IOS_AGENT_REQUEST_TIMEOUT", "90"))

    # CORS - comma-separated origins from environment
    CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
        if origin.strip()
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
