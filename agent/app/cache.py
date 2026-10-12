"""Redis caching layer for AI Invoice Auditor."""
import hashlib
import json
import logging
from typing import Optional, Any
import redis
from app.config import settings

logger = logging.getLogger("agent.cache")


class RedisCache:
    def __init__(self):
        self._client: Optional[redis.Redis] = None

    def get_client(self) -> Optional[redis.Redis]:
        if self._client is None:
            try:
                self._client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
                self._client.ping()
            except Exception as exc:
                logger.warning("Redis connection unavailable (%s). Cache disabled.", exc)
                self._client = None
        return self._client

    def _hash_key(self, prefix: str, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{prefix}:{digest}"

    def get_cached_llm(self, prompt: str) -> Optional[str]:
        client = self.get_client()
        if not client:
            return None
        try:
            key = self._hash_key("llm", prompt)
            return client.get(key)
        except Exception as exc:
            logger.debug("Redis read error: %s", exc)
            return None

    def set_cached_llm(self, prompt: str, response: str, ttl: int = settings.REDIS_TTL_SECONDS) -> None:
        client = self.get_client()
        if not client:
            return
        try:
            key = self._hash_key("llm", prompt)
            client.setex(key, ttl, response)
        except Exception as exc:
            logger.debug("Redis write error: %s", exc)

    def get_cached_translation(self, text: str, source_lang: str) -> Optional[Dict[str, Any]]:
        client = self.get_client()
        if not client:
            return None
        try:
            key = self._hash_key(f"trans:{source_lang}", text)
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("Redis translation cache read error: %s", exc)
            return None

    def set_cached_translation(self, text: str, source_lang: str, result: Dict[str, Any], ttl: int = settings.REDIS_TTL_SECONDS) -> None:
        client = self.get_client()
        if not client:
            return
        try:
            key = self._hash_key(f"trans:{source_lang}", text)
            client.setex(key, ttl, json.dumps(result))
        except Exception as exc:
            logger.debug("Redis translation cache write error: %s", exc)


cache_client = RedisCache()
