"""Agent Service FastAPI Entrypoint."""
import os
import glob
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from pydantic import BaseModel
from app.config import settings
from app.workflow.graph import process_invoice_file, revalidate_invoice
from app.rag.graph import query_rag
from app.rag.indexing import rebuild_index_from_postgres
from app.db import get_db_connection
from app.cache import cache_client
from app.rag.vector_store import qdrant_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("agent.api")

app = FastAPI(
    title="AI Invoice Auditor Agent Service",
    description="Multilingual Agentic AI Invoice Validation and RAG Service.",
    version="1.0.0",
)


class ProcessRequest(BaseModel):
    file_path: Optional[str] = None


class RevalidateRequest(BaseModel):
    invoice_id: str


class QueryRequest(BaseModel):
    query: str
    invoice_id: Optional[str] = None
    vendor: Optional[str] = None


@app.get("/health", status_code=status.HTTP_200_OK)
def health():
    """Health check endpoint for Docker Compose."""
    # Check Postgres
    postgres_ok = False
    try:
        conn = get_db_connection()
        conn.close()
        postgres_ok = True
    except Exception as exc:
        logger.debug("PostgreSQL health ping failed: %s", exc)

    # Check Redis
    redis_ok = cache_client.get_client() is not None

    # Check Qdrant
    qdrant_ok = False
    try:
        qdrant_store.get_client().get_collections()
        qdrant_ok = True
    except Exception as exc:
        logger.debug("Qdrant health ping failed: %s", exc)

    return {
        "status": "ok",
        "service": "agent",
        "dependencies": {
            "postgres": postgres_ok,
            "redis": redis_ok,
            "qdrant": qdrant_ok,
        },
    }


@app.post("/process")
def process_invoice(req: ProcessRequest, background_tasks: BackgroundTasks):
    """Processes a specific invoice file or scans all files in incoming directory."""
    incoming_dir = Path(settings.INCOMING_DIR)

    if req.file_path:
        target = Path(req.file_path)
        if not target.exists():
            # Try prepending incoming directory
            target = incoming_dir / req.file_path
            if not target.exists():
                raise HTTPException(status_code=404, detail=f"File not found: {req.file_path}")

        result = process_invoice_file(str(target))
        return {
            "status": "success",
            "invoice_id": result.get("invoice_id"),
            "file_name": result.get("file_name"),
            "already_audited": result.get("already_audited", False),
            "recommendation": result.get("recommendation"),
            "validation_status": result.get("validation_status"),
            "discrepancies_count": len(result.get("discrepancies", [])),
        }

    # Batch scan incoming directory
    supported_extensions = ["*.pdf", "*.docx", "*.png", "*.jpg", "*.jpeg"]
    all_files = []
    for ext in supported_extensions:
        all_files.extend(list(incoming_dir.glob(ext)))

    if not all_files:
        return {"status": "success", "message": "No invoice files found in incoming directory.", "processed": 0}

    results = []
    for f in all_files:
        try:
            res = process_invoice_file(str(f))
            results.append({
                "file": f.name,
                "invoice_id": res.get("invoice_id"),
                "already_audited": res.get("already_audited"),
                "recommendation": res.get("recommendation"),
            })
        except Exception as exc:
            logger.error("Error processing %s: %s", f.name, exc)
            results.append({"file": f.name, "error": str(exc)})

    return {
        "status": "success",
        "processed_count": len(results),
        "results": results,
    }


@app.post("/revalidate")
def revalidate(req: RevalidateRequest):
    """Re-validates an invoice after human feedback has been entered."""
    res = revalidate_invoice(req.invoice_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Invoice not found: {req.invoice_id}")
    return {
        "status": "revalidated",
        "invoice_id": req.invoice_id,
        "recommendation": res.get("recommendation"),
        "validation_status": res.get("validation_status"),
        "discrepancies": res.get("discrepancies", []),
    }


@app.post("/query")
def rag_query(req: QueryRequest):
    """Natural-language question answering via RAG pipeline with RAG Triad reflection."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    result = query_rag(req.query, req.invoice_id, req.vendor)
    return result


@app.post("/rebuild-index")
def rebuild_index():
    """Rebuilds the entire Qdrant vector index directly from PostgreSQL text records."""
    count = rebuild_index_from_postgres()
    return {"status": "rebuilt", "chunks_indexed": count}
