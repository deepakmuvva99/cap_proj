"""Qdrant Vector Store Management."""
import uuid
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from app.config import settings

logger = logging.getLogger("agent.rag.vector_store")


class QdrantStore:
    def __init__(self):
        self.host = settings.QDRANT_HOST
        self.port = settings.QDRANT_PORT
        self.collection_name = settings.QDRANT_COLLECTION
        self._client: Optional[QdrantClient] = None

    def get_client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(host=self.host, port=self.port, timeout=10)
        return self._client

    def ensure_collection(self, vector_size: int = 1024) -> None:
        """Create the Qdrant collection if it doesn't already exist."""
        client = self.get_client()
        try:
            collections = client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                logger.info("Creating Qdrant collection '%s' with vector size %d", self.collection_name, vector_size)
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=vector_size,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
        except Exception as exc:
            logger.error("Error creating/checking Qdrant collection: %s", exc)

    def upsert_points(self, vectors: List[List[float]], payloads: List[Dict[str, Any]]) -> None:
        """Upsert vectors with rich metadata payloads to Qdrant."""
        client = self.get_client()
        points = []
        for vec, payload in zip(vectors, payloads):
            point_id = str(uuid.uuid4())
            points.append(qmodels.PointStruct(
                id=point_id,
                vector=vec,
                payload=payload,
            ))

        try:
            client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            logger.info("Successfully upserted %d points to Qdrant collection '%s'", len(points), self.collection_name)
        except Exception as exc:
            logger.error("Failed to upsert points to Qdrant: %s", exc)

    def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        invoice_id_filter: Optional[str] = None,
        vendor_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search similar vectors with optional invoice_id or vendor filters."""
        client = self.get_client()

        filter_conditions = []
        if invoice_id_filter:
            filter_conditions.append(
                qmodels.FieldCondition(
                    key="invoice_id",
                    match=qmodels.MatchValue(value=invoice_id_filter),
                )
            )
        if vendor_filter:
            filter_conditions.append(
                qmodels.FieldCondition(
                    key="vendor",
                    match=qmodels.MatchValue(value=vendor_filter),
                )
            )

        query_filter = None
        if filter_conditions:
            query_filter = qmodels.Filter(must=filter_conditions)

        try:
            results = client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
            )
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload,
                    "text": hit.payload.get("chunk_text", ""),
                    "source_type": hit.payload.get("source_type", ""),
                    "invoice_id": hit.payload.get("invoice_id", ""),
                }
                for hit in results
            ]
        except Exception as exc:
            logger.error("Qdrant search failed: %s", exc)
            return []


qdrant_store = QdrantStore()
