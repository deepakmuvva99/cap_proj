"""Scanned Image Extractor using Tesseract OCR with multi-language support."""
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image
import pytesseract
from app.extractors.parser_utils import extract_and_merge_fields

logger = logging.getLogger("agent.extractors.image")


def extract_from_image(file_path: str, meta_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extract text from scanned image files (PNG, JPG, TIFF) via Tesseract OCR."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {file_path}")

    try:
        img = Image.open(path)
        # Convert to RGB if palette or transparency
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # Run OCR with English, German, and Spanish language models
        raw_text = pytesseract.image_to_string(img, lang="eng+deu+spa").strip()
    except Exception as exc:
        logger.error("OCR execution failed for image %s: %s", file_path, exc)
        raw_text = ""

    parsed_fields = extract_and_merge_fields(raw_text, meta_data)

    return {
        "raw_text": raw_text,
        "extraction_method": "tesseract",
        "fields": parsed_fields,
    }
