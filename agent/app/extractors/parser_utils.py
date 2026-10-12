"""Parsing utilities for extracting structured fields from invoice text."""
import re
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import rules_config, personas_config, settings
from app.llm.bedrock import bedrock_manager

logger = logging.getLogger("agent.extractors.parser_utils")


def clean_number(value_str: str) -> float:
    """Sanitize and parse float from currency or quantity strings."""
    if not value_str:
        return 0.0
    s = re.sub(r"[^\d.,\-]", "", str(value_str).strip())
    # Handle European decimal comma if e.g. 1.250,50 or 25,00
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def extract_currency(text: str) -> Optional[str]:
    """Extract 3-letter currency code from text or symbols."""
    symbol_map = rules_config.get("currency_symbol_map", {
        "$": "USD", "€": "EUR", "₹": "INR", "£": "GBP"
    })
    for symbol, code in symbol_map.items():
        if symbol in text:
            return code

    accepted = rules_config.get("accepted_currencies", ["USD", "EUR", "INR", "GBP"])
    for curr in accepted:
        if re.search(rf"\b{curr}\b", text, re.IGNORECASE):
            return curr
    return "USD"


def parse_date_string(date_str: str) -> Optional[str]:
    """Parse various date formats into YYYY-MM-DD."""
    if not date_str:
        return None
    cleaned = date_str.strip()
    formats = rules_config.get("date_validation", {}).get("accepted_formats", [
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%d.%m.%Y"
    ])
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Try regex fallback for YYYY-MM-DD
    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", cleaned)
    if match:
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return None


