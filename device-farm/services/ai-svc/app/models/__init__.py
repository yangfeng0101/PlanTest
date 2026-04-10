# AI Service Models
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple
from enum import Enum


class OCRResult(BaseModel):
    """Single OCR text result with position"""
    text: str = Field(..., description="Recognized text")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Recognition confidence")
    box: List[Tuple[float, float]] = Field(
        ...,
        description="Bounding box coordinates (4 corners)"
    )


class OCRResponse(BaseModel):
    """OCR API response"""
    success: bool = Field(..., description="Whether OCR succeeded")
    results: List[OCRResult] = Field(default_factory=list, description="OCR results")
    full_text: str = Field(default="", description="Combined full text")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")


class Language(str, Enum):
    """Supported OCR languages"""
    CHINESE = "ch"  # Chinese + English
    ENGLISH = "en"
    KOREAN = "korean"
    JAPANESE = "japan"


class OCRRequest(BaseModel):
    """OCR API request for URL-based image"""
    image_url: Optional[str] = Field(None, description="Image URL to process")
    language: Language = Field(Language.CHINESE, description="OCR language")
    return_box: bool = Field(True, description="Return bounding box coordinates")
