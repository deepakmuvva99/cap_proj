-- =============================================================
-- AI Invoice Auditor – Database Initialization Script
-- =============================================================
-- This script initializes the three distinct schemas:
-- 1. erp        - Owned by mock-erp (read-only for others)
-- 2. audit      - Owned by agent (written by agent, read by UI)
-- 3. langgraph  - Owned by agent (state checkpoints)
-- =============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================
-- SCHEMA 1: erp (Master Data)
-- =============================================================
CREATE SCHEMA IF NOT EXISTS erp;

CREATE TABLE IF NOT EXISTS erp.vendors (
    vendor_id VARCHAR(32) PRIMARY KEY,
    vendor_name VARCHAR(255) NOT NULL,
    country VARCHAR(64) NOT NULL,
    currency CHAR(3) NOT NULL
);

CREATE TABLE IF NOT EXISTS erp.sku_master (
    item_code VARCHAR(64) PRIMARY KEY,
    category VARCHAR(64) NOT NULL,
    uom VARCHAR(32) NOT NULL,
    gst_rate NUMERIC(5,2) NOT NULL DEFAULT 10.00
);

CREATE TABLE IF NOT EXISTS erp.purchase_orders (
    po_number VARCHAR(64) PRIMARY KEY,
    vendor_id VARCHAR(32) NOT NULL REFERENCES erp.vendors(vendor_id),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.po_line_items (
    id BIGSERIAL PRIMARY KEY,
    po_number VARCHAR(64) NOT NULL REFERENCES erp.purchase_orders(po_number) ON DELETE CASCADE,
    item_code VARCHAR(64) NOT NULL REFERENCES erp.sku_master(item_code),
    description TEXT NOT NULL,
    qty NUMERIC(12,3) NOT NULL,
    unit_price NUMERIC(14,4) NOT NULL,
    currency CHAR(3) NOT NULL
);

-- =============================================================
-- SCHEMA 2: audit (System of Record for Invoices & Audits)
-- =============================================================
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.invoice_audit (
    invoice_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_path VARCHAR(512),
    file_checksum VARCHAR(64) UNIQUE,
    extraction_method VARCHAR(32), -- pdfplumber | docx | tesseract
    raw_extracted_text TEXT,
    translated_text TEXT,
    source_language VARCHAR(8),
    translation_confidence NUMERIC(4,3),
    invoice_number VARCHAR(64),
    vendor_name VARCHAR(255),
    po_number VARCHAR(64),
    invoice_date DATE,
    currency CHAR(3),
    total_amount NUMERIC(14,2),
    subtotal NUMERIC(14,2),
    tax_amount NUMERIC(14,2),
    validation_status VARCHAR(32) DEFAULT 'pending', -- passed | failed | partial
    recommendation VARCHAR(32) DEFAULT 'review',     -- approve | review | reject
    extracted_raw JSONB,
    thread_id VARCHAR(128),
    processed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit.invoice_line_items (
    id BIGSERIAL PRIMARY KEY,
    invoice_id UUID NOT NULL REFERENCES audit.invoice_audit(invoice_id) ON DELETE CASCADE,
    line_number INTEGER,
    item_code VARCHAR(64),
    description TEXT,
    quantity NUMERIC(12,3),
    unit_price NUMERIC(14,4),
    line_total NUMERIC(14,2)
);

CREATE TABLE IF NOT EXISTS audit.discrepancies (
    id BIGSERIAL PRIMARY KEY,
    invoice_id UUID NOT NULL REFERENCES audit.invoice_audit(invoice_id) ON DELETE CASCADE,
    field_name VARCHAR(64) NOT NULL,
    invoice_value TEXT,
    erp_value TEXT,
    deviation_pct NUMERIC(8,4),
    severity VARCHAR(16) DEFAULT 'medium', -- low | medium | high | critical
    detected_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit.human_feedback (
    id BIGSERIAL PRIMARY KEY,
    invoice_id UUID NOT NULL REFERENCES audit.invoice_audit(invoice_id) ON DELETE CASCADE,
    field_name VARCHAR(64) NOT NULL,
    original_value TEXT,
    corrected_value TEXT,
    corrected_by VARCHAR(128) NOT NULL DEFAULT 'auditor',
    corrected_at TIMESTAMPTZ DEFAULT now(),
    revalidated BOOLEAN DEFAULT FALSE
);

-- =============================================================
-- SCHEMA 3: langgraph (Workflow Checkpoints)
-- =============================================================
CREATE SCHEMA IF NOT EXISTS langgraph;

CREATE TABLE IF NOT EXISTS langgraph.checkpoints (
    thread_id VARCHAR(128) NOT NULL,
    checkpoint_ns VARCHAR(128) NOT NULL DEFAULT '',
    checkpoint_id VARCHAR(128) NOT NULL,
    parent_checkpoint_id VARCHAR(128),
    type VARCHAR(64),
    checkpoint BYTEA,
    metadata BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS langgraph.checkpoint_blobs (
    thread_id VARCHAR(128) NOT NULL,
    checkpoint_ns VARCHAR(128) NOT NULL DEFAULT '',
    channel VARCHAR(128) NOT NULL,
    version VARCHAR(128) NOT NULL,
    type VARCHAR(64),
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS langgraph.checkpoint_writes (
    thread_id VARCHAR(128) NOT NULL,
    checkpoint_ns VARCHAR(128) NOT NULL DEFAULT '',
    checkpoint_id VARCHAR(128) NOT NULL,
    task_id VARCHAR(128) NOT NULL,
    idx INTEGER NOT NULL,
    channel VARCHAR(128) NOT NULL,
    type VARCHAR(64),
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- =============================================================
-- Seed Master Data into erp schema
-- =============================================================

-- 1. Vendors
INSERT INTO erp.vendors (vendor_id, vendor_name, country, currency) VALUES
('VEND-001', 'Global Logistics Ltd', 'UK', 'USD'),
('VEND-002', 'BlueOcean Transport Co.', 'USA', 'USD'),
('VEND-003', 'Transporte Ibérico S.A.', 'Spain', 'EUR'),
('VEND-004', 'HafenLogistik GmbH', 'Germany', 'EUR'),
('VEND-005', 'SwiftMove Couriers', 'USA', 'USD'),
('VEND-006', 'OceanFreight Pvt Ltd', 'India', 'INR')
ON CONFLICT (vendor_id) DO UPDATE SET
    vendor_name = EXCLUDED.vendor_name,
    country = EXCLUDED.country,
    currency = EXCLUDED.currency;

-- 2. SKU Master
INSERT INTO erp.sku_master (item_code, category, uom, gst_rate) VALUES
('SKU-001', 'Packaging', 'roll', 10.00),
('SKU-002', 'Safety', 'pair', 10.00),
('SKU-003', 'Safety', 'piece', 10.00),
('SKU-101', 'Logistics', 'piece', 10.00),
('SKU-201', 'Packaging', 'box', 10.00),
('SKU-202', 'Packaging', 'label', 10.00),
('SKU-301', 'Transport', 'crate', 10.00),
('SKU-302', 'Safety', 'vest', 10.00),
('SKU-401', 'Charges', 'service', 10.00),
('SKU-402', 'Packaging', 'box', 10.00),
('SKU-501', 'Transport', 'service', 10.00)
ON CONFLICT (item_code) DO UPDATE SET
    category = EXCLUDED.category,
    uom = EXCLUDED.uom,
    gst_rate = EXCLUDED.gst_rate;

-- 3. Purchase Orders
INSERT INTO erp.purchase_orders (po_number, vendor_id) VALUES
('PO-1001', 'VEND-001'),
('PO-1002', 'VEND-002'),
('PO-1003', 'VEND-003'),
('PO-1004', 'VEND-004'),
('PO-1005', 'VEND-005'),
('PO-1006', 'VEND-006')
ON CONFLICT (po_number) DO UPDATE SET
    vendor_id = EXCLUDED.vendor_id;

-- 4. PO Line Items
DELETE FROM erp.po_line_items;

INSERT INTO erp.po_line_items (po_number, item_code, description, qty, unit_price, currency) VALUES
-- PO-1001
('PO-1001', 'SKU-001', 'Pallet Wrapping Film', 50, 12.00, 'USD'),
('PO-1001', 'SKU-002', 'Industrial Gloves', 120, 3.00, 'USD'),
('PO-1001', 'SKU-003', 'Safety Helmets', 30, 15.00, 'USD'),

-- PO-1002
('PO-1002', 'SKU-101', 'Container Seals', 200, 1.25, 'USD'),

-- PO-1003
('PO-1003', 'SKU-201', 'Cajas de carton', 100, 2.50, 'EUR'),
('PO-1003', 'SKU-202', 'Etiquetas adhesivas', 300, 0.30, 'EUR'),

-- PO-1004
('PO-1004', 'SKU-301', 'Transportkisten', 40, 25.00, 'EUR'),
('PO-1004', 'SKU-302', 'Sicherheitswesten', 60, 10.00, 'EUR'),

-- PO-1005
('PO-1005', 'SKU-401', 'Fuel Surcharge', 1, 120.00, 'USD'),
('PO-1005', 'SKU-402', 'Express Delivery Boxes', 25, 4.50, 'USD'),

-- PO-1006
('PO-1006', 'SKU-501', 'Container Transport', 5, 8000.00, 'INR');
