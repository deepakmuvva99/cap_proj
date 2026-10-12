"""Invoice Data Validation and ERP Business Validation nodes."""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import requests
from app.workflow.state import InvoiceState
from app.config import rules_config, settings

logger = logging.getLogger("agent.workflow.validation")


def invoice_data_validation_node(state: InvoiceState) -> InvoiceState:
    """Validates completeness, data types, and internal arithmetic against rules.yaml."""
    if state.get("already_audited"):
        return state

    missing_fields = []
    discrepancies = state.get("discrepancies", [])

    # 1. Header completeness check
    header_rules = rules_config.get("required_fields", {}).get("header", [
        "invoice_no", "invoice_date", "vendor_id", "currency", "total_amount"
    ])
    header_mapping = {
        "invoice_no": state.get("invoice_number"),
        "invoice_date": state.get("invoice_date"),
        "vendor_id": state.get("vendor_id"),
        "currency": state.get("currency"),
        "total_amount": state.get("total_amount"),
    }

    for rule_field in header_rules:
        val = header_mapping.get(rule_field)
        if val is None or val == "" or val == 0.0:
            missing_fields.append(f"header.{rule_field}")
            discrepancies.append({
                "field_name": f"Missing Header: {rule_field}",
                "invoice_value": "NULL",
                "erp_value": "REQUIRED",
                "deviation_pct": 100.0,
                "severity": "high",
            })

    # 2. Currency check
    accepted_currencies = rules_config.get("accepted_currencies", ["USD", "EUR", "INR", "GBP"])
    curr = (state.get("currency") or "").upper()
    if curr not in accepted_currencies:
        discrepancies.append({
            "field_name": "currency",
            "invoice_value": curr or "UNKNOWN",
            "erp_value": "/".join(accepted_currencies),
            "deviation_pct": 100.0,
            "severity": "critical",
        })

    # 3. Date check
    inv_date_str = state.get("invoice_date")
    if inv_date_str:
        try:
            inv_date = datetime.strptime(inv_date_str, "%Y-%m-%d").date()
            max_future_days = rules_config.get("date_validation", {}).get("max_future_days", 7)
            today = datetime.now().date()
            if inv_date > (today + timedelta(days=max_future_days)):
                discrepancies.append({
                    "field_name": "invoice_date",
                    "invoice_value": str(inv_date),
                    "erp_value": f"<= {today + timedelta(days=max_future_days)}",
                    "deviation_pct": 0.0,
                    "severity": "medium",
                })
        except Exception as exc:
            logger.debug("Date validation parse error: %s", exc)

    # 4. Line items completeness & arithmetic check
    line_items = state.get("line_items", [])
    tolerances = rules_config.get("tolerances", {})
    math_tolerance = tolerances.get("line_item_math_tolerance_percent", 1) / 100.0

    sum_line_totals = 0.0
    for idx, item in enumerate(line_items, start=1):
        qty = float(item.get("quantity") or item.get("qty") or 0.0)
        unit_price = float(item.get("unit_price") or 0.0)
        line_total = float(item.get("line_total") or item.get("total") or 0.0)

        # Completeness
        if not item.get("item_code"):
            missing_fields.append(f"line_{idx}.item_code")
        if not item.get("description"):
            missing_fields.append(f"line_{idx}.description")

        # Arithmetic: qty * unit_price vs line_total
        expected_line_total = qty * unit_price
        if line_total > 0:
            diff = abs(expected_line_total - line_total)
            if diff / line_total > math_tolerance:
                dev_pct = round((diff / line_total) * 100, 2)
                discrepancies.append({
                    "field_name": f"Line {idx} ({item.get('item_code')}) Math Mismatch",
                    "invoice_value": f"{line_total:.2f}",
                    "erp_value": f"{expected_line_total:.2f}",
                    "deviation_pct": dev_pct,
                    "severity": "medium",
                })

        sum_line_totals += line_total

    # 5. Header total vs line items total + tax
    inv_total = float(state.get("total_amount") or 0.0)
    tax_amt = float(state.get("tax_amount") or 0.0)
    expected_total = sum_line_totals + tax_amt

    if inv_total > 0 and len(line_items) > 0:
        total_diff = abs(expected_total - inv_total)
        if total_diff > 1.0:  # More than 1 currency unit
            dev_pct = round((total_diff / inv_total) * 100, 2)
            discrepancies.append({
                "field_name": "Invoice Total vs Line Sum Math",
                "invoice_value": f"{inv_total:.2f}",
                "erp_value": f"{expected_total:.2f}",
                "deviation_pct": dev_pct,
                "severity": "high",
            })

    state["missing_fields"] = missing_fields
    state["discrepancies"] = discrepancies
    logger.info("Invoice data validation complete: %d missing fields, %d discrepancies", len(missing_fields), len(discrepancies))
    return state


