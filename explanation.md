# AI Invoice Auditor: Detailed Project Explanation & Execution Guide

Welcome! This document provides a complete, clear, and comprehensive explanation of everything built in your project, why each technical decision was made, and exact step-by-step instructions on how to run and test the system.

---

## 1. What Exactly Did We Build?

We built a containerized, enterprise-grade **AI Invoice Auditor** system. 
In simple terms:
1. Vendors around the world send invoices (PDFs, Word documents, or scanned images) in English, German, and Spanish into an incoming directory.
2. Our **Agent** picks up the invoice, checks if it was already processed (using a SHA-256 fingerprint), extracts the text (using direct PDF reading or OCR for scans), and translates foreign languages to English using **AWS Bedrock**.
3. It performs mathematical checks (checking if `quantity × unit_price = line total` and checking tax and total amounts).
4. It calls our **Mock ERP service** over HTTP to check if the purchase order exists, and whether the vendor, quantities, and prices match what the company agreed to pay.
5. It generates an audit report (HTML and JSON) with a clear recommendation: **Approve**, **Review**, or **Reject**.
6. It saves all records into **PostgreSQL** (the permanent system of record) and indexes the text into **Qdrant** (the vector database).
7. It runs a **RAG (Retrieval-Augmented Generation) pipeline** that allows users to ask natural-language questions about invoices, and an AI judge evaluates the answer against the **RAG Triad** (Context Relevance, Groundedness, Answer Relevance).
8. It provides a modern **Streamlit Web Dashboard** where human auditors can review discrepancies, submit field corrections without altering original files, and trigger instant re-validation.

---

## 2. Walk-Through of the 6 Microservices

Your project runs as **6 separate Docker containers** that talk to each other across a private Docker network (`invoice-net`):

```
+-------------------------------------------------------------------------------+
|                        Docker Compose Bridge Network                          |
|                                                                               |
|   [streamlit-ui :8501]               [agent :8000]             [mock-erp :8001]
|     Auditor Web UI                     LangGraph AI               ERP Master  
|           |                                  |                         |      
|           | (Reads audit schema)             | (Writes audit)          | (Reads erp)
|           +-----------------+----------------+                         |      
|                             |                                          |      
|                             v                                          v      
|                   [postgres:16 :5432] <--------------------------------+      
|                     - erp schema                                              
|                     - audit schema                                            
|                     - langgraph schema                                        
|                                                                               
|   [qdrant :6333]                     [redis:7 :6379]                          
|     Vector DB (RAG)                    LLM & Translation Cache                
+-------------------------------------------------------------------------------+
```

### 1. `postgres` (PostgreSQL 16)
- **Role:** The permanent system of record.
- **Why PostgreSQL?** It holds structured tables, handles decimal math precisely (`NUMERIC` types prevent loss of cents), and supports JSON storage (`JSONB`).
- **3 Schemas in One DB:**
  - `erp`: Master vendor, SKU, and purchase order data. Owned strictly by `mock-erp`.
  - `audit`: Tables for `invoice_audit`, `invoice_line_items`, `discrepancies`, and `human_feedback`. Written by `agent`, read by `streamlit-ui`.
  - `langgraph`: Stores serialized workflow memory checkpoints.

### 2. `mock-erp` (FastAPI Microservice)
- **Role:** Simulates the company's enterprise ERP backend.
- **Crucial Rule:** The agent cannot directly read ERP tables from the database. It must call `mock-erp:8000` over HTTP. This maintains clean service boundaries.

### 3. `agent` (LangGraph & Bedrock Core Engine)
- **Role:** The brain of the application.
- **Workflow Nodes:**
  - **Monitor Node:** Computes SHA-256 hash. If the hash already exists in PostgreSQL, it skips processing.
  - **Extractor Node:** Extracts text using `pdfplumber` for digital PDFs, `python-docx` for Word documents, and `pytesseract` (with English, German, and Spanish packs) for scanned images.
  - **Translation Node:** Detects language and translates German/Spanish invoices to English using **Cohere Command R+** on AWS Bedrock, caching results in Redis.
  - **Data Validation Node:** Checks completeness and math according to `config/rules.yaml`.
  - **Business Validation Node:** Calls `mock-erp` via HTTP to compare against PO records (e.g. ±5% price tolerance, 0% quantity tolerance).
  - **Reporting Node:** Synthesizes discrepancies into a recommendation, saves everything to PostgreSQL, and writes HTML/JSON reports to disk.
  - **RAG Indexing:** Automatically chunks text and pushes vector embeddings to Qdrant.

