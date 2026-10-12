"""HTTP client calling Agent and ERP services from Streamlit."""
import os
import logging
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger("streamlit_ui.api_client")

AGENT_URL = os.getenv("AGENT_SERVICE_URL", "http://agent:8000")
ERP_URL = os.getenv("ERP_SERVICE_URL", "http://mock-erp:8000")


def trigger_scan() -> Dict[str, Any]:
    """Trigger agent to scan incoming folder."""
    try:
        resp = requests.post(f"{AGENT_URL}/process", json={}, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Error triggering folder scan: %s", exc)
        return {"error": str(exc)}


def trigger_process_file(file_path: str) -> Dict[str, Any]:
    """Trigger processing for a specific file."""
    try:
        resp = requests.post(f"{AGENT_URL}/process", json={"file_path": file_path}, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Error processing file %s: %s", file_path, exc)
        return {"error": str(exc)}


def trigger_revalidate(invoice_id: str) -> Dict[str, Any]:
    """Trigger agent to revalidate an invoice after human feedback."""
    try:
        resp = requests.post(f"{AGENT_URL}/revalidate", json={"invoice_id": invoice_id}, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Error revalidating invoice %s: %s", invoice_id, exc)
        return {"error": str(exc)}


def query_rag_service(query: str, invoice_id: Optional[str] = None) -> Dict[str, Any]:
    """Query the LangGraph RAG pipeline."""
    payload = {"query": query}
    if invoice_id:
        payload["invoice_id"] = invoice_id
    try:
        resp = requests.post(f"{AGENT_URL}/query", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("RAG query failed: %s", exc)
        return {"error": str(exc)}


def trigger_rebuild_index() -> Dict[str, Any]:
    """Trigger Qdrant vector index rebuild from PostgreSQL."""
    try:
        resp = requests.post(f"{AGENT_URL}/rebuild-index", timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


def check_health() -> Dict[str, Any]:
    """Check health of agent and mock-erp services."""
    results = {}
    try:
        r = requests.get(f"{AGENT_URL}/health", timeout=3)
        results["agent"] = r.status_code == 200
        results["agent_details"] = r.json()
    except Exception:
        results["agent"] = False

    try:
        r = requests.get(f"{ERP_URL}/health", timeout=3)
        results["mock_erp"] = r.status_code == 200
        results["mock_erp_details"] = r.json()
    except Exception:
        results["mock_erp"] = False

    return results
