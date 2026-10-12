"""LangGraph Orchestration Graph for AI Invoice Auditor."""
import uuid
import logging
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.workflow.state import InvoiceState
from app.workflow.nodes_monitor import monitor_node
from app.workflow.nodes_extractor import extractor_node
from app.workflow.nodes_translation import translation_node
from app.workflow.nodes_validation import invoice_data_validation_node, business_validation_node
from app.workflow.nodes_reporting import reporting_node
from app.rag.indexing import index_invoice_and_report
from app.db import fetch_invoice_details, mark_feedback_revalidated

logger = logging.getLogger("agent.workflow.graph")


def should_skip_if_audited(state: InvoiceState) -> str:
    """If invoice was already audited, skip directly to end."""
    if state.get("already_audited"):
        return "end"
    return "continue"


def build_invoice_graph():
    """Builds and compiles the end-to-end invoice auditing LangGraph workflow."""
    workflow = StateGraph(InvoiceState)

    # 1. Add Workflow Nodes
    workflow.add_node("monitor", monitor_node)
    workflow.add_node("extractor", extractor_node)
    workflow.add_node("translation", translation_node)
    workflow.add_node("data_validation", invoice_data_validation_node)
    workflow.add_node("business_validation", business_validation_node)
    workflow.add_node("reporting", reporting_node)

    # 2. Add Flow Edges
    workflow.set_entry_point("monitor")

    workflow.add_conditional_edges(
        "monitor",
        should_skip_if_audited,
        {
            "end": END,
            "continue": "extractor",
        },
    )

    workflow.add_edge("extractor", "translation")
    workflow.add_edge("translation", "data_validation")
    workflow.add_edge("data_validation", "business_validation")
    workflow.add_edge("business_validation", "reporting")
    workflow.add_edge("reporting", END)

    # Compile with memory checkpointer
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


invoice_graph = build_invoice_graph()


def process_invoice_file(file_path: str, thread_id: Optional[str] = None) -> InvoiceState:
    """Executes the complete LangGraph audit workflow for a single invoice file."""
    if not thread_id:
        thread_id = str(uuid.uuid4())

    initial_state: InvoiceState = {
        "invoice_id": str(uuid.uuid4()),
        "file_path": file_path,
        "file_name": "",
        "file_checksum": "",
        "already_audited": False,
        "extraction_method": "",
        "raw_extracted_text": "",
        "translated_text": None,
        "source_language": "en",
        "translation_confidence": 1.0,
        "invoice_number": None,
        "vendor_id": None,
        "vendor_name": None,
        "po_number": None,
        "invoice_date": None,
        "currency": "USD",
        "subtotal": 0.0,
        "tax_amount": 0.0,
        "total_amount": 0.0,
        "line_items": [],
        "extracted_raw": {},
        "validation_status": "pending",
        "recommendation": "review",
        "missing_fields": [],
        "discrepancies": [],
        "erp_data": None,
        "html_report_path": None,
        "json_report_path": None,
        "thread_id": thread_id,
        "errors": [],
    }

    config = {"configurable": {"thread_id": thread_id}}
    final_state = invoice_graph.invoke(initial_state, config=config)

    # Trigger RAG indexing if freshly processed
    if not final_state.get("already_audited") and final_state.get("raw_extracted_text"):
        try:
            index_invoice_and_report(final_state)
        except Exception as exc:
            logger.error("Failed to index invoice into Qdrant: %s", exc)

    return final_state


def revalidate_invoice(invoice_id: str) -> Optional[InvoiceState]:
    """Re-runs validation for an invoice after human corrections have been applied."""
    inv = fetch_invoice_details(invoice_id)
    if not inv:
        return None

    logger.info("Re-validating invoice %s with human feedback overrides...", invoice_id)

    # Apply feedback overrides to values
    feedbacks = inv.get("feedback", [])
    overrides = {f["field_name"]: f["corrected_value"] for f in feedbacks}

    state: InvoiceState = {
        "invoice_id": invoice_id,
        "file_path": inv.get("file_path", ""),
        "file_name": "",
        "file_checksum": inv.get("file_checksum", ""),
        "already_audited": False,
        "extraction_method": inv.get("extraction_method", ""),
        "raw_extracted_text": inv.get("raw_extracted_text", ""),
        "translated_text": inv.get("translated_text"),
        "source_language": inv.get("source_language", "en"),
        "translation_confidence": float(inv.get("translation_confidence", 1.0)),
        "invoice_number": overrides.get("invoice_number", inv.get("invoice_number")),
        "vendor_id": overrides.get("vendor_id", inv.get("vendor_id")),
        "vendor_name": overrides.get("vendor_name", inv.get("vendor_name")),
        "po_number": overrides.get("po_number", inv.get("po_number")),
        "invoice_date": overrides.get("invoice_date", str(inv.get("invoice_date"))),
        "currency": overrides.get("currency", inv.get("currency")),
        "subtotal": float(overrides.get("subtotal", inv.get("subtotal") or 0.0)),
        "tax_amount": float(overrides.get("tax_amount", inv.get("tax_amount") or 0.0)),
        "total_amount": float(overrides.get("total_amount", inv.get("total_amount") or 0.0)),
        "line_items": inv.get("line_items", []),
        "extracted_raw": inv.get("extracted_raw") or {},
        "validation_status": "pending",
        "recommendation": "review",
        "missing_fields": [],
        "discrepancies": [],
        "erp_data": None,
        "html_report_path": None,
        "json_report_path": None,
        "thread_id": str(uuid.uuid4()),
        "errors": [],
    }

    # Run data validation, business validation, and reporting
    state = invoice_data_validation_node(state)
    state = business_validation_node(state)
    state = reporting_node(state)

    mark_feedback_revalidated(invoice_id)

    # Update RAG index
    index_invoice_and_report(state)

    return state
