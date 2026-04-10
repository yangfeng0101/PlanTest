# OCR API Routes
from fastapi import APIRouter, HTTPException, File, UploadFile, Query, Form
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel
import logging
import base64

from app.services.ocr import ocr_service

logger = logging.getLogger(__name__)

router = APIRouter()


class OCRRequest(BaseModel):
    """OCR request with base64 image"""
    image_base64: str
    language: Optional[str] = None


class TextRegionResponse(BaseModel):
    """Text region response"""
    text: str
    confidence: float
    bbox: List[List[int]]
    center: List[int]


class OCRResponse(BaseModel):
    """OCR response"""
    text: str
    regions: List[TextRegionResponse]
    language: str
    processing_time_ms: float


class FindTextRequest(BaseModel):
    """Find text request"""
    image_base64: str
    search_text: str
    language: Optional[str] = None
    threshold: float = 0.8


class FindTextResponse(BaseModel):
    """Find text response"""
    matches: List[TextRegionResponse]
    found: bool


@router.post("/recognize", response_model=OCRResponse)
async def recognize_text(request: OCRRequest):
    """
    Perform OCR on base64 encoded image

    Returns recognized text and bounding boxes for each text region.
    """
    try:
        result = await ocr_service.recognize_from_base64(
            base64_data=request.image_base64,
            language=request.language,
        )

        regions = [
            TextRegionResponse(
                text=r.text,
                confidence=r.confidence,
                bbox=[[p[0], p[1]] for p in r.bbox],
                center=list(r.center),
            )
            for r in result.regions
        ]

        return OCRResponse(
            text=result.text,
            regions=regions,
            language=result.language,
            processing_time_ms=result.processing_time_ms,
        )

    except Exception as e:
        logger.error(f"OCR recognition failed: {e}")
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")


@router.post("/recognize/file", response_model=OCRResponse)
async def recognize_text_from_file(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
):
    """
    Perform OCR on uploaded image file

    Supports PNG, JPEG, and other common image formats.
    """
    try:
        image_data = await file.read()

        result = await ocr_service.recognize(
            image_data=image_data,
            language=language,
        )

        regions = [
            TextRegionResponse(
                text=r.text,
                confidence=r.confidence,
                bbox=[[p[0], p[1]] for p in r.bbox],
                center=list(r.center),
            )
            for r in result.regions
        ]

        return OCRResponse(
            text=result.text,
            regions=regions,
            language=result.language,
            processing_time_ms=result.processing_time_ms,
        )

    except Exception as e:
        logger.error(f"OCR recognition from file failed: {e}")
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")


@router.post("/find", response_model=FindTextResponse)
async def find_text(request: FindTextRequest):
    """
    Find specific text in image

    Returns matching text regions with their bounding boxes.
    """
    try:
        # Remove data URL prefix if present
        base64_data = request.image_base64
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]

        image_data = base64.b64decode(base64_data)

        matches = await ocr_service.find_text(
            image_data=image_data,
            search_text=request.search_text,
            language=request.language,
            threshold=request.threshold,
        )

        regions = [
            TextRegionResponse(
                text=r.text,
                confidence=r.confidence,
                bbox=[[p[0], p[1]] for p in r.bbox],
                center=list(r.center),
            )
            for r in matches
        ]

        return FindTextResponse(
            matches=regions,
            found=len(matches) > 0,
        )

    except Exception as e:
        logger.error(f"Find text failed: {e}")
        raise HTTPException(status_code=500, detail=f"Find text failed: {str(e)}")


@router.get("/health")
async def ocr_health():
    """Check OCR engine status"""
    ocr_service.initialize()

    engine_status = {
        "engine": ocr_service.engine,
        "paddleocr": ocr_service._paddleocr is not None,
        "tesseract": ocr_service._tesseract_available,
        "language": ocr_service.language,
    }

    return {
        "status": "ready" if (ocr_service._paddleocr is not None or ocr_service._tesseract_available) else "not_configured",
        "engines": engine_status,
    }
