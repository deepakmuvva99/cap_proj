"""Database read-only adapter for Streamlit UI querying the Audit schema."""
import os
import logging
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("streamlit_ui.db")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "invoicedb")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")


def get_connection():
    """Establish database connection."""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        connect_timeout=5,
    )


def get_all_invoices() -> List[Dict[str, Any]]:
    """Retrieve all invoices from audit.invoice_audit."""
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
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)
                return [dict(row) for row in cur.fetchall()]
    except Exception as exc:
        logger.error("Failed to fetch invoices: %s", exc)
        return []


def get_invoice_full(invoice_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve complete audit record including line items and discrepancies."""
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM audit.invoice_audit WHERE invoice_id = %s;", (invoice_id,))
                row = cur.fetchone()
                if not row:
                    return None
                data = dict(row)

                cur.execute("SELECT * FROM audit.invoice_line_items WHERE invoice_id = %s ORDER BY line_number ASC;", (invoice_id,))
                data["line_items"] = [dict(r) for r in cur.fetchall()]

                cur.execute("SELECT * FROM audit.discrepancies WHERE invoice_id = %s ORDER BY id ASC;", (invoice_id,))
                data["discrepancies"] = [dict(r) for r in cur.fetchall()]

                cur.execute("SELECT * FROM audit.human_feedback WHERE invoice_id = %s ORDER BY corrected_at DESC;", (invoice_id,))
                data["feedback"] = [dict(r) for r in cur.fetchall()]

                return data
    except Exception as exc:
        logger.error("Failed to fetch invoice details: %s", exc)
        return None


def insert_human_feedback(invoice_id: str, field_name: str, original_val: str, corrected_val: str, auditor_name: str = "auditor") -> bool:
    """Inserts a human correction into audit.human_feedback (never overwriting original extraction)."""
    query = """
    INSERT INTO audit.human_feedback (
        invoice_id, field_name, original_value, corrected_value, corrected_by, corrected_at, revalidated
    ) VALUES (%s, %s, %s, %s, %s, now(), FALSE);
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (invoice_id, field_name, str(original_val), str(corrected_val), auditor_name))
            conn.commit()
            return True
    except Exception as exc:
        logger.error("Failed to insert human feedback: %s", exc)
        return False
