# AI Invoice Auditor: Multilingual Agentic Validation System
## Capstone Project Presentation (5 Slides)

---

## Slide 1: Project Overview & Problem Statement

### Business Context
- Global logistics firms receive hundreds of daily vendor invoices in heterogeneous formats (PDF, DOCX, scanned PNG) and diverse languages (English, German, Spanish).
- Manual auditing is slow, expensive, and error-prone across hundreds of line items and cross-currency conversions.

### Solution: Autonomous Multi-Service Agentic AI System
- **Single-Command Containerized Deployment:** 6 containerized services running via Docker Compose (`docker compose up --build -d`).
- **Complete Ingestion & Extraction:** Direct PDF parsing, DOCX processing, and Tesseract OCR with automatic fallback.
- **Multilingual Bedrock Translation:** Autonomous source language detection, Cohere Command R+ translation, confidence scoring, and Redis caching.
- **Dual Validation Engine:** Configurable completeness/arithmetic rules (`rules.yaml`) + strict HTTP mock ERP PO verification.
- **Durable Audit Trail:** Relational PostgreSQL 16 system of record surviving complete container destruction.
- **Natural-Language RAG:** Qdrant vector index with LangGraph RAG Triad reflection (Context Relevance, Groundedness, Answer Relevance >= 0.70).
- **Human-in-the-Loop:** Streamlit dashboard enabling non-destructive auditor feedback and instant re-validation.

---

## Slide 2: Deployed Solution Architecture

```
+---------------------------------------------------------------------------------------------------------+
|                                      DOCKER COMPOSE BRIDGE NETWORK                                      |
|                                                                                                         |
|     +-------------------------+                     +---------------------------------------------+     |
|     |  streamlit-ui (:8501)   |                     |                agent (:8000)                |     |
|     |  - Streamlit Dashboard  |                     |  - LangGraph Audit Workflow (6 Nodes)       |     |
|     |  - Auditor Corrections  |--HTTP :8000 (reval)-|  - RAG Pipeline (Retrieval + Reflection)    |     |
|     +-------------------------+                     +---------------------------------------------+     |
|                  |                                         |           |               |                |
|           SQL (Read Audit)                           SQL (Writes)  HTTP :8000     Vector Ops (gRPC)     |
|                  |                                         |           |               |                |
|                  v                                         v           v               v                |
|     +-------------------------+                     +----------+  +----------+   +----------------+     |
|     |      postgres:16        |                     | mock-erp |  |  redis:7 |   |  qdrant:v1.9   |     |
|     |  Schemas:               |                     |  (:8001) |  |  (:6379) |   |    (:6333)     |     |
|     |  - erp (Master Data)    |<--SQL (Read erp)----| - Master |  | - LLM &  |   | - RAG Chunks & |     |
|     |  - audit (Audit Trail)  |                     |   API    |  |   Trans  |   |   Payloads     |     |
|     |  - langgraph (Checkpts) |                     +----------+  |   Cache  |   +----------------+     |
|     |  [Named Volume]         |                                   +----------+     [Named Volume]       |
|     +-------------------------+                                                                         |
+---------------------------------------------------------------------------------------------------------+
```

### Architectural Boundaries & Design Principles
1. **Agent Writes Exclusively:** Only `agent` inserts audit records and line items; UI never alters raw extractions.
2. **Strict ERP Service Boundary:** ERP data is accessible *only* through `mock-erp:8000` HTTP API. Direct database queries into `erp` schema from the agent are strictly prohibited.
3. **Qdrant Derived From PostgreSQL:** Vector index is entirely rebuildable from persisted PostgreSQL text without repeating OCR.
4. **Redis Disposable by Design:** Ephemeral cache for `llm:{sha256(prompt)}` and translations; no data loss on cache flush.

---

## Slide 3: LangGraph Invoice Auditing Workflow

