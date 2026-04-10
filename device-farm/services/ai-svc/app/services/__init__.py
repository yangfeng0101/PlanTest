# Services Package
from app.services.ocr import ocr_service, OCRService
from app.services.element_locator import element_locator_service, ElementLocatorService

__all__ = ["ocr_service", "OCRService", "element_locator_service", "ElementLocatorService"]
