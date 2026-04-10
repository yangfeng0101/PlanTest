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
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

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

    # HDC config (HarmonyOS Device Connector)
    HDC_PATH: str = "hdc"

    # Device scan interval (seconds)
    DEVICE_SCAN_INTERVAL: int = 30

    # WebSocket config
    WS_HEARTBEAT_INTERVAL: int = 30

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
