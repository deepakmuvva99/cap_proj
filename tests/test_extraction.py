"""Unit tests for document extractors and parsing logic."""
import os
import unittest
from pathlib import Path
import sys

# Add agent app to path
sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

from app.extractors.parser_utils import clean_number, extract_currency, parse_date_string, heuristic_parse


class TestExtraction(unittest.TestCase):

    def test_clean_number(self):
        self.assertEqual(clean_number("$1,250.50"), 1250.50)
        self.assertEqual(clean_number("€ 25,00"), 25.00)
        self.assertEqual(clean_number("₹8000.00"), 8000.00)
        self.assertEqual(clean_number("1.250,50"), 1250.50)
        self.assertEqual(clean_number(""), 0.0)

    def test_extract_currency(self):
        self.assertEqual(extract_currency("Total: $500.00"), "USD")
        self.assertEqual(extract_currency("Gesamtbetrag: 1200,00 €"), "EUR")
        self.assertEqual(extract_currency("Payment in INR"), "INR")
        self.assertEqual(extract_currency("Amount: £45.00"), "GBP")

    def test_parse_date(self):
        self.assertEqual(parse_date_string("2025-03-14"), "2025-03-14")
        self.assertEqual(parse_date_string("14/03/2025"), "2025-03-14")
        self.assertEqual(parse_date_string("14.03.2025"), "2025-03-14")
        self.assertEqual(parse_date_string("March 14, 2025"), "2025-03-14")

    def test_heuristic_parse(self):
        sample_invoice_text = """
        INVOICE
        Invoice Number: INV-1001
        Date: 2025-03-14
        Purchase Order: PO-1001
        Vendor: Global Logistics Ltd
        Currency: USD
        
        Line Items:
        SKU-001 Pallet Wrapping Film 50 $12.00 $600.00
        SKU-002 Industrial Gloves 120 $3.00 $360.00
        SKU-003 Safety Helmets 30 $15.00 $450.00
        
        Subtotal: $1410.00
        Tax (10%): $141.00
        Total Amount: $1551.00
        """
        parsed = heuristic_parse(sample_invoice_text)
        self.assertEqual(parsed["invoice_number"], "INV-1001")
        self.assertEqual(parsed["po_number"], "PO-1001")
        self.assertEqual(parsed["vendor_id"], "VEND-001")
        self.assertEqual(parsed["currency"], "USD")
        self.assertEqual(parsed["total_amount"], 1551.00)
        self.assertEqual(len(parsed["line_items"]), 3)
        self.assertEqual(parsed["line_items"][0]["item_code"], "SKU-001")
        self.assertEqual(parsed["line_items"][0]["quantity"], 50.0)


if __name__ == "__main__":
    unittest.main()
