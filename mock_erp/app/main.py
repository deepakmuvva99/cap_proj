"""Mock ERP Service FastAPI Application."""
import logging
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, status
from app.models import PurchaseOrder, Vendor, SKUMaster
from app.database import fetch_purchase_order, fetch_vendor, fetch_sku, get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("mock_erp")

app = FastAPI(
    title="Mock ERP Service",
    description="Isolated ERP Master Data service providing PO, Vendor, and SKU lookup via HTTP.",
    version="1.0.0",
)


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Health check endpoint for Docker Compose and dependent services."""
    db_ok = False
    try:
        conn = get_connection()
        conn.close()
        db_ok = True
    except Exception as exc:
        logger.warning("Database health ping failed: %s", exc)

    return {
        "status": "ok",
        "service": "mock-erp",
        "database_connected": db_ok,
    }


@app.get("/po/{po_number}", response_model=PurchaseOrder)
def get_purchase_order(po_number: str):
    """Retrieve Purchase Order header and line items by PO number."""
    po = fetch_purchase_order(po_number.strip())
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order '{po_number}' not found in ERP system.",
        )
    return po


@app.get("/vendor/{vendor_id}", response_model=Vendor)
def get_vendor(vendor_id: str):
    """Retrieve Vendor master record by Vendor ID."""
    vendor = fetch_vendor(vendor_id.strip())
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor '{vendor_id}' not found in ERP system.",
        )
    return vendor


@app.get("/sku/{sku_code}", response_model=SKUMaster)
def get_sku(sku_code: str):
    """Retrieve SKU master record by SKU code."""
    sku = fetch_sku(sku_code.strip())
    if not sku:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU '{sku_code}' not found in ERP system.",
        )
    return sku
