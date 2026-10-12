"""State definition for LangGraph Invoice Workflow."""
from typing import TypedDict, List, Dict, Any, Optional


class InvoiceState(TypedDict):
    invoice_id: str
    file_path: str
    file_name: str
    file_checksum: str
    already_audited: bool
    extraction_method: str
    raw_extracted_text: str
    translated_text: Optional[str]
    source_language: str
    translation_confidence: float

    # Extracted fields
    invoice_number: Optional[str]
    vendor_id: Optional[str]
    vendor_name: Optional[str]
    po_number: Optional[str]
    invoice_date: Optional[str]
    currency: Optional[str]
    subtotal: Optional[float]
    tax_amount: Optional[float]
    total_amount: Optional[float]
    line_items: List[Dict[str, Any]]
    extracted_raw: Dict[str, Any]

    # Audit outcomes
    validation_status: str       # passed | failed | partial
    recommendation: str          # approve | review | reject
    missing_fields: List[str]
    discrepancies: List[Dict[str, Any]]
    erp_data: Optional[Dict[str, Any]]

    # Metadata & Reports
    html_report_path: Optional[str]
    json_report_path: Optional[str]
    thread_id: str
    errors: List[str]