def heuristic_parse(text: str, meta_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Rule-based regex extraction of invoice fields from raw text."""
    result: Dict[str, Any] = {
        "invoice_number": None,
        "invoice_date": None,
        "vendor_id": None,
        "vendor_name": None,
        "po_number": None,
        "currency": extract_currency(text),
        "subtotal": 0.0,
        "tax_amount": 0.0,
        "total_amount": 0.0,
        "line_items": [],
        "extracted_raw": {},
    }

    # Extract Invoice Number
    inv_match = re.search(
        r"(?:invoice\s*(?:no|number|#)?|rechnung(?:snummer)?|factura)\s*[:#\-]?\s*([A-Za-z0-9_\-\/]+)",
        text,
        re.IGNORECASE,
    )
    if inv_match:
        result["invoice_number"] = inv_match.group(1).strip()

    # Extract PO Number
    po_match = re.search(
        r"(?:po\s*(?:no|number|#)?|purchase\s*order|pedido|bestellung)\s*[:#\-]?\s*(PO[-_]?[0-9]+|[A-Za-z0-9_\-]+)",
        text,
        re.IGNORECASE,
    )
    if po_match:
        result["po_number"] = po_match.group(1).strip()
    elif meta_data and "subject" in meta_data:
        subj_po = re.search(r"PO-\d+", meta_data["subject"], re.IGNORECASE)
        if subj_po:
            result["po_number"] = subj_po.group(0).upper()

    # Extract Vendor ID or Name
    vend_id_match = re.search(r"\b(VEND-\d{3})\b", text, re.IGNORECASE)
    if vend_id_match:
        result["vendor_id"] = vend_id_match.group(1).upper()

    vendor_names = [
        ("Global Logistics Ltd", "VEND-001"),
        ("BlueOcean Transport Co.", "VEND-002"),
        ("Transporte Ibérico S.A.", "VEND-003"),
        ("Transporte Iberico", "VEND-003"),
        ("HafenLogistik GmbH", "VEND-004"),
        ("SwiftMove Couriers", "VEND-005"),
        ("OceanFreight Pvt Ltd", "VEND-006"),
    ]
    for vname, vid in vendor_names:
        if vname.lower() in text.lower():
            result["vendor_name"] = vname
            if not result["vendor_id"]:
                result["vendor_id"] = vid
            break

    # Extract Date
    date_match = re.search(
        r"(?:date|datum|fecha)\s*[:#\-]?\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}|[0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        result["invoice_date"] = parse_date_string(date_match.group(1))

    # Extract Totals
    total_match = re.search(
        r"(?:total\s*(?:amount|due)?|gesamtbetrag|total\s*factura)\s*[:#\-]?\s*[$€₹£]?\s*([0-9.,]+)",
        text,
        re.IGNORECASE,
    )
    if total_match:
        result["total_amount"] = clean_number(total_match.group(1))

    subtotal_match = re.search(
        r"(?:subtotal|zwischensumme|base\s*imponible)\s*[:#\-]?\s*[$€₹£]?\s*([0-9.,]+)",
        text,
        re.IGNORECASE,
    )
    if subtotal_match:
        result["subtotal"] = clean_number(subtotal_match.group(1))

    tax_match = re.search(
        r"(?:tax|vat|gst|mwst|iva)\s*(?:\([^)]*\))?\s*[:#\-]?\s*[$€₹£]?\s*([0-9.,]+)",
        text,
        re.IGNORECASE,
    )
    if tax_match:
        result["tax_amount"] = clean_number(tax_match.group(1))

    # Extract Line Items (e.g. SKU-001, description, qty, unit_price, total)
    line_item_pattern = re.compile(
        r"(SKU-\d+)\s+([A-Za-z0-9\s\-_.,()äöüÄÖÜßáéíóúÁÉÍÓÚñÑ]+?)\s+(\d+(?:\.\d+)?)\s+([$€₹£]?\s*[0-9.,]+)\s+([$€₹£]?\s*[0-9.,]+)"
    )
    line_idx = 1
    for match in line_item_pattern.finditer(text):
        item_code, desc, qty_str, unit_price_str, total_str = match.groups()
        qty = clean_number(qty_str)
        unit_price = clean_number(unit_price_str)
        line_total = clean_number(total_str)
        result["line_items"].append({
            "line_number": line_idx,
            "item_code": item_code.upper(),
            "description": desc.strip(),
            "quantity": qty,
            "unit_price": unit_price,
            "line_total": line_total,
        })
        line_idx += 1

    return result


def parse_with_llm(raw_text: str, source_language: str = "en") -> Dict[str, Any]:
    """Parse invoice fields using AWS Bedrock (Nova Lite or Command R+)."""
    persona = personas_config.get("personas", {}).get("invoice_extractor", {})
    system_prompt = persona.get("system_prompt", "Extract structured JSON from invoice text.")
    prompt_template = personas_config.get("prompts", {}).get("extraction", {}).get("template", "")

    user_prompt = prompt_template.format(raw_text=raw_text[:4000])

    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response_text = bedrock_manager.invoke_with_cache(
            model_id=settings.MODEL_REASONING,
            messages=messages,
            temperature=0.0,
        )

        # Extract JSON from markdown backticks if present
        clean_json = response_text.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()

        parsed = json.loads(clean_json)
        return parsed
    except Exception as exc:
        logger.warning("LLM extraction failed (%s), returning empty dict for fallback merge", exc)
        return {}


def extract_and_merge_fields(raw_text: str, meta_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Combines rule-based heuristic extraction with LLM parsing for maximum accuracy."""
    base = heuristic_parse(raw_text, meta_data)

    # Use LLM to enhance if base is missing key fields or has no line items
    if not base.get("invoice_number") or not base.get("line_items") or not base.get("total_amount"):
        llm_data = parse_with_llm(raw_text)
        for k, v in llm_data.items():
            if v and (not base.get(k) or base.get(k) == 0.0 or base.get(k) == []):
                base[k] = v

    # Fallback vendor ID from PO number if known
    if not base.get("vendor_id") and base.get("po_number"):
        po_num = str(base["po_number"]).upper()
        po_vendor_map = {
            "PO-1001": "VEND-001",
            "PO-1002": "VEND-002",
            "PO-1003": "VEND-003",
            "PO-1004": "VEND-004",
            "PO-1005": "VEND-005",
            "PO-1006": "VEND-006",
        }
        if po_num in po_vendor_map:
            base["vendor_id"] = po_vendor_map[po_num]

    return base
