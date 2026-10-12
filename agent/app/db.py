"""PostgreSQL database operations for Audit schema."""
import json
import logging
from typing import Dict, Any, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from app.config import settings

logger = logging.getLogger("agent.db")


def get_db_connection():
    """Create and return a connection to PostgreSQL."""
    return psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        connect_timeout=5,
    )


def is_checksum_processed(checksum: str) -> bool:
    """Check if an invoice with the given file checksum has already been audited."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM audit.invoice_audit WHERE file_checksum = %s LIMIT 1;",
                    (checksum,),
                )
                return cur.fetchone() is not None
    except Exception as exc:
        logger.error("Error querying checksum: %s", exc)
        return False


def save_invoice_audit(data: Dict[str, Any]) -> str:
    """Save or update invoice record in audit.invoice_audit."""
    query = """
    INSERT INTO audit.invoice_audit (
        invoice_id, file_path, file_checksum, extraction_method,
        raw_extracted_text, translated_text, source_language,
        translation_confidence, invoice_number, vendor_name, po_number,
        invoice_date, currency, total_amount, subtotal, tax_amount,
        validation_status, recommendation, extracted_raw, thread_id
    ) VALUES (
        %(invoice_id)s, %(file_path)s, %(file_checksum)s, %(extraction_method)s,
        %(raw_extracted_text)s, %(translated_text)s, %(source_language)s,
        %(translation_confidence)s, %(invoice_number)s, %(vendor_name)s, %(po_number)s,
        %(invoice_date)s, %(currency)s, %(total_amount)s, %(subtotal)s, %(tax_amount)s,
        %(validation_status)s, %(recommendation)s, %(extracted_raw)s, %(thread_id)s
    )
    ON CONFLICT (invoice_id) DO UPDATE SET
        translated_text = EXCLUDED.translated_text,
        invoice_number = EXCLUDED.invoice_number,
        vendor_name = EXCLUDED.vendor_name,
        po_number = EXCLUDED.po_number,
        invoice_date = EXCLUDED.invoice_date,
        currency = EXCLUDED.currency,
        total_amount = EXCLUDED.total_amount,
        subtotal = EXCLUDED.subtotal,
        tax_amount = EXCLUDED.tax_amount,
        validation_status = EXCLUDED.validation_status,
        recommendation = EXCLUDED.recommendation,
        extracted_raw = EXCLUDED.extracted_raw,
        processed_at = now()
    RETURNING invoice_id;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            payload = {
                "invoice_id": str(data["invoice_id"]),
                "file_path": data.get("file_path"),
                "file_checksum": data.get("file_checksum"),
                "extraction_method": data.get("extraction_method"),
                "raw_extracted_text": data.get("raw_extracted_text"),
                "translated_text": data.get("translated_text"),
                "source_language": data.get("source_language", "en"),
                "translation_confidence": data.get("translation_confidence", 1.0),
                "invoice_number": data.get("invoice_number"),
                "vendor_name": data.get("vendor_name"),
                "po_number": data.get("po_number"),
                "invoice_date": data.get("invoice_date"),
                "currency": data.get("currency"),
                "total_amount": data.get("total_amount"),
                "subtotal": data.get("subtotal"),
                "tax_amount": data.get("tax_amount"),
                "validation_status": data.get("validation_status", "pending"),
                "recommendation": data.get("recommendation", "review"),
                "extracted_raw": Json(data.get("extracted_raw", {})),
                "thread_id": data.get("thread_id"),
            }
            cur.execute(query, payload)
            res = cur.fetchone()
            return str(res[0])


def save_invoice_line_items(invoice_id: str, line_items: List[Dict[str, Any]]) -> None:
    """Save invoice line items into audit.invoice_line_items table."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit.invoice_line_items WHERE invoice_id = %s;", (invoice_id,))
            insert_sql = """
            INSERT INTO audit.invoice_line_items (
                invoice_id, line_number, item_code, description, quantity, unit_price, line_total
            ) VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
            for idx, item in enumerate(line_items, start=1):
                cur.execute(
                    insert_sql,
                    (
                        invoice_id,
                        item.get("line_number", idx),
                        item.get("item_code"),
                        item.get("description", ""),
                        item.get("quantity") or item.get("qty", 0.0),
                        item.get("unit_price", 0.0),
                        item.get("line_total") or item.get("total", 0.0),
                    ),
                )


def save_discrepancies(invoice_id: str, discrepancies: List[Dict[str, Any]]) -> None:
    """Save detected discrepancies into audit.discrepancies."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit.discrepancies WHERE invoice_id = %s;", (invoice_id,))
            insert_sql = """
            INSERT INTO audit.discrepancies (
                invoice_id, field_name, invoice_value, erp_value, deviation_pct, severity
            ) VALUES (%s, %s, %s, %s, %s, %s);
            """
            for disc in discrepancies:
                cur.execute(
                    insert_sql,
                    (
                        invoice_id,
                        disc.get("field_name"),
                        str(disc.get("invoice_value", "")),
                        str(disc.get("erp_value", "")),
                        disc.get("deviation_pct", 0.0),
                        disc.get("severity", "medium"),
                    ),
                )


def insert_human_feedback(
    invoice_id: str,
    field_name: str,
    original_value: str,
    corrected_value: str,
    corrected_by: str = "auditor",
) -> int:
    """Insert human feedback without overwriting original extraction."""
    query = """
    INSERT INTO audit.human_feedback (
        invoice_id, field_name, original_value, corrected_value, corrected_by, corrected_at, revalidated
    ) VALUES (%s, %s, %s, %s, %s, now(), FALSE)
    RETURNING id;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (invoice_id, field_name, str(original_value), str(corrected_value), corrected_by),
            )
            return cur.fetchone()[0]


def mark_feedback_revalidated(invoice_id: str) -> None:
    """Mark all human feedback for this invoice as revalidated."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE audit.human_feedback SET revalidated = TRUE WHERE invoice_id = %s;",
                (invoice_id,),
            )


def fetch_all_invoices() -> List[Dict[str, Any]]:
    """Fetch all invoice audit records."""
    query = """
    SELECT
        invoice_id, file_path, file_checksum, extraction_method,
        source_language, translation_confidence, invoice_number,
        vendor_name, po_number, invoice_date, currency,
        total_amount, subtotal, tax_amount, validation_status,
        recommendation, processed_at
    FROM audit.invoice_audit
    ORDER BY processed_at DESC;
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            return [dict(row) for row in cur.fetchall()]


def fetch_invoice_details(invoice_id: str) -> Optional[Dict[str, Any]]:
    """Fetch complete invoice audit record, including line items and discrepancies."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM audit.invoice_audit WHERE invoice_id = %s;",
                (invoice_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            result = dict(row)

            cur.execute(
                "SELECT * FROM audit.invoice_line_items WHERE invoice_id = %s ORDER BY line_number ASC;",
                (invoice_id,),
            )
            result["line_items"] = [dict(item) for item in cur.fetchall()]

            cur.execute(
                "SELECT * FROM audit.discrepancies WHERE invoice_id = %s ORDER BY id ASC;",
                (invoice_id,),
            )
            result["discrepancies"] = [dict(d) for d in cur.fetchall()]

            cur.execute(
                "SELECT * FROM audit.human_feedback WHERE invoice_id = %s ORDER BY corrected_at DESC;",
                (invoice_id,),
            )
            result["feedback"] = [dict(f) for f in cur.fetchall()]

            return result
