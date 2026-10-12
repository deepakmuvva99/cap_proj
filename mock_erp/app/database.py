"""Database layer for Mock ERP service."""
import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("mock_erp.database")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "invoicedb")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")


def get_connection():
    """Establish and return a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        connect_timeout=5,
    )


def _load_fallback_json(filename: str):
    """Load mock data from local JSON file if DB connection is unavailable."""
    possible_paths = [
        Path(f"/data/ERP_mockdata/{filename}"),
        Path(f"./data/ERP_mockdata/{filename}"),
        Path(f"../data/ERP_mockdata/{filename}"),
        Path(f"../../data/ERP_mockdata/{filename}"),
    ]
    for p in possible_paths:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def fetch_purchase_order(po_number: str) -> Optional[Dict[str, Any]]:
    """Fetch PO and its line items from erp schema."""
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT po_number, vendor_id
                    FROM erp.purchase_orders
                    WHERE po_number = %s;
                    """,
                    (po_number,),
                )
                po_row = cur.fetchone()
                if not po_row:
                    return None

                cur.execute(
                    """
                    SELECT item_code, description, qty::float, unit_price::float, currency
                    FROM erp.po_line_items
                    WHERE po_number = %s
                    ORDER BY id ASC;
                    """,
                    (po_number,),
                )
                items = cur.fetchall()
                return {
                    "po_number": po_row["po_number"],
                    "vendor_id": po_row["vendor_id"],
                    "line_items": [dict(i) for i in items],
                }
    except Exception as exc:
        logger.warning("DB query for PO failed (%s), attempting fallback JSON", exc)
        data = _load_fallback_json("PO Records.json")
        if data:
            for item in data:
                if item.get("po_number") == po_number:
                    return item
        return None


def fetch_vendor(vendor_id: str) -> Optional[Dict[str, Any]]:
    """Fetch vendor record from erp.vendors table."""
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT vendor_id, vendor_name, country, currency
                    FROM erp.vendors
                    WHERE vendor_id = %s;
                    """,
                    (vendor_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as exc:
        logger.warning("DB query for vendor failed (%s), attempting fallback JSON", exc)
        data = _load_fallback_json("vendors.json")
        if data:
            for v in data:
                if v.get("vendor_id") == vendor_id:
                    return v
        return None


def fetch_sku(sku_code: str) -> Optional[Dict[str, Any]]:
    """Fetch SKU record from erp.sku_master table."""
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT item_code, category, uom, gst_rate::float
                    FROM erp.sku_master
                    WHERE item_code = %s;
                    """,
                    (sku_code,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as exc:
        logger.warning("DB query for SKU failed (%s), attempting fallback JSON", exc)
        data = _load_fallback_json("sku_master.json")
        if data:
            for s in data:
                if s.get("item_code") == sku_code:
                    return s
        return None
