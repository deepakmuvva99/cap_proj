# 📂 Complete Deep-Dive: `data/` folder, ERP, PostgreSQL & Mock-ERP

> This document explains **everything** in the data layer of the AI Invoice Auditor:
> the `data/` folder structure, every file inside it, the PostgreSQL database with its
> three schemas, the Mock-ERP microservice, and how they all talk to each other.

---

## 🗂️ Part 1 — The `data/` Folder (Two Sub-Folders)

The `data/` folder sits at the project root. It is **mounted as a Docker volume** so the
containers can read and write to it. It has exactly two sub-folders:

```
data/
├── ERP_mockdata/       ← fallback reference data for the ERP service
└── incoming/           ← the real invoices that the AI must audit
```

Think of it like a physical filing cabinet:
- **`incoming/`** is the IN-TRAY: vendor invoices arrive here for processing.
- **`ERP_mockdata/`** is the REFERENCE SHELF: the "truth" the company already holds (what was ordered, from whom, at what price).

---

## 📁 Part 1a — `data/incoming/` — The Invoice IN-TRAY

This is the folder the AI **watches and processes**. Every invoice file that lands here
gets picked up, read, audited, and stored.

### How naming works

Every invoice is named with a **coding convention**:

```
INV_{LANGUAGE}_{NUMBER}[_suffix].{extension}
```

| Part | Meaning |
|------|---------|
| `INV` | Short for Invoice — all files start with this |
| `{LANGUAGE}` | Language code: `EN` = English, `DE` = German, `ES` = Spanish |
| `{NUMBER}` | Sequential invoice number (001, 002, 003…) |
| `[_suffix]` | Optional tag e.g., `_scan` (scanned image), `_malformed` (intentionally broken) |
| `.{extension}` | File type: `.pdf`, `.docx`, or `.png` |

### Every file and what it represents

#### 1. `INV_EN_001.pdf` + `INV_EN_001.meta.json`
- **Language**: English  
- **Vendor**: Global Logistics Ltd (UK) — `VEND-001`  
- **PO Referenced**: `PO-1001`  
- **Format**: Normal, text-based PDF (readable without OCR)  
- **Items**: Pallet Wrapping Film, Industrial Gloves, Safety Helmets  
- **What the meta says**: Sent from `accounts@globallogistics.com`, received `2025-03-14 09:32`  
- **Expected Result**: Should PASS — it matches the ERP PO perfectly  

#### 2. `INV_EN_002.pdf` + `INV_EN_002.meta.json`
- **Language**: English  
- **Vendor**: BlueOcean Transport Co. (USA) — `VEND-002`  
- **PO Referenced**: `PO-1002`  
- **Format**: Normal text PDF  
- **Items**: Container Seals  
- **What the meta says**: Sent from `billing@blueocean.com`  
- **Expected Result**: Clean invoice, price comparison with ERP — should mostly APPROVE  

#### 3. `INV_ES_003.pdf` + `INV_ES_003.meta.json`
- **Language**: **Spanish** (ES)  
- **Vendor**: Transporte Ibérico S.A. (Spain) — `VEND-003`  
- **PO Referenced**: `PO-1003`  
- **Format**: Normal PDF written in Spanish  
- **Items**: "Cajas de cartón" (cardboard boxes), "Etiquetas adhesivas" (sticky labels)  
- **What the meta says**: Sent from `facturacion@transporteiberico.es`, language = `es`  
- **What happens**: The agent **detects Spanish**, calls **Cohere Command R+** via AWS Bedrock to translate it to English, then proceeds with English text for validation  
- **Expected Result**: Tests the multilingual pipeline — should REVIEW or APPROVE depending on prices  

