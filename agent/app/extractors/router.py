"""Router and file monitor dispatcher for incoming invoice files."""
import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from app.extractors.pdf_extractor import extract_from_pdf
from app.extractors.docx_extractor import extract_from_docx
from app.extractors.image_extractor import extract_from_image
from app.db import is_checksum_processed

logger = logging.getLogger("agent.extractors.router")


def compute_file_checksum(file_path: str) -> str:
    """Compute SHA-256 hash of a file's binary contents."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_accompanying_metadata(file_path: str) -> Optional[Dict[str, Any]]:
    """Check for and load an accompanying .meta.json file if one exists."""
    p = Path(file_path)
    meta_path = p.with_suffix(".meta.json")
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not read meta file %s: %s", meta_path, exc)
    return None


def route_and_extract(file_path: str) -> Dict[str, Any]:
    """Inspects file, computes checksum, checks audit history, and routes to extractor."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Invoice file not found: {file_path}")

    checksum = compute_file_checksum(file_path)
    meta_data = load_accompanying_metadata(file_path)

    # Check for already processed checksum
    already_audited = is_checksum_processed(checksum)
    if already_audited:
        logger.info("Invoice file '%s' (checksum %s) has already been audited. Skipping re-extraction.", path.name, checksum[:8])
        return {
            "file_path": str(path.resolve()),
            "file_name": path.name,
            "file_checksum": checksum,
            "already_audited": True,
            "raw_text": "",
            "extraction_method": "skipped",
            "fields": {},
            "meta_data": meta_data,
        }

    ext = path.suffix.lower()
    logger.info("Routing invoice %s (type %s, checksum %s)", path.name, ext, checksum[:8])

    if ext == ".pdf":
        result = extract_from_pdf(file_path, meta_data)
    elif ext == ".docx":
        result = extract_from_docx(file_path, meta_data)
    elif ext in (".png", ".jpg", ".jpeg", ".tiff"):
        result = extract_from_image(file_path, meta_data)
    else:
        raise ValueError(f"Unsupported invoice file extension: {ext}")

    return {
        "file_path": str(path.resolve()),
        "file_name": path.name,
        "file_checksum": checksum,
        "already_audited": False,
        "raw_text": result["raw_text"],
        "extraction_method": result["extraction_method"],
        "fields": result["fields"],
        "meta_data": meta_data,
    }
