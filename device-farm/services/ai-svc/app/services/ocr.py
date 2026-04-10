# OCR Service for Device Farm
import base64
import io
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from app.config import settings

logger = logging.getLogger(__name__)


class OCRLanguage(str, Enum):
    """Supported OCR languages"""
    CHINESE = "ch"
    ENGLISH = "en"
    JAPANESE = "japan"
    KOREAN = "korean"


@dataclass
class TextRegion:
    """Detected text region with bounding box"""
    text: str
    confidence: float
    bbox: List[Tuple[int, int]]  # [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
    center: Tuple[int, int]


@dataclass
class OCRResult:
    """OCR recognition result"""
    text: str
    regions: List[TextRegion]
    language: str
    processing_time_ms: float


class OCRService:
    """OCR service supporting multiple engines"""

    def __init__(self):
        self.engine = settings.OCR_ENGINE
        self.language = settings.OCR_LANGUAGE
        self._paddleocr = None
        self._tesseract_available = False
        self._initialized = False

    def _initialize_paddleocr(self):
        """Initialize PaddleOCR engine"""
        if self._paddleocr is not None:
            return True

        try:
            from paddleocr import PaddleOCR

            # Initialize with language support
            self._paddleocr = PaddleOCR(
                use_angle_cls=True,
                lang=self.language,
                show_log=False,
                use_gpu=(settings.AI_DEVICE == "cuda"),
            )
            logger.info(f"PaddleOCR initialized with language: {self.language}")
            return True

        except ImportError:
            logger.warning("PaddleOCR not installed. Install with: pip install paddleocr")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR: {e}")
            return False

    def _initialize_tesseract(self):
        """Check if Tesseract is available"""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            self._tesseract_available = True
            logger.info("Tesseract OCR is available")
            return True
        except ImportError:
            logger.warning("pytesseract not installed. Install with: pip install pytesseract")
            return False
        except Exception as e:
            logger.warning(f"Tesseract not available: {e}")
            return False

    def initialize(self):
        """Initialize OCR engine"""
        if self._initialized:
            return

        if self.engine == "paddleocr":
            self._initialize_paddleocr()
        elif self.engine == "tesseract":
            self._initialize_tesseract()
        else:
            # Try paddleocr first, then tesseract
            if not self._initialize_paddleocr():
                self._initialize_tesseract()

        self._initialized = True

    async def recognize(
        self,
        image_data: bytes,
        language: Optional[str] = None,
    ) -> OCRResult:
        """
        Perform OCR on image data

        Args:
            image_data: Image bytes (PNG, JPEG, etc.)
            language: Override language (ch, en, etc.)

        Returns:
            OCRResult with recognized text and regions
        """
        import time
        start_time = time.time()

        self.initialize()

        lang = language or self.language

        if self._paddleocr is not None:
            result = await self._recognize_with_paddleocr(image_data, lang)
        elif self._tesseract_available:
            result = await self._recognize_with_tesseract(image_data, lang)
        else:
            # Fallback: return empty result
            logger.warning("No OCR engine available")
            result = OCRResult(
                text="",
                regions=[],
                language=lang,
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        result.processing_time_ms = (time.time() - start_time) * 1000
        return result

    async def _recognize_with_paddleocr(
        self,
        image_data: bytes,
        language: str,
    ) -> OCRResult:
        """Recognize text using PaddleOCR"""
        import numpy as np
        from PIL import Image

        try:
            # Convert bytes to numpy array
            image = Image.open(io.BytesIO(image_data))
            image_array = np.array(image)

            # Run OCR
            result = self._paddleocr.ocr(image_array, cls=True)

            regions = []
            full_text_parts = []

            if result and result[0]:
                for line in result[0]:
                    # line format: [bbox, (text, confidence)]
                    bbox = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    text = line[1][0]
                    confidence = float(line[1][1])

                    # Calculate center
                    x_coords = [p[0] for p in bbox]
                    y_coords = [p[1] for p in bbox]
                    center = (int(sum(x_coords) / 4), int(sum(y_coords) / 4))

                    region = TextRegion(
                        text=text,
                        confidence=confidence,
                        bbox=[(int(p[0]), int(p[1])) for p in bbox],
                        center=center,
                    )
                    regions.append(region)
                    full_text_parts.append(text)

            return OCRResult(
                text="\n".join(full_text_parts),
                regions=regions,
                language=language,
                processing_time_ms=0,  # Set by caller
            )

        except Exception as e:
            logger.error(f"PaddleOCR recognition failed: {e}")
            return OCRResult(
                text="",
                regions=[],
                language=language,
                processing_time_ms=0,
            )

    async def _recognize_with_tesseract(
        self,
        image_data: bytes,
        language: str,
    ) -> OCRResult:
        """Recognize text using Tesseract"""
        import pytesseract
        from PIL import Image

        try:
            image = Image.open(io.BytesIO(image_data))

            # Map language code
            lang_map = {
                "ch": "chi_sim",
                "en": "eng",
                "japan": "jpn",
                "korean": "kor",
            }
            tess_lang = lang_map.get(language, "eng")

            # Get text
            text = pytesseract.image_to_string(image, lang=tess_lang)

            # Get bounding boxes
            data = pytesseract.image_to_data(image, lang=tess_lang, output_type=pytesseract.Output.DICT)

            regions = []
            for i in range(len(data['text'])):
                if data['text'][i].strip():
                    x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                    bbox = [
                        (x, y),
                        (x + w, y),
                        (x + w, y + h),
                        (x, y + h),
                    ]
                    center = (x + w // 2, y + h // 2)

                    region = TextRegion(
                        text=data['text'][i],
                        confidence=float(data['conf'][i]) / 100.0 if data['conf'][i] > 0 else 0.5,
                        bbox=bbox,
                        center=center,
                    )
                    regions.append(region)

            return OCRResult(
                text=text.strip(),
                regions=regions,
                language=language,
                processing_time_ms=0,  # Set by caller
            )

        except Exception as e:
            logger.error(f"Tesseract recognition failed: {e}")
            return OCRResult(
                text="",
                regions=[],
                language=language,
                processing_time_ms=0,
            )

    async def recognize_from_base64(
        self,
        base64_data: str,
        language: Optional[str] = None,
    ) -> OCRResult:
        """
        Perform OCR on base64 encoded image

        Args:
            base64_data: Base64 encoded image string
            language: Override language

        Returns:
            OCRResult
        """
        # Remove data URL prefix if present
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]

        image_data = base64.b64decode(base64_data)
        return await self.recognize(image_data, language)

    async def find_text(
        self,
        image_data: bytes,
        search_text: str,
        language: Optional[str] = None,
        threshold: float = 0.8,
    ) -> List[TextRegion]:
        """
        Find specific text in image

        Args:
            image_data: Image bytes
            search_text: Text to search for
            language: OCR language
            threshold: Minimum confidence threshold

        Returns:
            List of matching TextRegions
        """
        result = await self.recognize(image_data, language)

        matches = []
        search_lower = search_text.lower()

        for region in result.regions:
            if region.confidence >= threshold:
                if search_lower in region.text.lower():
                    matches.append(region)

        return matches


# Global instance
ocr_service = OCRService()
