# API Package
from app.api.ocr import router as ocr_router
from app.api.locate import router as locate_router

__all__ = ["ocr_router", "locate_router"]
