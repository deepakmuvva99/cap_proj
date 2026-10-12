"""Unit tests for RAG pipeline reflection and retry decision logic."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

from app.rag.graph import should_retry


class TestRAG(unittest.TestCase):

    def test_should_retry_pass_threshold(self):
        state = {
            "rag_triad_scores": {
                "context_relevance": 0.85,
                "groundedness": 0.80,
                "answer_relevance": 0.90,
                "average_score": 0.85,
            },
            "retry_count": 0,
            "max_retries": 3,
        }
        decision = should_retry(state)
        self.assertEqual(decision, "end")

    def test_should_retry_low_score_triggers_retry(self):
        state = {
            "rag_triad_scores": {
                "context_relevance": 0.50,
                "groundedness": 0.60,
                "answer_relevance": 0.55,
                "average_score": 0.55,
            },
            "retry_count": 1,
            "max_retries": 3,
        }
        decision = should_retry(state)
        self.assertEqual(decision, "retrieval")

    def test_should_retry_max_retries_reached(self):
        state = {
            "rag_triad_scores": {
                "context_relevance": 0.50,
                "groundedness": 0.60,
                "answer_relevance": 0.55,
                "average_score": 0.55,
            },
            "retry_count": 3,
            "max_retries": 3,
        }
        decision = should_retry(state)
        self.assertEqual(decision, "end")


if __name__ == "__main__":
    unittest.main()