def business_validation_node(state: InvoiceState) -> InvoiceState:
    """Validates invoice against ERP records by querying the Mock ERP HTTP API."""
    if state.get("already_audited"):
        return state

    po_number = state.get("po_number")
    discrepancies = state.get("discrepancies", [])

    if not po_number:
        discrepancies.append({
            "field_name": "po_number",
            "invoice_value": "None",
            "erp_value": "Valid PO Number",
            "deviation_pct": 100.0,
            "severity": "critical",
        })
        state["discrepancies"] = discrepancies
        return state

    # Strict Service Boundary: Call Mock ERP via HTTP
    erp_url = f"{settings.ERP_SERVICE_URL}/po/{po_number}"
    logger.info("Calling Mock ERP service: GET %s", erp_url)

    try:
        resp = requests.get(erp_url, timeout=5)
        if resp.status_code == 404:
            discrepancies.append({
                "field_name": "Purchase Order",
                "invoice_value": po_number,
                "erp_value": "NOT FOUND",
                "deviation_pct": 100.0,
                "severity": "critical",
            })
            state["discrepancies"] = discrepancies
            return state
        resp.raise_for_status()
        erp_po = resp.json()
        state["erp_data"] = erp_po
    except Exception as exc:
        logger.error("Failed to query Mock ERP service (%s): %s", erp_url, exc)
        discrepancies.append({
            "field_name": "ERP Service Connection",
            "invoice_value": "Unavailable",
            "erp_value": "mock-erp:8000",
            "deviation_pct": 100.0,
            "severity": "critical",
        })
        state["discrepancies"] = discrepancies
        return state

    # 1. Compare Vendor ID
    erp_vendor_id = erp_po.get("vendor_id")
    inv_vendor_id = state.get("vendor_id")
    if inv_vendor_id and erp_vendor_id and inv_vendor_id.upper() != erp_vendor_id.upper():
        discrepancies.append({
            "field_name": "vendor_id",
            "invoice_value": inv_vendor_id,
            "erp_value": erp_vendor_id,
            "deviation_pct": 100.0,
            "severity": "high",
        })

    # 2. Compare Line Items
    erp_line_items = {item["item_code"].upper(): item for item in erp_po.get("line_items", [])}
    invoice_line_items = state.get("line_items", [])

    tolerances = rules_config.get("tolerances", {})
    price_tol_pct = tolerances.get("price_difference_percent", 5)  # ±5%
    qty_tol_pct = tolerances.get("quantity_difference_percent", 0)   # 0%

    for inv_item in invoice_line_items:
        item_code = (inv_item.get("item_code") or "").upper()
        if not item_code or item_code not in erp_line_items:
            discrepancies.append({
                "field_name": f"item_code.{item_code or 'UNKNOWN'}",
                "invoice_value": item_code or "Missing Code",
                "erp_value": f"Present in {po_number}",
                "deviation_pct": 100.0,
                "severity": "high",
            })
            continue

        erp_item = erp_line_items[item_code]

        # Check Currency
        inv_curr = (state.get("currency") or "").upper()
        erp_curr = (erp_item.get("currency") or "").upper()
        if inv_curr and erp_curr and inv_curr != erp_curr:
            discrepancies.append({
                "field_name": f"{item_code}.currency",
                "invoice_value": inv_curr,
                "erp_value": erp_curr,
                "deviation_pct": 100.0,
                "severity": "high",
            })

        # Check Quantity
        inv_qty = float(inv_item.get("quantity") or inv_item.get("qty") or 0.0)
        erp_qty = float(erp_item.get("qty", 0.0))
        if erp_qty > 0:
            qty_diff = abs(inv_qty - erp_qty)
            qty_dev_pct = (qty_diff / erp_qty) * 100.0
            if qty_dev_pct > qty_tol_pct:
                discrepancies.append({
                    "field_name": f"{item_code}.quantity",
                    "invoice_value": f"{inv_qty:.2f}",
                    "erp_value": f"{erp_qty:.2f}",
                    "deviation_pct": round(qty_dev_pct, 2),
                    "severity": "high" if qty_dev_pct > 10 else "medium",
                })

        # Check Unit Price
        inv_price = float(inv_item.get("unit_price") or 0.0)
        erp_price = float(erp_item.get("unit_price", 0.0))
        if erp_price > 0:
            price_diff = abs(inv_price - erp_price)
            price_dev_pct = (price_diff / erp_price) * 100.0
            if price_dev_pct > price_tol_pct:
                discrepancies.append({
                    "field_name": f"{item_code}.unit_price",
                    "invoice_value": f"{inv_price:.2f}",
                    "erp_value": f"{erp_price:.2f}",
                    "deviation_pct": round(price_dev_pct, 2),
                    "severity": "high" if price_dev_pct > 20 else "medium",
                })

    state["discrepancies"] = discrepancies
    logger.info("Business validation completed against %s with total %d discrepancies", po_number, len(discrepancies))
    return state
