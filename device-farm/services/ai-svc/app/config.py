# AI Service Configuration
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service
    SERVICE_NAME: str = "ai-svc"
    SERVICE_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # API
    API_PREFIX: str = "/api/v1"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8005"))

    # OCR Configuration
    OCR_ENGINE: str = os.getenv("OCR_ENGINE", "paddleocr")  # paddleocr or tesseract
    OCR_LANGUAGE: str = os.getenv("OCR_LANGUAGE", "ch")  # ch for Chinese, en for English

    # Tesseract Configuration (if using tesseract)
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "tesseract")

    # AI Model Configuration
    AI_MODEL_PATH: str = os.getenv("AI_MODEL_PATH", "/models")
    AI_DEVICE: str = os.getenv("AI_DEVICE", "cpu")  # cpu or cuda

    # GPU Configuration
    CUDA_VISIBLE_DEVICES: str = os.getenv("CUDA_VISIBLE_DEVICES", "0")

    # CORS - comma-separated origins from environment
    CORS_ORIGINS: list = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
        if origin.strip()
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
