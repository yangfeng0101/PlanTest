# Test Service Configuration
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Service
    SERVICE_NAME: str = "test-svc"
    SERVICE_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # API
    API_PREFIX: str = "/api/v1"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8001"))

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://admin@localhost:5432/device_farm"
    )

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Celery
    CELERY_BROKER_URL: str = os.getenv(
        "CELERY_BROKER_URL",
        "redis://localhost:6379/1"
    )
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND",
        "redis://localhost:6379/2"
    )
    CELERY_TIMEZONE: str = os.getenv("CELERY_TIMEZONE", "Asia/Shanghai")
    CELERY_ENABLE_UTC: bool = os.getenv("CELERY_ENABLE_UTC", "false").lower() == "true"

    # MinIO
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "device-farm")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    # Appium
    APPIUM_HOST: str = os.getenv("APPIUM_HOST", "http://localhost:4723")
    APPIUM_TIMEOUT: int = int(os.getenv("APPIUM_TIMEOUT", "300"))

    # Script Storage
    SCRIPT_STORAGE_PATH: str = os.getenv(
        "SCRIPT_STORAGE_PATH",
        "/tmp/device-farm/scripts"
    )

    # Report Service
    REPORT_SERVICE_URL: str = os.getenv(
        "REPORT_SERVICE_URL",
        "http://localhost:8002"
    )

    # API Authentication
    API_KEY: str = os.getenv("API_KEY", "")
    API_KEY_ENABLED: bool = os.getenv("API_KEY_ENABLED", "true").lower() == "true"

    # Celery Beat Scheduler
    CELERY_BEAT_SCHEDULE: dict = {}  # Dynamic schedules loaded from database
    CELERY_BEAT_SCHEDULER: str = "celery.beat:PersistentScheduler"
    CELERY_BEAT_SCHEDULE_FILENAME: str = os.getenv(
        "CELERY_BEAT_SCHEDULE_FILENAME",
        "/tmp/device-farm/celerybeat-schedule"
    )

    # JWT Authentication
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "120"))  # 2 hours
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))  # 7 days

    # CORS - comma-separated origins from environment
    CORS_ORIGINS: list = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
        if origin.strip()
    ]

    def validate_jwt_config(self) -> None:
        """Validate JWT configuration. Call at startup to ensure security."""
        if not self.JWT_SECRET_KEY:
            raise ValueError(
                "JWT_SECRET_KEY environment variable must be set. "
                "Generate a secure key with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if len(self.JWT_SECRET_KEY) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters for security. "
                "Generate a secure key with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
