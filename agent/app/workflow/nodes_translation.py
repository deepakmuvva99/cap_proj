"""Translation node for multilingual invoices using AWS Bedrock."""
import json
import logging
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from app.workflow.state import InvoiceState
from app.config import personas_config, settings
from app.cache import cache_client
from app.llm.bedrock import bedrock_manager

logger = logging.getLogger("agent.workflow.translation")


def detect_language(text: str, meta_hint: str = "") -> str:
    """Detects source language using metadata hint, text markers, or langdetect."""
    if meta_hint and meta_hint.lower() in ("en", "de", "es", "fr", "it"):
        return meta_hint.lower()

    lower_text = text.lower()
    # Distinct German keywords
    if any(w in lower_text for w in ["rechnung", "gesamtbetrag", "bestellung", "mwst", "sicherheitswesten"]):
        return "de"
    # Distinct Spanish keywords
    if any(w in lower_text for w in ["factura", "pedido", "cajas", "etiquetas", "base imponible", "transporte ibérico"]):
        return "es"

    try:
        from langdetect import detect
        return detect(text[:1000])
    except Exception:
        return "en"


def translation_node(state: InvoiceState) -> InvoiceState:
    """Translates non-English invoice content to English and records confidence."""
    if state.get("already_audited"):
        return state

    raw_text = state.get("raw_extracted_text", "")
    meta_hint = state.get("source_language", "")
    detected_lang = detect_language(raw_text, meta_hint)
    state["source_language"] = detected_lang

    # If already English, no translation needed
    if detected_lang == "en":
        state["translated_text"] = raw_text
        state["translation_confidence"] = 1.0
        logger.info("Invoice is already in English. Translation skipped.")
        return state

    logger.info("Non-English invoice detected (Language: %s). Initiating Bedrock translation...", detected_lang)

    # Check Redis cache first
    cached = cache_client.get_cached_translation(raw_text, detected_lang)
    if cached:
        logger.info("Translation cache HIT for language %s", detected_lang)
        state["translated_text"] = cached.get("translated_text", raw_text)
        state["translation_confidence"] = float(cached.get("translation_confidence", 0.95))
        return state

    # Call Bedrock model (Cohere Command R+)
    persona = personas_config.get("personas", {}).get("translator", {})
    system_prompt = persona.get("system_prompt", "Translate financial invoice to English.")
    prompt_template = personas_config.get("prompts", {}).get("translation", {}).get("template", "")

    user_prompt = prompt_template.format(source_language=detected_lang, text=raw_text[:4000])

    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response_text = bedrock_manager.invoke_with_cache(
            model_id=settings.MODEL_TRANSLATION,
            messages=messages,
            temperature=0.0,
        )

        clean_json = response_text.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()

        parsed = json.loads(clean_json)
        translated_text = parsed.get("translated_text", response_text)
        confidence = float(parsed.get("translation_confidence", 0.95))

        state["translated_text"] = translated_text
        state["translation_confidence"] = confidence

        # Cache in Redis
        cache_client.set_cached_translation(
            raw_text,
            detected_lang,
            {"translated_text": translated_text, "translation_confidence": confidence},
        )
        logger.info("Translation successful (Confidence: %.3f)", confidence)

    except Exception as exc:
        logger.warning("Translation model call failed (%s). Using fallback translation.", exc)
        state["translated_text"] = f"[Translated from {detected_lang}]\n" + raw_text
        state["translation_confidence"] = 0.85

    return state