#### 4. `INV_DE_004.pdf` + `INV_DE_004.meta.json`
- **Language**: **German** (DE)  
- **Vendor**: HafenLogistik GmbH (Germany) — `VEND-004`  
- **PO Referenced**: `PO-1004`  
- **Format**: DOCX (Word document) — note the meta says `INV_DE_004.docx` as attachment  
- **Items**: "Transportkisten" (transport crates), "Sicherheitswesten" (safety vests)  
- **What the meta says**: Sent from `rechnung@hafenlogistik.de`, language = `de`  
- **What happens**: Agent uses **python-docx** (not PDF reader) to extract paragraphs and table cells. Then **translates German → English** via Bedrock  
- **Expected Result**: Tests DOCX + German translation pipeline  

#### 5. `INV_EN_005_scan.png` + `INV_EN_005_scan.meta.json`
- **Language**: English  
- **Vendor**: SwiftMove Couriers (USA) — `VEND-005`  
- **PO Referenced**: `PO-1005`  
- **Format**: **PNG image** (scanned paper invoice — not a text file at all!)  
- **Items**: Fuel Surcharge, Express Delivery Boxes  
- **What the meta says**: Sent from `billing@swiftmovecouriers.com`  
- **What happens**: Since it's a PNG, the agent uses **Pillow** (image library) to preprocess the image and **pytesseract** (OCR engine) to read text from the image pixels. No PDF parsing here — pure image-to-text  
- **Expected Result**: Tests the OCR pipeline — results depend on image quality  

#### 6. `INV_EN_006_malformed.pdf` + `INV_EN_006_malformed.meta.json`
- **Language**: English  
- **Vendor**: OceanFreight Pvt Ltd (India) — `VEND-006`  
- **PO Referenced**: `PO-1006`  
- **Format**: PDF, but **intentionally broken/missing fields**  
- **Items**: Container Transport  
- **What the meta says**: Sent from `accounts@oceanfreight.in`  
- **What happens**: The validation engine will find mandatory fields missing (e.g., `invoice_no`, `vendor_id`, or `total_amount`). The system will flag discrepancies and set recommendation = **`reject`** or `review`  
- **Expected Result**: Tests the validation failure path — should REJECT  

#### 7. `Actual_invoice.pdf`
- A real-looking PDF invoice (101KB, largest file in the folder)  
- Used as an additional real-world test or demonstration asset  
- Does not follow the `INV_` naming convention — processed as a regular PDF  

---

### What is a `.meta.json` file?

Every invoice PDF/DOCX/PNG has a **companion `.meta.json` file** (same base name). This is
like the **envelope** that came with the attachment in an email. It records:

```json
{
    "sender": "accounts@globallogistics.com",    ← who sent it
    "subject": "Invoice INV-1001 for PO-1001",   ← email subject
    "received_timestamp": "2025-03-14T09:32:00Z",← when it arrived
    "language": "en",                             ← language hint
    "attachments": ["INV_EN_001.pdf"]             ← file name(s)
}
```

The agent reads this `.meta.json` to:
1. **Know the language upfront** (saves detection step)
2. **Know when it arrived** (for date validation — invoices > 365 days old get flagged)
3. **Know the sender** (audit trail)

> If the `.meta.json` is missing, the agent still works — it auto-detects the language from the extracted text.

---

## 📁 Part 1b — `data/ERP_mockdata/` — The Reference/Fallback Data

This folder contains **three JSON files** that act as the **"ground truth" reference data** —
what your company actually ordered, from which vendor, at what price.

These files have a dual purpose:
1. **Primary** → They were used to **seed the PostgreSQL database** when the system first started
2. **Fallback** → If the database connection fails, the Mock-ERP service reads these JSON files directly

### `vendors.json` — Who are our suppliers?

```json
[
    { "vendor_id": "VEND-001", "vendor_name": "Global Logistics Ltd",     "country": "UK",      "currency": "USD" },
    { "vendor_id": "VEND-002", "vendor_name": "BlueOcean Transport Co.",  "country": "USA",     "currency": "USD" },
    { "vendor_id": "VEND-003", "vendor_name": "Transporte Ibérico S.A.",  "country": "Spain",   "currency": "EUR" },
    { "vendor_id": "VEND-004", "vendor_name": "HafenLogistik GmbH",       "country": "Germany", "currency": "EUR" },
    { "vendor_id": "VEND-005", "vendor_name": "SwiftMove Couriers",       "country": "USA",     "currency": "USD" },
    { "vendor_id": "VEND-006", "vendor_name": "OceanFreight Pvt Ltd",     "country": "India",   "currency": "INR" }
]
```

