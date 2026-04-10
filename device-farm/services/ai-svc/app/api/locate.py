# Element Location API Routes
from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from typing import Optional, List
from pydantic import BaseModel
import logging
import base64

from app.services.element_locator import element_locator_service, ElementType

logger = logging.getLogger(__name__)

router = APIRouter()


class LocateRequest(BaseModel):
    """Element location request"""
    image_base64: str
    description: str
    language: Optional[str] = None


class LocatedElementResponse(BaseModel):
    """Located element response"""
    element_type: str
    description: str
    text: Optional[str]
    confidence: float
    bbox: List[List[int]]
    center: List[int]
    clickable: bool
    attributes: dict


class LocateResponse(BaseModel):
    """Element location response"""
    elements: List[LocatedElementResponse]
    query: str
    processing_time_ms: float
    found: bool


class FindSimilarRequest(BaseModel):
    """Find similar elements request"""
    image_base64: str
    reference_text: str
    threshold: float = 0.7
    language: Optional[str] = None


class FindSimilarResponse(BaseModel):
    """Find similar elements response"""
    elements: List[LocatedElementResponse]
    count: int


@router.post("/locate", response_model=LocateResponse)
async def locate_element(request: LocateRequest):
    """
    Locate UI element based on natural language description

    Examples:
    - "点击登录按钮" - Find login button
    - "输入用户名" - Find username input field
    - "确定" - Find confirm button
    """
    try:
        result = await element_locator_service.locate_from_base64(
            base64_data=request.image_base64,
            description=request.description,
            language=request.language,
        )

        elements = [
            LocatedElementResponse(
                element_type=e.element_type.value,
                description=e.description,
                text=e.text,
                confidence=e.confidence,
                bbox=[[p[0], p[1]] for p in e.bbox],
                center=list(e.center),
                clickable=e.clickable,
                attributes=e.attributes,
            )
            for e in result.elements
        ]

        return LocateResponse(
            elements=elements,
            query=result.query,
            processing_time_ms=result.processing_time_ms,
            found=len(elements) > 0,
        )

    except Exception as e:
        logger.error(f"Element location failed: {e}")
        raise HTTPException(status_code=500, detail=f"Location failed: {str(e)}")


@router.post("/locate/file", response_model=LocateResponse)
async def locate_element_from_file(
    file: UploadFile = File(...),
    description: str = Form(...),
    language: Optional[str] = Form(None),
):
    """
    Locate UI element from uploaded image file

    Upload an image and provide a natural language description to locate elements.
    """
    try:
        image_data = await file.read()

        result = await element_locator_service.locate_element(
            image_data=image_data,
            description=description,
            language=language,
        )

        elements = [
            LocatedElementResponse(
                element_type=e.element_type.value,
                description=e.description,
                text=e.text,
                confidence=e.confidence,
                bbox=[[p[0], p[1]] for p in e.bbox],
                center=list(e.center),
                clickable=e.clickable,
                attributes=e.attributes,
            )
            for e in result.elements
        ]

        return LocateResponse(
            elements=elements,
            query=result.query,
            processing_time_ms=result.processing_time_ms,
            found=len(elements) > 0,
        )

    except Exception as e:
        logger.error(f"Element location from file failed: {e}")
        raise HTTPException(status_code=500, detail=f"Location failed: {str(e)}")


@router.post("/similar", response_model=FindSimilarResponse)
async def find_similar_elements(request: FindSimilarRequest):
    """
    Find elements similar to reference text

    Useful for finding all buttons or text elements that match a pattern.
    """
    try:
        # Remove data URL prefix if present
        base64_data = request.image_base64
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]

        image_data = base64.b64decode(base64_data)

        elements = await element_locator_service.find_similar_elements(
            image_data=image_data,
            reference_text=request.reference_text,
            threshold=request.threshold,
            language=request.language,
        )

        response_elements = [
            LocatedElementResponse(
                element_type=e.element_type.value,
                description=e.description,
                text=e.text,
                confidence=e.confidence,
                bbox=[[p[0], p[1]] for p in e.bbox],
                center=list(e.center),
                clickable=e.clickable,
                attributes=e.attributes,
            )
            for e in elements
        ]

        return FindSimilarResponse(
            elements=response_elements,
            count=len(response_elements),
        )

    except Exception as e:
        logger.error(f"Find similar elements failed: {e}")
        raise HTTPException(status_code=500, detail=f"Find similar failed: {str(e)}")


@router.get("/element-types")
async def get_element_types():
    """Get supported element types"""
    return {
        "types": [t.value for t in ElementType],
        "keywords": {
            t.value: element_locator_service.ELEMENT_KEYWORDS.get(t, [])
            for t in ElementType
        }
    }
