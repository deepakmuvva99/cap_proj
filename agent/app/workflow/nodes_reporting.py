"""Reporting node for generating HTML/JSON reports and persisting to PostgreSQL."""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from app.workflow.state import InvoiceState
from app.config import rules_config, settings
from app.db import save_invoice_audit, save_invoice_line_items, save_discrepancies

logger = logging.getLogger("agent.workflow.reporting")


def determine_recommendation(discrepancies: List[Dict[str, Any]], missing_fields: List[str], translation_confidence: float) -> str:
    """Determines audit recommendation: approve, review, or reject."""
    # Check for critical discrepancies
    has_critical = any(d.get("severity") == "critical" for d in discrepancies)
    has_high = any(d.get("severity") == "high" for d in discrepancies)
    has_medium = any(d.get("severity") == "medium" for d in discrepancies)

    if has_critical:
        return "reject"
    if has_high or has_medium or missing_fields:
        return "review"
    if translation_confidence < 0.95:
        return "review"
    return "approve"


def generate_html_report(state: InvoiceState, output_path: Path) -> str:
    """Generates a human-readable styled HTML audit report."""
    rec = state.get("recommendation", "review").upper()
    badge_colors = {
        "APPROVE": "#10B981", # Green
        "REVIEW": "#F59E0B",  # Amber
        "REJECT": "#EF4444",  # Red
    }
    badge_color = badge_colors.get(rec, "#6B7280")

    discrepancies_rows = ""
    for d in state.get("discrepancies", []):
        discrepancies_rows += f"""
        <tr>
            <td><strong>{d.get('field_name')}</strong></td>
            <td><code>{d.get('invoice_value')}</code></td>
            <td><code>{d.get('erp_value')}</code></td>
            <td>{d.get('deviation_pct', 0):.2f}%</td>
            <td><span class="severity-badge sev-{d.get('severity', 'medium')}">{d.get('severity', 'medium').upper()}</span></td>
        </tr>
        """

    line_items_rows = ""
    for item in state.get("line_items", []):
        line_items_rows += f"""
        <tr>
            <td>{item.get('line_number', '-')}</td>
            <td><strong>{item.get('item_code', '-')}</strong></td>
            <td>{item.get('description', '-')}</td>
            <td>{float(item.get('quantity') or item.get('qty', 0)):.2f}</td>
            <td>{float(item.get('unit_price', 0)):.2f}</td>
            <td>{float(item.get('line_total') or item.get('total', 0)):.2f} {state.get('currency', 'USD')}</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Audit Report: {state.get('invoice_number', 'Invoice')}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f8fafc;
            color: #1e293b;
            margin: 0;
            padding: 30px;
        }}
        .report-card {{
            max-width: 950px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
            padding: 36px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 20px;
            margin-bottom: 24px;
        }}
        .header h1 {{ margin: 0; font-size: 26px; color: #0f172a; }}
        .header .meta {{ color: #64748b; font-size: 14px; margin-top: 4px; }}
        .rec-badge {{
            background-color: {badge_color};
            color: white;
            font-size: 16px;
            font-weight: 700;
            padding: 8px 18px;
            border-radius: 9999px;
            letter-spacing: 0.05em;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 28px;
        }}
        .stat-box {{
            background: #f1f5f9;
            padding: 16px;
            border-radius: 8px;
        }}
        .stat-box .label {{ font-size: 12px; color: #64748b; text-transform: uppercase; font-weight: 600; }}
        .stat-box .val {{ font-size: 18px; font-weight: 700; color: #0f172a; margin-top: 4px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            margin-bottom: 28px;
            font-size: 14px;
        }}
        th, td {{
            text-align: left;
            padding: 10px 14px;
            border-bottom: 1px solid #e2e8f0;
        }}
        th {{ background: #f8fafc; color: #475569; font-weight: 600; text-transform: uppercase; font-size: 12px; }}
        .severity-badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            color: white;
        }}
        .sev-critical {{ background-color: #ef4444; }}
        .sev-high {{ background-color: #f97316; }}
        .sev-medium {{ background-color: #f59e0b; }}
        .sev-low {{ background-color: #3b82f6; }}
        .section-title {{ font-size: 18px; font-weight: 700; color: #1e293b; margin-top: 24px; margin-bottom: 8px; }}
    </style>
</head>
<body>
    <div class="report-card">
        <div class="header">
            <div>
                <h1>AI Invoice Audit Report</h1>
                <div class="meta">Invoice: <strong>{state.get('invoice_number', 'N/A')}</strong> | File: {state.get('file_name', 'N/A')} | Audited: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
            <div>
                <span class="rec-badge">{rec}</span>
            </div>
        </div>

        <div class="grid">
            <div class="stat-box">
                <div class="label">Vendor</div>
                <div class="val">{state.get('vendor_name') or state.get('vendor_id') or 'N/A'}</div>
            </div>
            <div class="stat-box">
                <div class="label">PO Number</div>
                <div class="val">{state.get('po_number') or 'N/A'}</div>
            </div>
            <div class="stat-box">
                <div class="label">Total Amount</div>
                <div class="val">{state.get('total_amount', 0.0):,.2f} {state.get('currency', 'USD')}</div>
            </div>
            <div class="stat-box">
                <div class="label">Translation Conf.</div>
                <div class="val">{state.get('translation_confidence', 1.0) * 100:.1f}% ({state.get('source_language', 'en').upper()})</div>
            </div>
        </div>

        <div class="section-title">Audit Discrepancies & Findings ({len(state.get('discrepancies', []))})</div>
        {'<p style="color: #10B981; font-weight: 500;">No discrepancies detected. Invoice matches ERP records.</p>' if not state.get('discrepancies') else f'''
        <table>
            <thead>
                <tr>
                    <th>Field / Anomaly</th>
                    <th>Invoice Value</th>
                    <th>ERP Value</th>
                    <th>Deviation</th>
                    <th>Severity</th>
                </tr>
            </thead>
            <tbody>
                {discrepancies_rows}
            </tbody>
        </table>
        '''}

        <div class="section-title">Invoice Line Items</div>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Item Code</th>
                    <th>Description</th>
                    <th>Qty</th>
                    <th>Unit Price</th>
                    <th>Line Total</th>
                </tr>
            </thead>
            <tbody>
                {line_items_rows}
            </tbody>
        </table>

        <div class="section-title">Raw Extracted Text</div>
        <pre style="background: #f1f5f9; padding: 14px; border-radius: 8px; font-size: 12px; overflow-x: auto; max-height: 200px;">{state.get('raw_extracted_text', '')}</pre>
    </div>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    return str(output_path.resolve())


def reporting_node(state: InvoiceState) -> InvoiceState:
    """Generates reports and writes the final audit outcome to PostgreSQL."""
    if state.get("already_audited"):
        return state

    discrepancies = state.get("discrepancies", [])
    missing_fields = state.get("missing_fields", [])
    confidence = float(state.get("translation_confidence", 1.0))

    recommendation = determine_recommendation(discrepancies, missing_fields, confidence)
    state["recommendation"] = recommendation
    state["validation_status"] = "passed" if recommendation == "approve" else ("failed" if recommendation == "reject" else "partial")

    # Ensure output reports directory exists
    reports_dir = Path(settings.OUTPUT_REPORTS_DIR)
    reports_dir.mkdir(parents=True, exist_ok=True)

    inv_id = state["invoice_id"]
    json_path = reports_dir / f"{inv_id}.json"
    html_path = reports_dir / f"{inv_id}.html"

    # Write JSON report
    report_dict = {
        "invoice_id": inv_id,
        "file_name": state.get("file_name"),
        "file_checksum": state.get("file_checksum"),
        "extraction_method": state.get("extraction_method"),
        "source_language": state.get("source_language"),
        "translation_confidence": state.get("translation_confidence"),
        "invoice_number": state.get("invoice_number"),
        "vendor_name": state.get("vendor_name"),
        "vendor_id": state.get("vendor_id"),
        "po_number": state.get("po_number"),
        "invoice_date": state.get("invoice_date"),
        "currency": state.get("currency"),
        "total_amount": state.get("total_amount"),
        "subtotal": state.get("subtotal"),
        "tax_amount": state.get("tax_amount"),
        "validation_status": state.get("validation_status"),
        "recommendation": state.get("recommendation"),
        "discrepancies": discrepancies,
        "line_items": state.get("line_items", []),
        "processed_at": datetime.now().isoformat(),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)

    state["json_report_path"] = str(json_path.resolve())

    # Write HTML report
    state["html_report_path"] = generate_html_report(state, html_path)

    # Persist to PostgreSQL audit schema (System of Record)
    try:
        save_invoice_audit(state)
        save_invoice_line_items(inv_id, state.get("line_items", []))
        save_discrepancies(inv_id, discrepancies)
        logger.info("Successfully persisted audit record for invoice %s to PostgreSQL", inv_id)
    except Exception as exc:
        logger.error("Failed to persist audit to PostgreSQL: %s", exc)
        state["errors"].append(f"PostgreSQL persistence error: {str(exc)}")

    return state
