"""Monitor and routing node for invoice workflow."""
import uuid
import logging
from pathlib import Path
from app.workflow.state import InvoiceState
from app.extractors.router import compute_file_checksum, load_accompanying_metadata
from app.db import is_checksum_processed

logger = logging.getLogger("agent.workflow.monitor")


def monitor_node(state: InvoiceState) -> InvoiceState:
    """Detects file, computes checksum, checks audit history, and initializes state."""
    file_path = state.get("file_path")
    if not file_path:
        state["errors"].append("Missing file_path in state")
        return state

    p = Path(file_path)
    state["file_name"] = p.name

    # Compute checksum
    checksum = compute_file_checksum(file_path)
    state["file_checksum"] = checksum

    # Check if already audited in database
    if is_checksum_processed(checksum):
        logger.info("Invoice '%s' (hash %s) has already been audited. Flagging as already_audited.", p.name, checksum[:8])
        state["already_audited"] = True
        return state

    state["already_audited"] = False
    if not state.get("invoice_id"):
        state["invoice_id"] = str(uuid.uuid4())

    meta = load_accompanying_metadata(file_path)
    if meta:
        state["extracted_raw"]["meta_json"] = meta
        if "language" in meta and not state.get("source_language"):
            state["source_language"] = meta["language"]

    logger.info("Monitor node processed %s (ID: %s)", p.name, state["invoice_id"])
    return state
