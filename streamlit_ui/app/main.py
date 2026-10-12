"""AI Invoice Auditor – Streamlit Auditor Dashboard."""
import os
import streamlit as st
import pandas as pd
from datetime import datetime
from db import get_all_invoices, get_invoice_full, insert_human_feedback
from api_client import (
    trigger_scan,
    trigger_revalidate,
    query_rag_service,
    trigger_rebuild_index,
    check_health,
)

# Page Configuration
st.set_page_config(
    page_title="AI Invoice Auditor",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished, enterprise look
st.markdown("""
<style>
    .main-header { font-size: 28px; font-weight: 700; color: #1E293B; margin-bottom: 4px; }
    .sub-header { font-size: 14px; color: #64748B; margin-bottom: 24px; }
    .metric-card {
        background: #FFFFFF;
        border-radius: 10px;
        padding: 18px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #E2E8F0;
        text-align: center;
    }
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
    }
    .badge-approve { background-color: #D1FAE5; color: #065F46; }
    .badge-review { background-color: #FEF3C7; color: #92400E; }
    .badge-reject { background-color: #FEE2E2; color: #991B1B; }
    .triad-box {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px;
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.image("https://img.icons8.com/fluency/96/bill.png", width=64)
st.sidebar.title("AI Invoice Auditor")
st.sidebar.caption("Multilingual Agentic Validation")

# Service Health Status
st.sidebar.markdown("### 🔌 Microservices Status")
health_data = check_health()
agent_status = "🟢 Healthy" if health_data.get("agent") else "🔴 Offline"
erp_status = "🟢 Healthy" if health_data.get("mock_erp") else "🔴 Offline"

st.sidebar.write(f"**Agent Service:** {agent_status}")
st.sidebar.write(f"**Mock ERP Service:** {erp_status}")

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚡ Quick Actions")
if st.sidebar.button("📥 Scan Incoming Folder", use_container_width=True):
    with st.spinner("Processing incoming folder via Agent workflow..."):
        res = trigger_scan()
        if "error" in res:
            st.sidebar.error(f"Scan failed: {res['error']}")
        else:
            st.sidebar.success(f"Processed {res.get('processed_count', 0)} file(s)!")
            st.rerun()

if st.sidebar.button("🔄 Rebuild RAG Index", use_container_width=True):
    with st.spinner("Rebuilding Qdrant vectors from PostgreSQL..."):
        res = trigger_rebuild_index()
        if "error" in res:
            st.sidebar.error(f"Rebuild failed: {res['error']}")
        else:
            st.sidebar.success(f"Indexed {res.get('chunks_indexed', 0)} chunks!")

# Top Navigation Tabs
tabs = st.tabs([
    "📊 Audit Dashboard",
    "🔍 Invoice Deep Dive",
    "✍️ Human-in-the-Loop",
    "🤖 RAG Assistant",
    "⚙️ System Topology",
])

invoices = get_all_invoices()
df_invoices = pd.DataFrame(invoices) if invoices else pd.DataFrame()

# ==============================================================================
# TAB 1: AUDIT DASHBOARD
# ==============================================================================
with tabs[0]:
    st.markdown("<div class='main-header'>Invoice Audit Overview</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Real-time status of all audited vendor invoices across formats and languages</div>", unsafe_allow_html=True)

    if df_invoices.empty:
        st.info("No audited invoices found in the system yet. Click **'Scan Incoming Folder'** in the sidebar to process invoices from `/data/incoming`.")
    else:
        # Metric KPI cards
        col1, col2, col3, col4, col5 = st.columns(5)
        total_inv = len(df_invoices)
        approved_cnt = len(df_invoices[df_invoices["recommendation"] == "approve"])
        review_cnt = len(df_invoices[df_invoices["recommendation"] == "review"])
        reject_cnt = len(df_invoices[df_invoices["recommendation"] == "reject"])

        with col1:
            st.metric("Total Invoices", total_inv)
        with col2:
            st.metric("Approved", approved_cnt, delta=f"{(approved_cnt/total_inv)*100:.0f}%" if total_inv else "0%")
        with col3:
            st.metric("Manual Review", review_cnt, delta=f"{(review_cnt/total_inv)*100:.0f}%" if total_inv else "0%", delta_color="off")
        with col4:
            st.metric("Rejected", reject_cnt, delta=f"-{(reject_cnt/total_inv)*100:.0f}%" if total_inv else "0%", delta_color="inverse")
        with col5:
            multilingual_cnt = len(df_invoices[df_invoices["source_language"] != "en"])
            st.metric("Multilingual", multilingual_cnt)

        st.markdown("---")

        # Filters
        fcol1, fcol2, fcol3 = st.columns([2, 1, 1])
        with fcol1:
            search_query = st.text_input("🔍 Search by Invoice #, Vendor, or PO", placeholder="e.g. INV-1001, HafenLogistik...")
        with fcol2:
            rec_filter = st.selectbox("Recommendation Filter", ["All", "approve", "review", "reject"])
        with fcol3:
            lang_filter = st.selectbox("Language Filter", ["All"] + sorted(list(df_invoices["source_language"].dropna().unique())))

        # Apply Filters
        filtered = df_invoices.copy()
        if search_query:
            filtered = filtered[
                filtered["invoice_number"].astype(str).str.contains(search_query, case=False, na=False) |
                filtered["vendor_name"].astype(str).str.contains(search_query, case=False, na=False) |
                filtered["po_number"].astype(str).str.contains(search_query, case=False, na=False)
            ]
        if rec_filter != "All":
            filtered = filtered[filtered["recommendation"] == rec_filter]
        if lang_filter != "All":
            filtered = filtered[filtered["source_language"] == lang_filter]

        # Display Invoices Table
        display_df = filtered[[
            "invoice_number", "vendor_name", "po_number", "invoice_date",
            "currency", "total_amount", "source_language", "translation_confidence",
            "extraction_method", "recommendation"
        ]].copy()
        display_df.rename(columns={
            "invoice_number": "Invoice #",
            "vendor_name": "Vendor",
            "po_number": "PO #",
            "invoice_date": "Date",
            "currency": "Currency",
            "total_amount": "Total",
            "source_language": "Lang",
            "translation_confidence": "Conf.",
            "extraction_method": "Method",
            "recommendation": "Recommendation"
        }, inplace=True)

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )

# ==============================================================================
# TAB 2: INVOICE DEEP DIVE
# ==============================================================================
with tabs[1]:
    st.markdown("<div class='main-header'>Invoice Deep Dive & Discrepancy Breakdown</div>", unsafe_allow_html=True)

    if df_invoices.empty:
        st.warning("No invoices available. Run a folder scan first.")
    else:
        inv_options = {
            f"{row['invoice_number'] or 'N/A'} ({row['vendor_name'] or 'Unknown'}) - {str(row['invoice_id'])[:8]}": str(row['invoice_id'])
            for _, row in df_invoices.iterrows()
        }
        selected_label = st.selectbox("Select Invoice to Inspect", list(inv_options.keys()))
        selected_id = inv_options[selected_label]

        inv_data = get_invoice_full(selected_id)
        if inv_data:
            # Header card
            rec = inv_data.get("recommendation", "review").upper()
            badge_class = f"badge-{rec.lower()}"
            st.markdown(f"### Status: <span class='badge {badge_class}'>{rec}</span>", unsafe_allow_html=True)

            hcol1, hcol2, hcol3, hcol4 = st.columns(4)
            hcol1.write(f"**Invoice Number:** `{inv_data.get('invoice_number')}`")
            hcol1.write(f"**PO Number:** `{inv_data.get('po_number')}`")
            hcol2.write(f"**Vendor:** {inv_data.get('vendor_name') or 'N/A'}")
            hcol2.write(f"**Invoice Date:** {inv_data.get('invoice_date')}")
            hcol3.write(f"**Currency:** {inv_data.get('currency')}")
            hcol3.write(f"**Total Amount:** {inv_data.get('total_amount', 0.0):,.2f}")
            hcol4.write(f"**Extraction:** `{inv_data.get('extraction_method')}`")
            hcol4.write(f"**Language:** `{inv_data.get('source_language')}` (Conf: {inv_data.get('translation_confidence', 1.0):.2f})")

            st.markdown("---")

            # Discrepancies Table
            st.markdown("#### ⚠️ Discrepancy Audit Log")
            discrepancies = inv_data.get("discrepancies", [])
            if not discrepancies:
                st.success("✅ Zero discrepancies detected. Invoice perfectly conforms to ERP records.")
            else:
                disc_df = pd.DataFrame(discrepancies)[["field_name", "invoice_value", "erp_value", "deviation_pct", "severity"]]
                disc_df.rename(columns={
                    "field_name": "Field / Finding",
                    "invoice_value": "Invoice Value",
                    "erp_value": "ERP Value",
                    "deviation_pct": "Deviation %",
                    "severity": "Severity"
                }, inplace=True)
                st.table(disc_df)

            # Line items table
            st.markdown("#### 📦 Extracted Line Items")
            line_items = inv_data.get("line_items", [])
            if line_items:
                line_df = pd.DataFrame(line_items)[["line_number", "item_code", "description", "quantity", "unit_price", "line_total"]]
                st.dataframe(line_df, use_container_width=True, hide_index=True)
            else:
                st.info("No line items extracted.")

            # Raw vs Translated text
            st.markdown("#### 📄 Document Text")
            tcol1, tcol2 = st.columns(2)
            with tcol1:
                st.caption("Raw Extracted Text (Pre-translation)")
                st.text_area("Raw Text", inv_data.get("raw_extracted_text", ""), height=200, disabled=True, label_visibility="collapsed")
            with tcol2:
                st.caption("English Translation & Normalized Content")
                st.text_area("Translated Text", inv_data.get("translated_text", ""), height=200, disabled=True, label_visibility="collapsed")

# ==============================================================================
# TAB 3: HUMAN-IN-THE-LOOP CORRECTIONS
# ==============================================================================
with tabs[2]:
    st.markdown("<div class='main-header'>Human-in-the-Loop Auditor Review</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Correct extracted values and trigger instant re-validation. Original extractions are never overwritten.</div>", unsafe_allow_html=True)

    if df_invoices.empty:
        st.warning("No invoices available.")
    else:
        inv_options = {
            f"{row['invoice_number'] or 'N/A'} - {row['vendor_name'] or 'Unknown'}": str(row['invoice_id'])
            for _, row in df_invoices.iterrows()
        }
        hil_selected = st.selectbox("Select Invoice to Review", list(inv_options.keys()), key="hil_select")
        hil_id = inv_options[hil_selected]
        hil_inv = get_invoice_full(hil_id)

        if hil_inv:
            st.markdown(f"**Current Recommendation:** `{hil_inv.get('recommendation')}` | **Validation Status:** `{hil_inv.get('validation_status')}`")

            # Correction Entry Form
            with st.form("correction_form"):
                st.markdown("##### ✏️ Submit Field Correction")
                ccol1, ccol2, ccol3 = st.columns(3)
                with ccol1:
                    field_choice = st.selectbox("Field Name", [
                        "po_number", "unit_price", "total_amount", "currency",
                        "invoice_number", "invoice_date", "vendor_id"
                    ])
                with ccol2:
                    current_val = str(hil_inv.get(field_choice, ""))
                    st.text_input("Current Extracted Value", value=current_val, disabled=True)
                with ccol3:
                    new_val = st.text_input("Corrected Value", placeholder="Enter verified value")

                auditor = st.text_input("Auditor Name", value="auditor_lead")
                submitted = st.form_submit_button("💾 Save Feedback & Re-Validate")

                if submitted:
                    if not new_val.strip():
                        st.error("Please enter a corrected value.")
                    else:
                        success = insert_human_feedback(
                            invoice_id=hil_id,
                            field_name=field_choice,
                            original_val=current_val,
                            corrected_val=new_val.strip(),
                            auditor_name=auditor,
                        )
                        if success:
                            st.success(f"Correction recorded in audit.human_feedback for '{field_choice}'. Triggering re-validation...")
                            reval_res = trigger_revalidate(hil_id)
                            st.info(f"Re-validation complete! New recommendation: **{reval_res.get('recommendation', '').upper()}**")
                            st.rerun()
                        else:
                            st.error("Failed to save feedback.")

            # Feedback History
            st.markdown("##### 📜 Audit Trail of Human Feedback")
            feedbacks = hil_inv.get("feedback", [])
            if not feedbacks:
                st.write("No manual corrections have been recorded for this invoice yet.")
            else:
                fb_df = pd.DataFrame(feedbacks)[["field_name", "original_value", "corrected_value", "corrected_by", "corrected_at", "revalidated"]]
                st.dataframe(fb_df, use_container_width=True, hide_index=True)

# ==============================================================================
# TAB 4: RAG ASSISTANT
# ==============================================================================
with tabs[3]:
    st.markdown("<div class='main-header'>RAG Intelligence Assistant</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Natural language Q&A evaluated on the RAG Triad (Context Relevance, Groundedness, Answer Relevance)</div>", unsafe_allow_html=True)

    # Scoping options
    qcol1, qcol2 = st.columns([3, 1])
    with qcol1:
        user_query = st.text_input(
            "Auditor Question",
            placeholder="e.g. Why was invoice INV-1004 flagged? What was the unit price variance for HafenLogistik?",
        )
    with qcol2:
        scope_choices = ["All Invoices"] + [f"{r['invoice_number']} ({str(r['invoice_id'])[:8]})" for _, r in df_invoices.iterrows()] if not df_invoices.empty else ["All Invoices"]
        selected_scope = st.selectbox("Query Scope", scope_choices)

    target_inv_id = None
    if selected_scope != "All Invoices":
        inv_match = selected_scope.split("(")[-1].replace(")", "").strip()
        for _, r in df_invoices.iterrows():
            if str(r["invoice_id"]).startswith(inv_match):
                target_inv_id = str(r["invoice_id"])
                break

    # Sample query chips
    st.caption("Quick Queries: "
               "[Why was INV-1004 flagged?] • "
               "[Which invoices have price discrepancies?] • "
               "[Summary of PO-1001 line items]")

    if st.button("🚀 Ask Auditor Assistant", use_container_width=True):
        if not user_query.strip():
            st.error("Please enter a question.")
        else:
            with st.spinner("Retrieving chunks and generating verified response..."):
                rag_res = query_rag_service(user_query, target_inv_id)

                if "error" in rag_res:
                    st.error(f"RAG query failed: {rag_res['error']}")
                else:
                    st.markdown("### 💬 Assistant Answer")
                    st.write(rag_res.get("answer", ""))

                    # RAG Triad Reflection Evaluation Box
                    scores = rag_res.get("scores", {})
                    avg_score = scores.get("average_score", 0.0)

                    st.markdown("#### ⚖️ RAG Triad Reflection Evaluation")
                    mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
                    mcol1.metric("Context Relevance", f"{scores.get('context_relevance', 0.0)*100:.1f}%")
                    mcol2.metric("Groundedness", f"{scores.get('groundedness', 0.0)*100:.1f}%")
                    mcol3.metric("Answer Relevance", f"{scores.get('answer_relevance', 0.0)*100:.1f}%")
                    mcol4.metric("Avg Triad Score", f"{avg_score*100:.1f}%")
                    mcol5.metric("Retries Needed", rag_res.get("retries", 0))

                    if avg_score >= 0.70:
                        st.success(f"✅ Quality Threshold Met: Score {avg_score:.2f} >= 0.70")
                    else:
                        st.warning(f"⚠️ Score {avg_score:.2f} < 0.70 (Retried {rag_res.get('retries', 0)} times)")

                    if rag_res.get("reasoning"):
                        st.caption(f"**Evaluator Critique:** {rag_res.get('reasoning')}")

                    # Retrieved Chunks Accordion
                    with st.expander(f"📚 Retrieved Context Chunks ({len(rag_res.get('chunks', []))})"):
                        for i, chunk in enumerate(rag_res.get("chunks", []), start=1):
                            st.markdown(f"**Chunk {i}:**")
                            st.code(chunk, language="text")

# ==============================================================================
# TAB 5: SYSTEM TOPOLOGY
# ==============================================================================
with tabs[4]:
    st.markdown("<div class='main-header'>Architecture & Service Topology</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Containerized Multi-Service Deployment Verification</div>", unsafe_allow_html=True)

    st.markdown("""
```mermaid
graph TD
    User([Auditor Browser]) -->|HTTP :8501| Streamlit[streamlit-ui :8501]
    Streamlit -->|HTTP :8000| Agent[agent :8000]
    Streamlit -.->|Read audit schema| Postgres[(PostgreSQL 16 :5432)]

    Agent -->|HTTP :8000| MockERP[mock-erp :8000 / host: 8001]
    Agent -.->|Read/Write audit & checkpoints| Postgres
    Agent -.->|Upsert & Search Vectors| Qdrant[(Qdrant :6333)]
    Agent -.->|Cache Prompts & Translations| Redis[(Redis 7 :6379)]

    MockERP -.->|Read erp schema only| Postgres
```
    """)

    st.markdown("### 🗄️ Database Schemas (Three Schemas in Single PostgreSQL)")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        st.info("**erp Schema**\n\n- `vendors`\n- `purchase_orders`\n- `po_line_items`\n- `sku_master`\n\n*Owned by mock-erp*")
    with sc2:
        st.info("**audit Schema**\n\n- `invoice_audit`\n- `invoice_line_items`\n- `discrepancies`\n- `human_feedback`\n\n*Written by agent, read by UI*")
    with sc3:
        st.info("**langgraph Schema**\n\n- `checkpoints`\n- `checkpoint_blobs`\n- `checkpoint_writes`\n\n*Working memory for agent graph*")

    st.markdown("### 🧪 6 Verification Checks Reference")
    st.markdown("""
    1. **Check 1 — Single-command startup:** `docker compose up --build -d` brings up all 6 services healthy.
    2. **Check 2 — End-to-end processing:** Ingests PDF/DOCX/PNG, translates, validates against mock-erp, produces report.
    3. **Check 3 — Persistence across restart:** `docker compose down` retains named volumes; audit & RAG intact.
    4. **Check 4 — Deliberate data loss:** `docker compose down -v` wipes volumes cleanly.
    5. **Check 5 — No secrets in images:** `docker history` proves no baked-in keys.
    6. **Check 6 — Service-name resolution:** Services communicate via Docker DNS names (`agent`, `mock-erp`, `postgres`, `qdrant`, `redis`).
    """)
