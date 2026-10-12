-- =============================================================
-- AI Invoice Auditor – Audit Schema Definition
-- =============================================================
-- Owned by: agent (writes), streamlit-ui (reads)
-- =============================================================

CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.invoice_audit (
    invoice_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path VARCHAR(512),                     -- Reference to incoming file volume
    file_checksum VARCHAR(64) UNIQUE,           -- SHA-256 prevents duplicate reprocessing
    extraction_method VARCHAR(32),              -- pdfplumber | docx | tesseract
    raw_extracted_text TEXT,                    -- Full verbatim extracted text
    translated_text TEXT,                       -- Translated English content
    source_language VARCHAR(8),                 -- Detected language code (en, de, es, etc.)
    translation_confidence NUMERIC(4,3),        -- Confidence metric 0.000 to 1.000
    invoice_number VARCHAR(64),                 -- Extracted invoice identifier
    vendor_name VARCHAR(255),                   -- Extracted vendor name
    po_number VARCHAR(64),                      -- Referenced Purchase Order
    invoice_date DATE,                          -- Extracted invoice date
    currency CHAR(3),                           -- Standardized 3-letter currency (USD, EUR, INR, GBP)
    total_amount NUMERIC(14,2),                 -- Total payable amount
    subtotal NUMERIC(14,2),                     -- Subtotal before taxes
    tax_amount NUMERIC(14,2),                   -- Tax amount
    validation_status VARCHAR(32) DEFAULT 'pending', -- passed | failed | partial
    recommendation VARCHAR(32) DEFAULT 'review',     -- approve | review | reject
    extracted_raw JSONB,                        -- Additional unstructured or extra fields
    thread_id VARCHAR(128),                     -- Links to LangGraph state checkpoint
    processed_at TIMESTAMPTZ DEFAULT now()      -- Audit timestamp
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

CREATE INDEX IF NOT EXISTS idx_invoice_audit_checksum ON audit.invoice_audit(file_checksum);
CREATE INDEX IF NOT EXISTS idx_invoice_audit_po ON audit.invoice_audit(po_number);
CREATE INDEX IF NOT EXISTS idx_invoice_audit_vendor ON audit.invoice_audit(vendor_name);
CREATE INDEX IF NOT EXISTS idx_discrepancies_invoice ON audit.discrepancies(invoice_id);
CREATE INDEX IF NOT EXISTS idx_line_items_invoice ON audit.invoice_line_items(invoice_id);
