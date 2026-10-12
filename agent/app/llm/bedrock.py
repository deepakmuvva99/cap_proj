"""AWS Bedrock integration using langchain_aws ChatBedrockConverse and BedrockEmbeddings."""
import os
import json
import logging
import hashlib
from typing import Optional, List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from app.config import settings
from app.cache import cache_client

logger = logging.getLogger("agent.bedrock")

# Try importing langchain_aws components
try:
    from langchain_aws import ChatBedrockConverse, BedrockEmbeddings
    HAS_LANGCHAIN_AWS = True
except ImportError:
    try:
        from langchain_community.chat_models import BedrockChat as ChatBedrockConverse
        from langchain_community.embeddings import BedrockEmbeddings
        HAS_LANGCHAIN_AWS = True
    except ImportError:
        HAS_LANGCHAIN_AWS = False
        ChatBedrockConverse = None
        BedrockEmbeddings = None


class BedrockManager:
    """Manages AWS Bedrock models for Chat and Embeddings."""

    def __init__(self):
        self.region = settings.AWS_REGION
        self.has_credentials = bool(
            os.getenv("AWS_ACCESS_KEY_ID")
            or os.getenv("AWS_PROFILE")
            or os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
            or (settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY)
        )

    def get_chat_model(self, model_id: str, temperature: float = 0.0) -> Any:
        """Returns ChatBedrockConverse instance configured for the requested model."""
        if not HAS_LANGCHAIN_AWS or not self.has_credentials:
            logger.info("Using simulated LLM fallback for model: %s (AWS credentials not set or package unavailable)", model_id)
            return MockChatModel(model_id=model_id)

        try:
            extra_kwargs = {}
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                extra_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                extra_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
                if settings.AWS_SESSION_TOKEN:
                    extra_kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN

            chat = ChatBedrockConverse(
                model=model_id,
                region_name=self.region,
                temperature=temperature,
                **extra_kwargs,
            )
            return chat
        except Exception as exc:
            logger.warning("Failed to initialize ChatBedrockConverse (%s). Falling back to mock model.", exc)
            return MockChatModel(model_id=model_id)

    def get_embeddings(self) -> Any:
        """Returns BedrockEmbeddings instance for Qdrant indexing."""
        if not HAS_LANGCHAIN_AWS or not self.has_credentials:
            logger.info("Using simulated Embedding fallback (AWS credentials not set)")
            return MockEmbeddings()

        try:
            extra_kwargs = {}
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                extra_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                extra_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
                if settings.AWS_SESSION_TOKEN:
                    extra_kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN

            embeddings = BedrockEmbeddings(
                model_id=settings.MODEL_EMBEDDING,
                region_name=self.region,
                **extra_kwargs,
            )
            return embeddings
        except Exception as exc:
            logger.warning("Failed to initialize BedrockEmbeddings (%s). Falling back to mock embeddings.", exc)
            return MockEmbeddings()

    def invoke_with_cache(
        self,
        model_id: str,
        messages: List[BaseMessage],
        temperature: float = 0.0,
    ) -> str:
        """Invokes chat model with Redis caching of sha256(prompt)."""
        prompt_content = "\n".join([f"{type(m).__name__}: {m.content}" for m in messages])

        # 1. Check Redis cache
        cached = cache_client.get_cached_llm(prompt_content)
        if cached:
            logger.info("Cache HIT for prompt hash: %s", hashlib.sha256(prompt_content.encode()).hexdigest()[:8])
            return cached

        # 2. Invoke LLM
        model = self.get_chat_model(model_id, temperature=temperature)
        response = model.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)

        # 3. Store in Redis cache
        cache_client.set_cached_llm(prompt_content, content)
        return content


class MockChatModel:
    """Mock fallback LLM providing deterministic, domain-specific responses when offline."""

    def __init__(self, model_id: str):
        self.model_id = model_id

    def invoke(self, messages: List[BaseMessage]) -> Any:
        prompt_text = "\n".join([str(m.content) for m in messages]).lower()

        # Mocking translation
        if "translate the following invoice" in prompt_text or "deutsch" in prompt_text or "español" in prompt_text:
            return MockResponse(json.dumps({
                "translated_text": "Translated Invoice:\nPurchase Order: PO-1004\nSupplier: HafenLogistik GmbH\nDescription: Transport Crates (40 units @ 25.00 EUR), Safety Vests (60 units @ 10.00 EUR)\nTotal: 1,760.00 EUR",
                "translation_confidence": 0.98,
                "translated_line_items": [
                    {"item_code": "SKU-301", "description": "Transport Crates"},
                    {"item_code": "SKU-302", "description": "Safety Vests"}
                ]
            }))

        # Mocking RAG reflection
        if "rag triad" in prompt_text or "context relevance" in prompt_text:
            return MockResponse(json.dumps({
                "context_relevance": 0.95,
                "groundedness": 0.92,
                "answer_relevance": 0.94,
                "average_score": 0.937,
                "reasoning": "Retrieved chunks contain direct invoice references; answer accurately reflects audited outcome without hallucination."
            }))

        # Mocking extraction
        if "extract all invoice details" in prompt_text:
            return MockResponse(json.dumps({
                "invoice_number": "INV-1001",
                "invoice_date": "2025-03-14",
                "vendor_id": "VEND-001",
                "vendor_name": "Global Logistics Ltd",
                "po_number": "PO-1001",
                "currency": "USD",
                "subtotal": 1410.0,
                "tax_amount": 141.0,
                "total_amount": 1551.0,
                "source_language": "en",
                "line_items": [
                    {"line_number": 1, "item_code": "SKU-001", "description": "Pallet Wrapping Film", "quantity": 50.0, "unit_price": 12.0, "line_total": 600.0},
                    {"line_number": 2, "item_code": "SKU-002", "description": "Industrial Gloves", "quantity": 120.0, "unit_price": 3.0, "line_total": 360.0},
                    {"line_number": 3, "item_code": "SKU-003", "description": "Safety Helmets", "quantity": 30.0, "unit_price": 15.0, "line_total": 450.0}
                ]
            }))

        # Mocking general RAG answer
        return MockResponse("Based on the audited invoice records, invoice details have been verified against purchase orders with recorded discrepancies and line item validations.")


class MockResponse:
    def __init__(self, content: str):
        self.content = content


class MockEmbeddings:
    """Mock deterministic embeddings generator for vector indexing testing."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._hash_vector(text)

    def _hash_vector(self, text: str, dim: int = 1024) -> List[float]:
        # Generate pseudo-random vector with fixed seed from text hash
        val = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        vec = [((val >> (i % 64)) & 0xFF) / 255.0 for i in range(dim)]
        # Normalize
        norm = sum(x**2 for x in vec) ** 0.5 or 1.0
        return [round(x / norm, 6) for x in vec]


bedrock_manager = BedrockManager()