### 4. `qdrant` (Qdrant Vector Database)
- **Role:** Holds document embeddings for semantic search.
- **Why it's a "derived store":** The raw text is already stored in PostgreSQL. If Qdrant is deleted or reset, we can re-embed and rebuild the entire index directly from PostgreSQL without ever re-reading the original files or repeating OCR.

### 5. `redis` (Redis 7 In-Memory Cache)
- **Role:** Fast cache for LLM responses and translations.
- **Why it's "disposable":** It speeds up repeated questions and repeated translations. If flushed, nothing breaks—the system just recomputes the answer.

### 6. `streamlit-ui` (Web Dashboard)
- **Role:** Clean web interface for human auditors on port `8501`.
- **Tabs:**
  - **Audit Dashboard:** High-level metrics, approval rates, filterable table.
  - **Invoice Deep Dive:** View raw text vs. translated text, line items, and discrepancy details.
  - **Human-in-the-Loop:** Form to enter field corrections (stored as an `INSERT` into `audit.human_feedback` to preserve history) and trigger instant re-validation.
  - **RAG Assistant:** Ask natural language questions with live RAG Triad scores.
  - **System Topology:** Check health status of all 6 containers.

---

## 3. How LangGraph and RAG Triad Work

### LangGraph Workflow
LangGraph organizes the auditing steps into a stateful directed graph. Each node receives the current `InvoiceState`, performs its job, and passes the updated state to the next node. If a step fails, the checkpointer allows inspection of the exact state where the failure occurred.

### RAG Triad Reflection
When an auditor asks a question (e.g. *"Why was invoice INV-1004 flagged?"*):
1. **Retrieval Agent:** Fetches relevant chunks from Qdrant.
2. **Augmentation Agent:** Formats the chunks into clean context.
3. **Generation Agent:** Uses **Cohere Command R+** to answer the question.
4. **Reflection Agent (Judge):** Uses **Amazon Nova Lite** to grade the answer on 3 metrics:
   - **Context Relevance:** Did the chunks contain the facts needed?
   - **Groundedness:** Is every claim in the answer backed by the chunks (no hallucinations)?
   - **Answer Relevance:** Did the answer directly respond to the user's question?
5. **Quality Gate:** If the average score is `>= 0.70`, the answer is displayed. If `< 0.70`, the pipeline automatically reforms the query, retrieves deeper chunks, and retries (up to 3 times).

---

## 4. Step-by-Step Instructions to Run the Project

### Prerequisites
Make sure you have installed on your computer:
1. **Docker Desktop** (running).
2. **Docker Compose v2** (included with modern Docker Desktop).

---

### Step 1: Configure Environment Variables
Copy the template file to `.env`:
```powershell
cp .env.example .env
```
Open `.env` in any text editor. If you have AWS Bedrock credentials, paste them in:
```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
AWS_SESSION_TOKEN=
```
> **Note:** If you don't enter AWS credentials, the application will automatically use built-in domain-specific mock models so the full pipeline, database, and web UI can be run and tested without errors!

---

### Step 2: Start All 6 Services With One Command
Run in your terminal (PowerShell or Bash) from the project root:
```powershell
docker compose up --build -d
```
Docker will build the 3 application images and start the 3 database/cache services.

---

### Step 3: Verify All Containers Are Healthy
Run:
```powershell
docker compose ps
```
You should see all 6 services with status `healthy` or `running`:
- `agent` (port 8000)
- `mock-erp` (port 8001)
- `streamlit-ui` (port 8501)
- `postgres` (port 5432)
- `qdrant` (port 6333)
- `redis` (port 6379)

---

### Step 4: Open the Web Dashboard
Open your web browser and go to:
👉 **`http://localhost:8501`**

1. On the left sidebar, click **"📥 Scan Incoming Folder"**.
   - The agent will read all invoice files from `data/incoming/`.
   - It will extract, translate, validate against mock-erp, and persist everything into PostgreSQL and Qdrant.
2. Explore the tabs:
   - **📊 Audit Dashboard:** View audited invoices and statuses.
   - **🔍 Invoice Deep Dive:** Click an invoice to inspect line items and discrepancy findings.
   - **✍️ Human-in-the-Loop:** Correct a discrepancy and click **"Save & Re-Validate"**.
   - **🤖 RAG Assistant:** Ask questions like *"What was the issue with HafenLogistik?"* and see the live RAG Triad scores.

---

### Step 5: Stop the System
When you want to stop the containers:
```powershell
docker compose down
```
*(Your data in PostgreSQL and Qdrant will remain saved in named Docker volumes).*

If you want to completely erase the volumes and start from a fresh slate:
```powershell
docker compose down -v
```
