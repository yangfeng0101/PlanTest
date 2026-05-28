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
    PORT: int = int(os.getenv("PORT", "8003"))

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
    MINIO_PUBLIC_ENDPOINT: str = os.getenv("MINIO_PUBLIC_ENDPOINT", MINIO_ENDPOINT)
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "device-farm")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    MINIO_REGION: str = os.getenv("MINIO_REGION", "us-east-1")

    # Appium
    APPIUM_HOST: str = os.getenv("APPIUM_HOST", "http://localhost:4723")
    IOS_APPIUM_HOST: str = os.getenv("IOS_APPIUM_HOST", "")
    IOS_XCODE_ORG_ID: str = os.getenv("IOS_XCODE_ORG_ID", "")
    IOS_XCODE_SIGNING_ID: str = os.getenv("IOS_XCODE_SIGNING_ID", "Apple Development")
    IOS_WDA_BUNDLE_ID: str = os.getenv("IOS_WDA_BUNDLE_ID", "")
    IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION: bool = (
        os.getenv("IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION", "false").lower() == "true"
    )
    APPIUM_TIMEOUT: int = int(os.getenv("APPIUM_TIMEOUT", "300"))
    APPIUM_REMOTE_ADB_HOST: str = os.getenv("APPIUM_REMOTE_ADB_HOST", "")

    # Script Storage
    SCRIPT_STORAGE_PATH: str = os.getenv(
        "SCRIPT_STORAGE_PATH",
        "/tmp/device-farm/scripts"
    )

    # Report Service
    REPORT_SERVICE_URL: str = os.getenv(
        "REPORT_SERVICE_URL",
        "http://localhost:8004"
    )

    # Midscene AI runner. Empty means AI script methods are disabled.
    MIDSCENE_RUNNER_URL: str = os.getenv("MIDSCENE_RUNNER_URL", "")

    # Device Service
    DEVICE_SERVICE_URL: str = os.getenv(
        "DEVICE_SERVICE_URL",
        "http://localhost:8001"
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
    SCRIPT_SCHEDULE_POLL_INTERVAL_SECONDS: int = int(os.getenv("SCRIPT_SCHEDULE_POLL_INTERVAL_SECONDS", "10"))

    # JWT Authentication
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "120"))  # 2 hours
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))  # 7 days

    # Cookie settings for HTTP-only cookie authentication
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"  # True in production (HTTPS)
    COOKIE_SAMESITE: str = os.getenv("COOKIE_SAMESITE", "lax")  # 'strict', 'lax', or 'none'

    # WebSocket settings
    WS_HEARTBEAT_INTERVAL: int = int(os.getenv("WS_HEARTBEAT_INTERVAL", "30"))  # seconds between heartbeats
    WS_CONNECTION_TIMEOUT: int = int(os.getenv("WS_CONNECTION_TIMEOUT", "300"))  # 5 minutes default
    WS_PING_TIMEOUT: int = int(os.getenv("WS_PING_TIMEOUT", "10"))  # seconds to wait for pong response

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

    def validate_api_key_config(self) -> None:
        """Validate API Key configuration. Call at startup to ensure security."""
        if self.API_KEY_ENABLED and not self.API_KEY:
            raise ValueError(
                "API_KEY_ENABLED is true but API_KEY is not set. "
                "Either set API_KEY environment variable or set API_KEY_ENABLED=false."
            )

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
