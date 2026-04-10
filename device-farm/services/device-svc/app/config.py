# Device Service Configuration
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

    # Database
    DATABASE_URL: str = "postgresql://admin@localhost:5432/device_farm"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # ADB config
    ADB_PATH: str = "adb"
    ADB_SERVER_HOST: str = "localhost"
    ADB_SERVER_PORT: int = 5037

    # Device scan interval (seconds)
    DEVICE_SCAN_INTERVAL: int = 30

    # WebSocket config
    WS_HEARTBEAT_INTERVAL: int = 30

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
