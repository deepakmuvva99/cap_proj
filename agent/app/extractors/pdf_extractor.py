"""PDF Extractor supporting direct text extraction and OCR fallback."""
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import pdfplumber
from PIL import Image
import pytesseract
from app.extractors.parser_utils import extract_and_merge_fields

logger = logging.getLogger("agent.extractors.pdf")


def extract_from_pdf(file_path: str, meta_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extract raw text and parsed fields from a PDF document."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    raw_text = ""
    extraction_method = "pdfplumber"

    # Step 1: Direct text extraction using pdfplumber
    try:
        with pdfplumber.open(path) as pdf:
            pages_text = []
            for p in pdf.pages:
                text = p.extract_text()
                if text:
                    pages_text.append(text)
            raw_text = "\n".join(pages_text).strip()
    except Exception as exc:
        logger.warning("pdfplumber direct extraction failed on %s: %s", file_path, exc)
        raw_text = ""

    # Step 2: Fall back to OCR if raw text is empty or insufficient (e.g. scanned PDF)
    if len(raw_text) < 30:
        logger.info("Direct text extraction yielded insufficient text (%d chars). Falling back to OCR.", len(raw_text))
        extraction_method = "tesseract_pdf"
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(file_path)
            ocr_text = []
            for img in images:
                text = pytesseract.image_to_string(img, lang="eng+deu+spa")
                ocr_text.append(text)
            raw_text = "\n".join(ocr_text).strip()
        except Exception as ocr_exc:
            logger.error("OCR fallback failed on %s: %s", file_path, ocr_exc)

    parsed_fields = extract_and_merge_fields(raw_text, meta_data)

    return {
        "raw_text": raw_text,
        "extraction_method": extraction_method,
        "fields": parsed_fields,
    }
