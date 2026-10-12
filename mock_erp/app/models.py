"""Data models for Mock ERP service."""
from typing import List, Optional
from pydantic import BaseModel


class Vendor(BaseModel):
    vendor_id: str
    vendor_name: str
    country: str
    currency: str


class SKUMaster(BaseModel):
    item_code: str
    category: str
    uom: str
    gst_rate: float


class POLineItem(BaseModel):
    item_code: str
    description: str
    qty: float
    unit_price: float
    currency: str


class PurchaseOrder(BaseModel):
    po_number: str
    vendor_id: str
    line_items: List[POLineItem]
