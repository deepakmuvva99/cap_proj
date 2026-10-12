"""Extractor node for invoice workflow."""
import logging
from pathlib import Path
from app.workflow.state import InvoiceState
from app.extractors.router import route_and_extract

logger = logging.getLogger("agent.workflow.extractor")


def extractor_node(state: InvoiceState) -> InvoiceState:
    """Extracts raw text and parsed fields using the appropriate format parser."""
    if state.get("already_audited"):
        return state

    file_path = state["file_path"]
    try:
        extraction = route_and_extract(file_path)
        state["raw_extracted_text"] = extraction["raw_text"]
        state["extraction_method"] = extraction["extraction_method"]

        fields = extraction.get("fields", {})
        state["invoice_number"] = fields.get("invoice_number") or state.get("invoice_number")
        state["vendor_id"] = fields.get("vendor_id") or state.get("vendor_id")
        state["vendor_name"] = fields.get("vendor_name") or state.get("vendor_name")
        state["po_number"] = fields.get("po_number") or state.get("po_number")
        state["invoice_date"] = fields.get("invoice_date") or state.get("invoice_date")
        state["currency"] = fields.get("currency") or state.get("currency") or "USD"
        state["subtotal"] = fields.get("subtotal", 0.0)
        state["tax_amount"] = fields.get("tax_amount", 0.0)
        state["total_amount"] = fields.get("total_amount", 0.0)
        state["line_items"] = fields.get("line_items", [])

        # Store any remaining raw extraction structures
        state["extracted_raw"].update(fields.get("extracted_raw", {}))

        logger.info(
            "Extraction complete for %s. Found %d line items, total: %s %s",
            Path(file_path).name,
            len(state["line_items"]),
            state["currency"],
            state["total_amount"],
        )
    except Exception as exc:
        logger.error("Extraction error for %s: %s", file_path, exc)
        state["errors"].append(f"Extraction error: {str(exc)}")

    return state