```
[Monitor Node] ──> [Extractor Node] ──> [Translation Node] ──> [Data Validation] ──> [Business Validation] ──> [Reporting Node]
  - SHA-256 Checksum  - pdfplumber        - Language Detection   - rules.yaml          - Mock ERP HTTP API        - Rec: Approve/
  - Duplicate Check   - OCR Fallback      - Bedrock Cohere R+    - Header Completeness - Price Tol: ±5%             Review/Reject
  - Route by Ext      - Store Raw Text    - Redis Cache          - Line Math & Tax     - Qty Tol: 0%              - HTML/JSON Report
                                                                                       - Discrepancy Records      - PostgreSQL Save
```

### Key Technical Capabilities
- **Deduplication:** Computes SHA-256 hash upfront. Already-audited files are skipped immediately, preventing redundant processing.
- **Multilingual Support:** Scanned German (`INV_DE_004`) and Spanish (`INV_ES_003`) invoices are OCR'd with multi-language Tesseract models and translated to English with confidence ratings.
- **Strict Mathematical Auditing:** Verifies `qty * unit_price == line_total` within 1% tolerance; reconciles subtotal + tax against invoice total.
- **Cross-Service Business Validation:** Matches PO lines against ERP master data. Discrepancy rows are created with field name, invoice value, ERP value, deviation %, and severity.

---

## Slide 4: LangGraph RAG Pipeline & RAG Triad Reflection

```
                       User Question
                             │
                             ▼
                    ┌─────────────────┐
                    │ Retrieval Agent │ <───────────┐
                    │ (Qdrant Search) │             │ Retry Retrieval
                    └────────┬────────┘             │ (Expanded k)
                             │ Chunks               │
                             ▼                      │
                   ┌──────────────────┐             │
                   │Augmentation Agent│             │
                   │ (Format Context) │             │
                   └─────────┬────────┘             │
                             │                      │
                             ▼                      │
                   ┌──────────────────┐             │
                   │ Generation Agent │             │
                   │(Cohere Command R+)             │
                   └─────────┬────────┘             │
                             │ Answer               │
                             ▼                      │
                  ┌────────────────────┐            │
                  │  Reflection Agent  │            │
                  │ (RAG Triad Judge)  │            │
                  └──────────┬─────────┘            │
                             │                      │
                   Average Score >= 0.70?           │
                        /        \                  │
                     Yes          No ───────────────┘
                      │       (Max 3 Retries)
                      ▼
               Display Answer
```

### RAG Triad Metrics
1. **Context Relevance:** Does the retrieved chunk contain the specific invoice data needed?
2. **Groundedness (Faithfulness):** Are all claims strictly supported by the text without hallucination?
3. **Answer Relevance:** Does the response directly address the auditor's question?
- **Quality Gate:** If `average_score < 0.70`, the pipeline automatically reforms the query and expands `k`, looping up to 3 times before returning the response.

---

## Slide 5: Human-in-the-Loop & Production Verification

### Non-Destructive Human Feedback
- Auditors can review extracted discrepancies and submit corrections through the Streamlit UI.
- Corrections are stored as `INSERT INTO audit.human_feedback`, strictly preserving the original OCR/extracted values for audit compliance.
- Clicking **"Re-Validate"** calls `POST http://agent:8000/revalidate`, which re-runs business rules against the corrected values and updates the final recommendation.

### 6 Verification Checks (Evaluator Guide)
1. **Check 1 — Single-Command Startup:** `docker compose down -v && docker compose up --build -d` starts all 6 containers healthy.
2. **Check 2 — End-to-End Processing:** Process invoices in `/data/incoming/` -> validated against ERP -> HTML report produced.
3. **Check 3 — Persistence Across Restart:** `docker compose down` followed by `docker compose up -d` preserves PostgreSQL audit records and Qdrant RAG index without reprocessing.
4. **Check 4 — Deliberate Data Loss:** `docker compose down -v` wipes volumes cleanly, demonstrating volume durability.
5. **Check 5 — No Secrets in Images:** `docker history <image> --no-trunc` verifies no AWS keys or passwords exist in image layers.
6. **Check 6 — Service-Name DNS Resolution:** `docker compose exec agent getent hosts postgres mock-erp qdrant redis` confirms proper bridge networking.
