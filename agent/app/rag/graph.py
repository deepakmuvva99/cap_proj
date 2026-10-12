"""LangGraph-based RAG pipeline with Reflection and RAG Triad retry loop."""
import logging
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from app.rag.state import RAGState
from app.rag.vector_store import qdrant_store
from app.rag.reflection import evaluate_rag_triad
from app.llm.bedrock import bedrock_manager
from app.config import personas_config, settings

logger = logging.getLogger("agent.rag.graph")


def retrieval_agent(state: RAGState) -> RAGState:
    """Retrieves relevant chunks from Qdrant with optional invoice_id filter."""
    query = state["query"]
    k = 4 + (state.get("retry_count", 0) * 2)  # Expand k on retries

    embeddings_model = bedrock_manager.get_embeddings()
    query_vector = embeddings_model.embed_query(query)

    hits = qdrant_store.search(
        query_vector=query_vector,
        limit=k,
        invoice_id_filter=state.get("invoice_id_filter"),
        vendor_filter=state.get("vendor_filter"),
    )
    state["retrieved_chunks"] = hits
    logger.info("Retrieved %d chunks for query '%s' (retry %d)", len(hits), query[:30], state.get("retry_count", 0))
    return state


def augmentation_agent(state: RAGState) -> RAGState:
    """Reranks and formats retrieved chunks into structured context."""
    hits = state.get("retrieved_chunks", [])
    if not hits:
        state["context"] = "No relevant invoice or report records found in the index."
        return state

    context_parts = []
    for idx, hit in enumerate(hits, start=1):
        payload = hit.get("payload", {})
        src = payload.get("source_type", "chunk")
        inv = payload.get("invoice_number", "N/A")
        text = hit.get("text", "")
        context_parts.append(f"--- Document Chunk {idx} [Invoice: {inv}, Source: {src}] ---\n{text}")

    state["context"] = "\n\n".join(context_parts)
    return state


def generation_agent(state: RAGState) -> RAGState:
    """Answers user's question using Cohere Command R+ via ChatBedrockConverse."""
    query = state["query"]
    context = state.get("context", "")

    persona = personas_config.get("personas", {}).get("rag_assistant", {})
    system_prompt = persona.get("system_prompt", "Answer questions factually using the provided invoice context.")

    user_prompt = f"""
Audited Records Context:
{context}

Auditor Question:
{query}

Please answer the auditor's question accurately based only on the above context.
Cite specific invoice numbers, dates, amounts, and discrepancy statuses.
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    answer = bedrock_manager.invoke_with_cache(
        model_id=settings.MODEL_RAG_GENERATION,
        messages=messages,
        temperature=0.1,
    )

    state["generated_answer"] = answer
    return state


def reflection_agent(state: RAGState) -> RAGState:
    """Evaluates the generation against the RAG Triad."""
    query = state["query"]
    context = state.get("context", "")
    answer = state.get("generated_answer", "")

    scores, reasoning = evaluate_rag_triad(query, context, answer)
    state["rag_triad_scores"] = scores
    state["triad_reasoning"] = reasoning

    avg_score = scores.get("average_score", 0.8)
    logger.info("RAG Triad Evaluation: Average=%.3f (ContextRel=%.2f, Groundedness=%.2f, AnsRel=%.2f)",
                avg_score, scores.get("context_relevance", 0), scores.get("groundedness", 0), scores.get("answer_relevance", 0))

    if avg_score >= 0.70:
        state["final_answer"] = answer
    else:
        state["retry_count"] = state.get("retry_count", 0) + 1
        if state["retry_count"] >= state.get("max_retries", 3):
            state["final_answer"] = answer + f"\n\n*[Note: Answer evaluated with caution (RAG Triad Score: {avg_score:.2f})]*"

    return state


def should_retry(state: RAGState) -> Literal["retrieval", "end"]:
    """Conditional edge deciding whether to retry retrieval or accept answer."""
    scores = state.get("rag_triad_scores", {})
    avg_score = scores.get("average_score", 0.8)
    retries = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if avg_score >= 0.70:
        return "end"
    if retries < max_retries:
        logger.info("Average score %.2f < 0.70. Retrying RAG retrieval (Attempt %d/%d)...", avg_score, retries + 1, max_retries)
        return "retrieval"
    return "end"


def build_rag_graph():
    """Builds and compiles the LangGraph RAG pipeline."""
    graph = StateGraph(RAGState)

    graph.add_node("retrieval", retrieval_agent)
    graph.add_node("augmentation", augmentation_agent)
    graph.add_node("generation", generation_agent)
    graph.add_node("reflection", reflection_agent)

    graph.set_entry_point("retrieval")
    graph.add_edge("retrieval", "augmentation")
    graph.add_edge("augmentation", "generation")
    graph.add_edge("generation", "reflection")

    graph.add_conditional_edges(
        "reflection",
        should_retry,
        {
            "retrieval": "retrieval",
            "end": END,
        },
    )

    return graph.compile()


rag_pipeline = build_rag_graph()


def query_rag(query: str, invoice_id: Optional[str] = None, vendor: Optional[str] = None) -> Dict[str, Any]:
    """Top-level entrypoint for answering questions via the RAG pipeline."""
    initial_state: RAGState = {
        "query": query,
        "invoice_id_filter": invoice_id,
        "vendor_filter": vendor,
        "retrieved_chunks": [],
        "context": "",
        "generated_answer": "",
        "rag_triad_scores": {},
        "triad_reasoning": "",
        "retry_count": 0,
        "max_retries": 3,
        "final_answer": "",
    }
    result = rag_pipeline.invoke(initial_state)
    return {
        "query": query,
        "answer": result.get("final_answer") or result.get("generated_answer"),
        "scores": result.get("rag_triad_scores", {}),
        "reasoning": result.get("triad_reasoning", ""),
        "retries": result.get("retry_count", 0),
        "chunks": [c.get("text", "") for c in result.get("retrieved_chunks", [])],
    }
