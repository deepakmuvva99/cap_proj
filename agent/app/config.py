"""Configuration module for AI Invoice Auditor Agent."""
import os
from pathlib import Path
from typing import Dict, Any
import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service Environment
    APP_ENV: str = "production"
    LOG_LEVEL: str = "INFO"

    # PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "invoicedb"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"

    # Mock ERP Service
    ERP_SERVICE_URL: str = "http://mock-erp:8000"

    # Redis Cache
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_TTL_SECONDS: int = 86400  # 24 hours

    # Qdrant Vector Store
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "invoice_audit_rag"

    # AWS Bedrock
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_SESSION_TOKEN: str = ""

    # Bedrock Models (from requirements)
    MODEL_REASONING: str = "amazon.nova-lite-v1:0"
    MODEL_RAG_GENERATION: str = "cohere.command-r-plus-v1:0"
    MODEL_TRANSLATION: str = "cohere.command-r-plus-v1:0"
    MODEL_EMBEDDING: str = "amazon.titan-embed-text-v2:0"

    # Directories
    INCOMING_DIR: str = "/data/incoming"
    OUTPUT_REPORTS_DIR: str = "/app/outputs/reports"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


def load_yaml_config(filepath: str) -> Dict[str, Any]:
    """Helper to safely load YAML files from multiple possible relative paths."""
    candidates = [
        Path(filepath),
        Path(f"/app/{filepath}"),
        Path(f"./{filepath}"),
        Path(f"../{filepath}"),
        Path(f"../../{filepath}"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            with open(candidate, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


# Load rules and personas
rules_config = load_yaml_config("config/rules.yaml")
personas_config = load_yaml_config("config/personas.yaml")
