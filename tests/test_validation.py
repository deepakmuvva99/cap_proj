"""Unit tests for business and data validation logic."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

from app.workflow.nodes_reporting import determine_recommendation


class TestValidation(unittest.TestCase):

    def test_determine_recommendation_approve(self):
        discrepancies = []
        missing_fields = []
        confidence = 0.98
        rec = determine_recommendation(discrepancies, missing_fields, confidence)
        self.assertEqual(rec, "approve")

    def test_determine_recommendation_review_on_discrepancy(self):
        discrepancies = [{"field_name": "unit_price", "severity": "medium", "deviation_pct": 8.0}]
        missing_fields = []
        confidence = 0.98
        rec = determine_recommendation(discrepancies, missing_fields, confidence)
        self.assertEqual(rec, "review")

    def test_determine_recommendation_review_on_low_confidence(self):
        discrepancies = []
        missing_fields = []
        confidence = 0.88  # < 0.95 threshold
        rec = determine_recommendation(discrepancies, missing_fields, confidence)
        self.assertEqual(rec, "review")

    def test_determine_recommendation_reject_on_critical(self):
        discrepancies = [{"field_name": "currency", "severity": "critical", "deviation_pct": 100.0}]
        missing_fields = []
        confidence = 1.0
        rec = determine_recommendation(discrepancies, missing_fields, confidence)
        self.assertEqual(rec, "reject")


if __name__ == "__main__":
    unittest.main()
