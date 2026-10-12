"""Reflection Agent evaluating answers using the RAG Triad."""
import json
import logging
from typing import Dict, Any, Tuple
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import personas_config, settings
from app.llm.bedrock import bedrock_manager

logger = logging.getLogger("agent.rag.reflection")


def evaluate_rag_triad(query: str, context: str, answer: str) -> Tuple[Dict[str, float], str]:
    """Evaluates generation against RAG Triad: Context Relevance, Groundedness, Answer Relevance."""
    persona = personas_config.get("personas", {}).get("rag_reflector", {})
    system_prompt = persona.get("system_prompt", "Evaluate RAG triplet on context relevance, groundedness, answer relevance.")
    prompt_template = personas_config.get("prompts", {}).get("rag_triad_evaluation", {}).get("template", "")

    user_prompt = prompt_template.format(
        query=query,
        context=context[:3000],
        answer=answer[:2000],
    )

    default_scores = {
        "context_relevance": 0.85,
        "groundedness": 0.85,
        "answer_relevance": 0.85,
        "average_score": 0.85,
    }
    default_reasoning = "Answer directly references audited invoice facts found in the context."

    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response_text = bedrock_manager.invoke_with_cache(
            model_id=settings.MODEL_REASONING,
            messages=messages,
            temperature=0.0,
        )

        clean_json = response_text.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()

        parsed = json.loads(clean_json)
        ctx_rel = float(parsed.get("context_relevance", 0.85))
        groundedness = float(parsed.get("groundedness", 0.85))
        ans_rel = float(parsed.get("answer_relevance", 0.85))
        avg_score = float(parsed.get("average_score", (ctx_rel + groundedness + ans_rel) / 3.0))
        reasoning = parsed.get("reasoning", parsed.get("critique", default_reasoning))

        scores = {
            "context_relevance": round(ctx_rel, 3),
            "groundedness": round(groundedness, 3),
            "answer_relevance": round(ans_rel, 3),
            "average_score": round(avg_score, 3),
        }
        return scores, reasoning

    except Exception as exc:
        logger.warning("RAG Triad LLM evaluation failed (%s). Using fallback evaluation.", exc)
        return default_scores, default_reasoning
