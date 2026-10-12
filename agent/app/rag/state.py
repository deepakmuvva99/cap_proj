"""State definition for LangGraph RAG pipeline."""
from typing import TypedDict, List, Dict, Any, Optional


class RAGState(TypedDict):
    query: str
    invoice_id_filter: Optional[str]
    vendor_filter: Optional[str]
    retrieved_chunks: List[Dict[str, Any]]
    context: str
    generated_answer: str
    rag_triad_scores: Dict[str, float]
    triad_reasoning: str
    retry_count: int
    max_retries: int
    final_answer: str
