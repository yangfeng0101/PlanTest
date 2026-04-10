# Element Locator Service for Device Farm
import base64
import io
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re

from app.config import settings
from app.services.ocr import ocr_service, TextRegion

logger = logging.getLogger(__name__)


class ElementType(str, Enum):
    """Element types for location"""
    BUTTON = "button"
    TEXT = "text"
    INPUT = "input"
    ICON = "icon"
    IMAGE = "image"
    LINK = "link"
    UNKNOWN = "unknown"


@dataclass
class LocatedElement:
    """Located UI element"""
    element_type: ElementType
    description: str
    text: Optional[str]
    confidence: float
    bbox: List[Tuple[int, int]]  # [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
    center: Tuple[int, int]
    clickable: bool
    attributes: Dict[str, Any]


@dataclass
class ElementLocationResult:
    """Result of element location"""
    elements: List[LocatedElement]
    query: str
    processing_time_ms: float


class ElementLocatorService:
    """Service for locating UI elements based on description"""

    # Keywords for element type detection
    ELEMENT_KEYWORDS = {
        ElementType.BUTTON: ["按钮", "button", "点击", "click", "确定", "取消", "提交", "确认", "登录", "注册", "保存", "删除"],
        ElementType.INPUT: ["输入", "input", "文本框", "输入框", "搜索", "search", "编辑", "edit"],
        ElementType.TEXT: ["文本", "text", "标题", "title", "内容", "content", "描述", "description"],
        ElementType.ICON: ["图标", "icon", "图片", "image", "头像", "avatar"],
        ElementType.LINK: ["链接", "link", "跳转", "navigate"],
    }

    def __init__(self):
        self._initialized = False

    def initialize(self):
        """Initialize the element locator"""
        if self._initialized:
            return

        # Ensure OCR is initialized
        ocr_service.initialize()
        self._initialized = True

    def _detect_element_type(self, description: str) -> ElementType:
        """Detect element type from description"""
        desc_lower = description.lower()

        for elem_type, keywords in self.ELEMENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in desc_lower:
                    return elem_type

        return ElementType.UNKNOWN

    def _extract_search_terms(self, description: str) -> List[str]:
        """Extract search terms from natural language description"""
        # Remove common action words
        action_words = ["点击", "点击一下", "找到", "定位", "查找", "寻找", "选择", "click", "find", "locate", "select", "tap"]

        cleaned = description.lower()
        for word in action_words:
            cleaned = cleaned.replace(word, "")

        # Split by common delimiters
        terms = re.split(r'[\s,，、的]', cleaned)
        terms = [t.strip() for t in terms if t.strip()]

        return terms

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings"""
        if not text1 or not text2:
            return 0.0

        t1 = text1.lower()
        t2 = text2.lower()

        # Exact match
        if t1 == t2:
            return 1.0

        # Contains
        if t1 in t2 or t2 in t1:
            return 0.8

        # Character overlap
        common = sum(1 for c in t1 if c in t2)
        return common / max(len(t1), len(t2)) * 0.6

    async def locate_element(
        self,
        image_data: bytes,
        description: str,
        language: Optional[str] = None,
    ) -> ElementLocationResult:
        """
        Locate UI element based on natural language description

        Args:
            image_data: Image bytes
            description: Natural language description (e.g., "点击登录按钮")
            language: OCR language

        Returns:
            ElementLocationResult with located elements
        """
        import time
        start_time = time.time()

        self.initialize()

        # Detect element type
        element_type = self._detect_element_type(description)

        # Extract search terms
        search_terms = self._extract_search_terms(description)

        # Run OCR to get text regions
        ocr_result = await ocr_service.recognize(image_data, language)

        # Find matching elements
        located_elements = []

        for region in ocr_result.regions:
            # Check if any search term matches
            best_similarity = 0.0
            matched_term = None

            for term in search_terms:
                similarity = self._calculate_text_similarity(term, region.text)
                if similarity > best_similarity:
                    best_similarity = similarity
                    matched_term = term

            # If good match found
            if best_similarity >= 0.5:
                # Determine if clickable based on element type and keywords
                is_clickable = element_type in [ElementType.BUTTON, ElementType.LINK] or \
                               any(kw in region.text.lower() for kw in ["确定", "取消", "登录", "提交", "button", "click"])

                element = LocatedElement(
                    element_type=element_type,
                    description=description,
                    text=region.text,
                    confidence=min(region.confidence * (best_similarity + 0.2), 1.0),
                    bbox=region.bbox,
                    center=region.center,
                    clickable=is_clickable,
                    attributes={
                        "matched_term": matched_term,
                        "text_similarity": best_similarity,
                    },
                )
                located_elements.append(element)

        # Sort by confidence
        located_elements.sort(key=lambda e: e.confidence, reverse=True)

        processing_time = (time.time() - start_time) * 1000

        return ElementLocationResult(
            elements=located_elements,
            query=description,
            processing_time_ms=processing_time,
        )

    async def locate_from_base64(
        self,
        base64_data: str,
        description: str,
        language: Optional[str] = None,
    ) -> ElementLocationResult:
        """
        Locate element from base64 encoded image

        Args:
            base64_data: Base64 encoded image
            description: Natural language description
            language: OCR language

        Returns:
            ElementLocationResult
        """
        # Remove data URL prefix if present
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]

        image_data = base64.b64decode(base64_data)
        return await self.locate_element(image_data, description, language)

    async def find_similar_elements(
        self,
        image_data: bytes,
        reference_text: str,
        threshold: float = 0.7,
        language: Optional[str] = None,
    ) -> List[LocatedElement]:
        """
        Find elements similar to reference text

        Args:
            image_data: Image bytes
            reference_text: Text to find similar elements for
            threshold: Similarity threshold
            language: OCR language

        Returns:
            List of similar elements
        """
        self.initialize()

        ocr_result = await ocr_service.recognize(image_data, language)

        similar = []
        for region in ocr_result.regions:
            similarity = self._calculate_text_similarity(reference_text, region.text)

            if similarity >= threshold:
                element = LocatedElement(
                    element_type=ElementType.TEXT,
                    description=f"Similar to: {reference_text}",
                    text=region.text,
                    confidence=region.confidence * similarity,
                    bbox=region.bbox,
                    center=region.center,
                    clickable=False,
                    attributes={
                        "reference_text": reference_text,
                        "similarity": similarity,
                    },
                )
                similar.append(element)

        similar.sort(key=lambda e: e.confidence, reverse=True)
        return similar


# Global instance
element_locator_service = ElementLocatorService()