**Purpose**: Every invoice must come from a **known vendor**. When an invoice says "vendor = HafenLogistik GmbH", the agent asks the ERP: "Do you know this vendor?" If yes, it checks whether the invoice's vendor matches what the PO says.

### `sku_master.json` — What items/products do we buy?

```json
[
    { "item_code": "SKU-001", "category": "Packaging",  "uom": "roll",    "gst_rate": 10 },
    { "item_code": "SKU-002", "category": "Safety",     "uom": "pair",    "gst_rate": 10 },
    { "item_code": "SKU-003", "category": "Safety",     "uom": "piece",   "gst_rate": 10 },
    { "item_code": "SKU-101", "category": "Logistics",  "uom": "piece",   "gst_rate": 10 },
    { "item_code": "SKU-201", "category": "Packaging",  "uom": "box",     "gst_rate": 10 },
    { "item_code": "SKU-202", "category": "Packaging",  "uom": "label",   "gst_rate": 10 },
    { "item_code": "SKU-301", "category": "Transport",  "uom": "crate",   "gst_rate": 10 },
    { "item_code": "SKU-302", "category": "Safety",     "uom": "vest",    "gst_rate": 10 },
    { "item_code": "SKU-401", "category": "Charges",    "uom": "service", "gst_rate": 10 },
    { "item_code": "SKU-402", "category": "Packaging",  "uom": "box",     "gst_rate": 10 },
    { "item_code": "SKU-501", "category": "Transport",  "uom": "service", "gst_rate": 10 }
]
```

- `item_code` = SKU identifier on the invoice line
- `category` = what type of product it is
- `uom` = Unit of Measure (rolls, pairs, boxes, services…)
- `gst_rate` = tax rate (10% for all items in this demo)

**Purpose**: When an invoice line says "SKU-001, qty 50", the agent verifies that SKU-001 is a known product code and what its unit of measure is.

### `PO Records.json` — What did we officially ORDER?

This is the most important reference file. A Purchase Order (PO) is the **company's official approval** to buy something:

```json
{
    "po_number": "PO-1001",
    "vendor_id": "VEND-001",
    "line_items": [
        { "item_code": "SKU-001", "description": "Pallet Wrapping Film",  "qty": 50,  "unit_price": 12.00, "currency": "USD" },
        { "item_code": "SKU-002", "description": "Industrial Gloves",     "qty": 120, "unit_price": 3.00,  "currency": "USD" },
        { "item_code": "SKU-003", "description": "Safety Helmets",        "qty": 30,  "unit_price": 15.00, "currency": "USD" }
    ]
}
```

**The PO tells us**:
- We ordered from `VEND-001` (Global Logistics Ltd)
- 50 rolls of Pallet Wrapping Film at $12.00 each
- 120 pairs of Industrial Gloves at $3.00 each
- 30 Safety Helmets at $15.00 each

**When the invoice arrives**, the agent checks:
- Does the invoice vendor match `VEND-001`? ✅ or ❌
- Is quantity on invoice = PO quantity? Must be **exactly 0% deviation** ✅ or ❌
- Is unit price within **±5% of the PO price**? ✅ or ❌

---

## 🗄️ Part 2 — PostgreSQL: One Database, Three Schemas

There is **ONE database** called `invoicedb`. Inside it there are **three completely separate schemas** (think of schemas like separate departments in the same building — they share walls but have their own rooms).

```
invoicedb (single PostgreSQL 16 database)
├── erp         ← Master data / company records (owned by mock-erp service)
├── audit       ← Invoice audit results (owned by agent service)
└── langgraph   ← AI workflow memory / checkpoints (owned by agent service)
```

