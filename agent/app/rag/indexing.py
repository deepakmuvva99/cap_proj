"""Indexing agent for chunking, embedding, and storing vectors in Qdrant."""
import logging
from typing import Dict, Any, List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.llm.bedrock import bedrock_manager
from app.rag.vector_store import qdrant_store
from app.db import get_db_connection

logger = logging.getLogger("agent.rag.indexing")

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=50,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def index_invoice_and_report(invoice_data: Dict[str, Any]) -> int:
    """Index both the raw invoice text and its audit report findings into Qdrant."""
    invoice_id = str(invoice_data.get("invoice_id"))
    vendor = invoice_data.get("vendor_name") or invoice_data.get("vendor_id") or "Unknown"
    language = invoice_data.get("source_language", "en")
    inv_num = invoice_data.get("invoice_number", "Unknown")

    chunks: List[str] = []
    payloads: List[Dict[str, Any]] = []

    # 1. Chunk and index raw invoice text
    raw_text = invoice_data.get("raw_extracted_text", "")
    if raw_text:
        raw_chunks = text_splitter.split_text(raw_text)
        for chunk in raw_chunks:
            chunks.append(chunk)
            payloads.append({
                "invoice_id": invoice_id,
                "invoice_number": inv_num,
                "vendor": vendor,
                "language": language,
                "source_type": "raw_invoice",
                "chunk_text": chunk,
            })

    # 2. Chunk and index translated text (if multilingual)
    trans_text = invoice_data.get("translated_text", "")
    if trans_text and language != "en":
        trans_chunks = text_splitter.split_text(trans_text)
        for chunk in trans_chunks:
            chunks.append(chunk)
            payloads.append({
                "invoice_id": invoice_id,
                "invoice_number": inv_num,
                "vendor": vendor,
                "language": language,
                "source_type": "translated_invoice",
                "chunk_text": chunk,
            })

    # 3. Create and index audit report synthesis chunk
    discrepancies = invoice_data.get("discrepancies", [])
    rec = invoice_data.get("recommendation", "review").upper()
    disc_summary = "; ".join([
        f"{d.get('field_name')} (Inv: {d.get('invoice_value')}, ERP: {d.get('erp_value')}, Dev: {d.get('deviation_pct')}%)"
        for d in discrepancies
    ]) if discrepancies else "Zero discrepancies detected. Matches ERP purchase order."

    report_text = (
        f"Audit Report for Invoice {inv_num} (ID: {invoice_id}).\n"
        f"Vendor: {vendor}, PO Number: {invoice_data.get('po_number', 'N/A')}.\n"
        f"Total Amount: {invoice_data.get('total_amount', 0.0)} {invoice_data.get('currency', 'USD')}.\n"
        f"Audit Recommendation: {rec}.\n"
        f"Translation Confidence: {float(invoice_data.get('translation_confidence', 1.0)):.2f}.\n"
        f"Discrepancy Details: {disc_summary}"
    )

    report_chunks = text_splitter.split_text(report_text)
    for chunk in report_chunks:
        chunks.append(chunk)
        payloads.append({
            "invoice_id": invoice_id,
            "invoice_number": inv_num,
            "vendor": vendor,
            "language": language,
            "source_type": "audit_report",
            "chunk_text": chunk,
        })

    if not chunks:
        logger.warning("No text available to index for invoice %s", invoice_id)
        return 0

    # Generate Embeddings
    embeddings_model = bedrock_manager.get_embeddings()
    vectors = embeddings_model.embed_documents(chunks)

    # Ensure collection exists
    vector_dim = len(vectors[0]) if vectors else 1024
    qdrant_store.ensure_collection(vector_size=vector_dim)

    # Upsert to Qdrant
    qdrant_store.upsert_points(vectors, payloads)
    logger.info("Indexed %d chunks for invoice %s in Qdrant", len(chunks), invoice_id)
    return len(chunks)


def rebuild_index_from_postgres() -> int:
    """Rebuilds entire Qdrant index from PostgreSQL audit schema without re-reading files or repeating OCR."""
    logger.info("Initiating Qdrant index rebuild from PostgreSQL audit records...")
    total_indexed = 0
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT invoice_id, raw_extracted_text, translated_text, source_language,
                           translation_confidence, invoice_number, vendor_name, po_number,
                           currency, total_amount, recommendation
                    FROM audit.invoice_audit;
                """)
                rows = cur.fetchall()
                for r in rows:
                    inv_id = str(r[0])
                    # Fetch discrepancies
                    cur.execute(
                        "SELECT field_name, invoice_value, erp_value, deviation_pct, severity FROM audit.discrepancies WHERE invoice_id = %s;",
                        (inv_id,),
                    )
                    discs = [
                        {"field_name": d[0], "invoice_value": d[1], "erp_value": d[2], "deviation_pct": float(d[3] or 0), "severity": d[4]}
                        for d in cur.fetchall()
                    ]

                    inv_dict = {
                        "invoice_id": inv_id,
                        "raw_extracted_text": r[1],
                        "translated_text": r[2],
                        "source_language": r[3],
                        "translation_confidence": float(r[4] or 1.0),
                        "invoice_number": r[5],
                        "vendor_name": r[6],
                        "po_number": r[7],
                        "currency": r[8],
                        "total_amount": float(r[9] or 0.0),
                        "recommendation": r[10],
                        "discrepancies": discs,
                    }
                    total_indexed += index_invoice_and_report(inv_dict)
    except Exception as exc:
        logger.error("Failed to rebuild index from PostgreSQL: %s", exc)

    logger.info("Index rebuild complete. Total indexed chunks: %d", total_indexed)
    return total_indexed