The schemas live in the file [db/init.sql](file:///c:/Users/Deepu/Downloads/Capstone_Project/db/init.sql).

---

### Schema 1: `erp` — The Company's Master Records

> **Who owns it**: `mock-erp` service  
> **Who can read it**: Only `mock-erp` (the `agent` is **strictly forbidden** from querying this directly)  
> **Purpose**: The single source of truth for "what we ordered and from whom"

#### Tables in `erp` schema:

**`erp.vendors`** — The approved supplier list
```sql
vendor_id    VARCHAR(32) PRIMARY KEY   -- e.g., "VEND-001"
vendor_name  VARCHAR(255)              -- "Global Logistics Ltd"
country      VARCHAR(64)               -- "UK"
currency     CHAR(3)                   -- "USD"
```

**`erp.sku_master`** — The catalogue of items/products we buy
```sql
item_code    VARCHAR(64) PRIMARY KEY   -- e.g., "SKU-001"
category     VARCHAR(64)               -- "Packaging"
uom          VARCHAR(32)               -- "roll"
gst_rate     NUMERIC(5,2)              -- 10.00
```

**`erp.purchase_orders`** — Header of each purchase order
```sql
po_number    VARCHAR(64) PRIMARY KEY   -- e.g., "PO-1001"
vendor_id    VARCHAR(32) FK→vendors    -- "VEND-001"
created_at   TIMESTAMPTZ               -- when PO was created
```

**`erp.po_line_items`** — The individual items within each PO
```sql
id           BIGSERIAL PRIMARY KEY
po_number    VARCHAR(64) FK→purchase_orders
item_code    VARCHAR(64) FK→sku_master
description  TEXT                      -- "Pallet Wrapping Film"
qty          NUMERIC(12,3)             -- 50.000
unit_price   NUMERIC(14,4)             -- 12.0000
currency     CHAR(3)                   -- "USD"
```

**How the tables link**:
```
erp.purchase_orders  →  links to →  erp.vendors      (via vendor_id)
erp.po_line_items    →  links to →  erp.purchase_orders (via po_number)
erp.po_line_items    →  links to →  erp.sku_master   (via item_code)
```

**Real example — reading PO-1001**:
> PO-1001 was placed with VEND-001 (Global Logistics Ltd, UK, USD currency).
> It contains 3 line items:
> - 50 rolls of SKU-001 (Pallet Wrapping Film) @ $12.00
> - 120 pairs of SKU-002 (Industrial Gloves) @ $3.00
> - 30 pieces of SKU-003 (Safety Helmets) @ $15.00

---

### Schema 2: `audit` — The Invoice Audit Trail

> **Who writes to it**: Only the `agent` service (Single Writer Principle)  
> **Who reads from it**: `streamlit-ui` reads for the dashboard; `agent` also reads for RAG  
> **Purpose**: Permanent, immutable record of every invoice processed and all findings

#### Tables in `audit` schema:

**`audit.invoice_audit`** — One row per invoice processed
```sql
invoice_id          UUID PRIMARY KEY      -- auto-generated unique ID (e.g., "550e8400-e29b-41d4...")
file_path           VARCHAR(512)          -- "/data/incoming/INV_EN_001.pdf"
file_checksum       VARCHAR(64) UNIQUE    -- SHA-256 of the file bytes — prevents re-processing same file
extraction_method   VARCHAR(32)           -- "pdfplumber" | "docx" | "tesseract"
raw_extracted_text  TEXT                  -- FULL raw text pulled from the file
translated_text     TEXT                  -- English translation (same as raw if already English)
source_language     VARCHAR(8)            -- "en" | "de" | "es"
translation_confidence NUMERIC(4,3)       -- 0.000 to 1.000 (how confident the translation is)
invoice_number      VARCHAR(64)           -- "INV-1001" (extracted from the document)
vendor_name         VARCHAR(255)          -- "Global Logistics Ltd"
po_number           VARCHAR(64)           -- "PO-1001"
invoice_date        DATE                  -- 2025-03-14
currency            CHAR(3)               -- "USD"
total_amount        NUMERIC(14,2)         -- 1260.00
subtotal            NUMERIC(14,2)         -- 1200.00
tax_amount          NUMERIC(14,2)         -- 60.00
validation_status   VARCHAR(32)           -- "passed" | "failed" | "partial"
recommendation      VARCHAR(32)           -- "approve" | "review" | "reject"
extracted_raw       JSONB                 -- any extra unstructured fields stored as JSON
thread_id           VARCHAR(128)          -- links to LangGraph checkpoint (workflow memory)
processed_at        TIMESTAMPTZ           -- when the agent processed this invoice
```

> **Key insight — `file_checksum`**: When a new file arrives, the agent computes its SHA-256 hash and **checks if that hash already exists** in this column. If yes → skip (already audited). This prevents duplicate processing even if the same file arrives twice.

**`audit.invoice_line_items`** — Each line from the invoice
```sql
id           BIGSERIAL PRIMARY KEY
invoice_id   UUID FK→invoice_audit      -- which invoice this line belongs to
line_number  INTEGER                    -- line 1, 2, 3…
item_code    VARCHAR(64)                -- "SKU-001"
description  TEXT                       -- "Pallet Wrapping Film"
quantity     NUMERIC(12,3)              -- 50.000
unit_price   NUMERIC(14,4)              -- 12.0000
line_total   NUMERIC(14,2)              -- 600.00
```

**`audit.discrepancies`** — Every mismatch found
```sql
id              BIGSERIAL PRIMARY KEY
invoice_id      UUID FK→invoice_audit
field_name      VARCHAR(64)    -- "unit_price" | "quantity" | "vendor_name" | "currency"
invoice_value   TEXT           -- what the invoice says: "12.50"
erp_value       TEXT           -- what ERP says: "12.00"
deviation_pct   NUMERIC(8,4)   -- percentage difference: 4.1667
severity        VARCHAR(16)    -- "low" | "medium" | "high" | "critical"
detected_at     TIMESTAMPTZ    -- when was this found
```

**Example discrepancy**:
> Invoice says SKU-001 unit price = $12.60  
> ERP (PO-1001) says unit price = $12.00  
> Deviation = (12.60 - 12.00) / 12.00 × 100 = **5.0%** → exceeds ±5% tolerance → **HIGH severity discrepancy**

**`audit.human_feedback`** — Human corrections from Streamlit UI (NON-DESTRUCTIVE)
```sql
id               BIGSERIAL PRIMARY KEY
invoice_id       UUID FK→invoice_audit
field_name       VARCHAR(64)     -- "vendor_name" | "total_amount" etc.
original_value   TEXT            -- what the AI extracted: "Global Logistics"
corrected_value  TEXT            -- what the human corrected to: "Global Logistics Ltd"
corrected_by     VARCHAR(128)    -- "auditor" (default) or user's name
corrected_at     TIMESTAMPTZ     -- timestamp of correction
revalidated      BOOLEAN         -- FALSE initially; TRUE after human triggers re-audit
```

> **Why non-destructive?** The original `audit.invoice_audit` row is **NEVER updated or deleted**. Human corrections go into a **separate table**. This preserves the complete audit trail — you can always see what the AI originally extracted vs. what a human corrected. Perfect for compliance.

---

### Schema 3: `langgraph` — AI Workflow Memory

> **Who owns it**: `agent` service  
> **Purpose**: LangGraph (the AI orchestration framework) needs to save "where it is" in the multi-step workflow. This is like a save-game feature for the AI processing pipeline.

#### Tables in `langgraph` schema:

**`langgraph.checkpoints`** — Snapshot of the entire graph state at each step
```sql
thread_id             VARCHAR(128)  -- unique run identifier (e.g., "audit-INV_EN_001-xyz")
checkpoint_ns         VARCHAR(128)  -- namespace (usually empty string "")
checkpoint_id         VARCHAR(128)  -- unique ID for this checkpoint
parent_checkpoint_id  VARCHAR(128)  -- which step came before (for rollback/replay)
type                  VARCHAR(64)   -- type identifier
checkpoint            BYTEA         -- binary blob of full graph state
metadata              BYTEA         -- binary blob of metadata
```

**`langgraph.checkpoint_blobs`** — Individual data channels saved between steps
```sql
thread_id      VARCHAR(128)
checkpoint_ns  VARCHAR(128)
channel        VARCHAR(128)  -- which part of the graph state this belongs to
version        VARCHAR(128)
type           VARCHAR(64)
blob           BYTEA         -- the actual binary data
```

**`langgraph.checkpoint_writes`** — Pending writes during graph execution
```sql
thread_id      VARCHAR(128)
checkpoint_ns  VARCHAR(128)
checkpoint_id  VARCHAR(128)
task_id        VARCHAR(128)
idx            INTEGER
channel        VARCHAR(128)
type           VARCHAR(64)
blob           BYTEA
```

**In simple terms**: When the agent is processing INV_EN_001 and it finishes the "extract" step but hasn't done "validate" yet, LangGraph saves the current state to `langgraph.checkpoints`. If the container crashes mid-way, it can **resume from where it left off** rather than starting over.

---

## 🏭 Part 3 — The Mock-ERP Service (FastAPI Microservice)

The Mock-ERP service lives in [mock_erp/](file:///c:/Users/Deepu/Downloads/Capstone_Project/mock_erp/) and runs as its own Docker container on port 8001 (host) / 8000 (container).

### What is it?

In a real company, there would be a giant SAP or Oracle ERP system. For this project, we simulate it with a **lightweight FastAPI service** that exposes only 3 HTTP endpoints (the exact queries our agent needs). The agent cannot go to PostgreSQL directly for ERP data — it **must** go through this service.

### The 3 API Endpoints

```
GET /po/{po_number}       → "What was in Purchase Order PO-1001?"
GET /vendor/{vendor_id}   → "Tell me about vendor VEND-001"
GET /sku/{sku_code}       → "What is SKU-001?"
GET /health               → "Are you alive?"
```

#### Example calls and responses:

**`GET http://mock-erp:8000/po/PO-1001`**
```json
{
    "po_number": "PO-1001",
    "vendor_id": "VEND-001",
    "line_items": [
        { "item_code": "SKU-001", "description": "Pallet Wrapping Film", "qty": 50.0, "unit_price": 12.0, "currency": "USD" },
        { "item_code": "SKU-002", "description": "Industrial Gloves",    "qty": 120.0, "unit_price": 3.0, "currency": "USD" },
        { "item_code": "SKU-003", "description": "Safety Helmets",       "qty": 30.0,  "unit_price": 15.0, "currency": "USD" }
    ]
}
```

**`GET http://mock-erp:8000/vendor/VEND-001`**
```json
{
    "vendor_id": "VEND-001",
    "vendor_name": "Global Logistics Ltd",
    "country": "UK",
    "currency": "USD"
}
```

**`GET http://mock-erp:8000/sku/SKU-001`**
```json
{
    "item_code": "SKU-001",
    "category": "Packaging",
    "uom": "roll",
    "gst_rate": 10.0
}
```

If a PO, vendor, or SKU is **not found**, it returns:
```json
HTTP 404
{ "detail": "Purchase order 'PO-9999' not found in ERP system." }
```

### Two-Layer Fallback Design in `database.py`

The Mock-ERP service is resilient — it has **two layers** for fetching data:

```
Layer 1 (Primary):   Query PostgreSQL erp schema
         ↓ (if DB is down or fails)
Layer 2 (Fallback):  Read JSON files from /data/ERP_mockdata/
```

Code from [mock_erp/app/database.py](file:///c:/Users/Deepu/Downloads/Capstone_Project/mock_erp/app/database.py):
```python
def fetch_purchase_order(po_number: str):
    try:
        # Try PostgreSQL first
        with get_connection() as conn:
            cur.execute("SELECT ... FROM erp.purchase_orders WHERE po_number = %s", (po_number,))
            ...
    except Exception as exc:
        # If DB fails, read from JSON file
        data = _load_fallback_json("PO Records.json")
        for item in data:
            if item.get("po_number") == po_number:
                return item
```

This means even if PostgreSQL is down, the system **doesn't crash** — it falls back to the JSON files. This is why the JSON files exist in `data/ERP_mockdata/`.

### Pydantic Models in `models.py`

The service uses [Pydantic models](file:///c:/Users/Deepu/Downloads/Capstone_Project/mock_erp/app/models.py) to **validate and type-check** all responses:

```python
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
```

FastAPI automatically uses these to serialize the responses into JSON and also validates incoming data. If any field is wrong type/missing, FastAPI returns a 422 error automatically.

---

## 🔁 Part 4 — How Everything Works Together (The Full Flow)

```
Step 1: Invoice arrives
    data/incoming/INV_EN_001.pdf
    data/incoming/INV_EN_001.meta.json
              ↓
Step 2: Agent computes SHA-256 of INV_EN_001.pdf
    Checks: SELECT file_checksum FROM audit.invoice_audit WHERE file_checksum = '<hash>'
    → Not found → proceed (new invoice)
    → Found → SKIP (already audited)
              ↓
Step 3: Agent reads .meta.json → knows it's English, from accounts@globallogistics.com
              ↓
Step 4: Agent extracts text from PDF via pdfplumber
    (If text < 30 chars → falls back to tesseract OCR)
    (If DOCX → uses python-docx)
    (If PNG → uses pytesseract)
              ↓
Step 5: Language check — English? → No translation needed
    (German/Spanish? → Call Cohere Command R+ via AWS Bedrock to translate)
              ↓
Step 6: Field extraction
    Regex patterns pick up: invoice_number, vendor_name, po_number, dates, currency, amounts
    Amazon Nova Lite LLM fills gaps for unstructured parts
              ↓
Step 7: Rule validation (from config/rules.yaml)
    ✓ All header fields present? (invoice_no, vendor_id, currency, total_amount, date)
    ✓ Currency in [USD, EUR, INR, GBP]?
    ✓ Date not > 7 days in future? Not > 365 days old?
    ✓ Line math: qty × unit_price == line_total (within 1%)?
    ✓ Total math: sum(line_totals) + tax == total_amount (within $1.00)?
              ↓
Step 8: ERP cross-reference (via HTTP to mock-erp service)
    GET http://mock-erp:8000/po/PO-1001
    → Compares: vendor match, quantity match (0% tolerance), price match (±5%)
    → Records each mismatch into audit.discrepancies
              ↓
Step 9: Recommendation
    Zero issues + translation confidence ≥ 0.95 → "approve"
    Some issues (medium/high discrepancy, missing fields, low confidence) → "review"
    Bad currency, PO not found, critical severity → "reject"
              ↓
Step 10: Save everything to PostgreSQL audit schema
    INSERT INTO audit.invoice_audit (...)      ← full extracted data
    INSERT INTO audit.invoice_line_items (...) ← all line items
    INSERT INTO audit.discrepancies (...)      ← all mismatches found
              ↓
Step 11: Index into Qdrant vector database
    Embed raw text + audit report → vectors → stored in Qdrant collection "invoice_audit_rag"
    This enables the RAG chatbot to answer questions about any invoice
              ↓
Step 12: Human reviews in Streamlit UI
    Reads from audit.invoice_audit, audit.invoice_line_items, audit.discrepancies
    If human corrects something:
        INSERT INTO audit.human_feedback (...) ← stored separately, original untouched
```

---

## 📊 Part 5 — Invoice-to-PO Mapping Summary

| Invoice File | Language | Vendor | PO | Expected Result |
|---|---|---|---|---|
| `INV_EN_001.pdf` | English | VEND-001 (Global Logistics Ltd, UK) | PO-1001 | ✅ APPROVE |
| `INV_EN_002.pdf` | English | VEND-002 (BlueOcean Transport Co., USA) | PO-1002 | ✅ APPROVE/REVIEW |
| `INV_ES_003.pdf` | **Spanish** | VEND-003 (Transporte Ibérico S.A., Spain) | PO-1003 | 🔄 Translation tested |
| `INV_DE_004.pdf` | **German** | VEND-004 (HafenLogistik GmbH, Germany) | PO-1004 | 🔄 Translation + DOCX tested |
| `INV_EN_005_scan.png` | English | VEND-005 (SwiftMove Couriers, USA) | PO-1005 | 📷 OCR tested |
| `INV_EN_006_malformed.pdf` | English | VEND-006 (OceanFreight Pvt Ltd, India) | PO-1006 | ❌ REJECT (broken) |
| `Actual_invoice.pdf` | English | Real-world demo | — | Real test |

---

## 🔐 Part 6 — Why the Agent Cannot Query ERP Schema Directly

This is a **critical design principle** called the **ERP Service Boundary**:

```
❌ WRONG (not allowed):
   agent → SELECT * FROM erp.vendors  (direct DB query)

✅ RIGHT (enforced design):
   agent → GET http://mock-erp:8000/vendor/VEND-001  (HTTP API call)
```

**Why?**
1. **Real-world ERP systems** (SAP, Oracle) never give direct DB access — they expose APIs
2. **Separation of concerns** — the agent doesn't need to know how ERP stores data
3. **Security** — limiting access surfaces reduces risk
4. **Replaceability** — swap mock-erp with real SAP tomorrow by just changing the URL
5. **Auditability** — all ERP lookups go through one service = one log source

---

## 🗺️ Final Summary Map

```
data/
├── ERP_mockdata/
│   ├── vendors.json       ← 6 vendors (UK, USA, Spain, Germany, India)
│   ├── sku_master.json    ← 11 product codes (Packaging, Safety, Logistics, Transport)
│   └── PO Records.json    ← 6 Purchase Orders (PO-1001 to PO-1006), 11 line items total
│
└── incoming/
    ├── INV_EN_001.pdf + .meta.json    ← English PDF, VEND-001, PO-1001
    ├── INV_EN_002.pdf + .meta.json    ← English PDF, VEND-002, PO-1002
    ├── INV_ES_003.pdf + .meta.json    ← Spanish PDF, VEND-003, PO-1003
    ├── INV_DE_004.pdf + .meta.json    ← German DOCX, VEND-004, PO-1004
    ├── INV_EN_005_scan.png + .meta    ← Scanned PNG, VEND-005, PO-1005 (OCR)
    ├── INV_EN_006_malformed.pdf + .meta ← Broken PDF, VEND-006, PO-1006 (REJECT)
    └── Actual_invoice.pdf             ← Real-world demo invoice

db/
├── init.sql         ← Creates ALL 3 schemas + tables + seeds ALL data
├── erp_schema.sql   ← ERP schema only (standalone version)
└── audit_schema.sql ← Audit schema only (standalone version)

mock_erp/app/
├── main.py          ← 3 FastAPI routes: /po, /vendor, /sku, /health
├── database.py      ← Queries PostgreSQL erp schema; falls back to JSON files
└── models.py        ← Pydantic response models for type safety

PostgreSQL: invoicedb
├── erp schema      ← Owned by mock-erp; 4 tables (vendors, sku_master, purchase_orders, po_line_items)
├── audit schema    ← Owned by agent; 4 tables (invoice_audit, invoice_line_items, discrepancies, human_feedback)
└── langgraph schema ← Owned by agent; 3 tables (checkpoints, checkpoint_blobs, checkpoint_writes)
```




