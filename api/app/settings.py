from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


EMBEDDING_MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

DEFAULT_DATABASE_URL = "postgresql+psycopg://ctx:ctx@db:5432/ctx"
DEFAULT_MAX_RETRIEVE_K = 50
DEFAULT_MAX_PAGINATION_LIMIT = 200


def embedding_dimension_for_model(model: str) -> int:
    try:
        return EMBEDDING_MODEL_DIMENSIONS[model]
    except KeyError as exc:  # pragma: no cover
        known = ", ".join(sorted(EMBEDDING_MODEL_DIMENSIONS))
        raise ValueError(
            f"Unsupported EMBEDDING_MODEL={model!r}. Known models: {known}"
        ) from exc


@dataclass(frozen=True)
class Settings:
    database_url: str
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    rerank_weight: float
    retrieval_overfetch: int
    vote_boost_weight: float
    usage_boost_weight: float
    usage_boost_ttl_days: int
    worker_poll_sec: float
    worker_batch: int
    worker_lease_sec: int
    cleanup_interval_sec: float
    cuecard_api_key: Optional[str]
    api_key_header: str
    cors_origins: tuple[str, ...]
    max_retrieve_k: int = DEFAULT_MAX_RETRIEVE_K
    max_pagination_limit: int = DEFAULT_MAX_PAGINATION_LIMIT


def load_settings() -> Settings:
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()
    if embedding_provider not in {"local", "openai"}:
        raise ValueError(
            f"Unsupported EMBEDDING_PROVIDER={embedding_provider!r}. Use 'local' or 'openai'."
        )

    embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip()
    embedding_dimension = embedding_dimension_for_model(embedding_model)

    retrieval_overfetch = int(os.getenv("RETRIEVAL_OVERFETCH", "8"))
    worker_batch = int(os.getenv("WORKER_BATCH", "32"))
    worker_lease_sec = int(os.getenv("WORKER_LEASE_SEC", "300"))
    usage_boost_ttl_days = int(os.getenv("USAGE_BOOST_TTL_DAYS", "14"))

    if retrieval_overfetch < 0:
        raise ValueError("RETRIEVAL_OVERFETCH must be >= 0")
    if worker_batch <= 0:
        raise ValueError("WORKER_BATCH must be > 0")
    if worker_lease_sec <= 0:
        raise ValueError("WORKER_LEASE_SEC must be > 0")
    if usage_boost_ttl_days <= 0:
        raise ValueError("USAGE_BOOST_TTL_DAYS must be > 0")

    cors_origins_raw = os.getenv("CORS_ORIGINS", "").strip()
    cors_origins = tuple(
        origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()
    )

    api_key = os.getenv("CUECARD_API_KEY")

    return Settings(
        database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        rerank_weight=float(os.getenv("RERANK_WEIGHT", "0.1")),
        retrieval_overfetch=retrieval_overfetch,
        vote_boost_weight=float(os.getenv("VOTE_BOOST_WEIGHT", "1.0")),
        usage_boost_weight=float(os.getenv("USAGE_BOOST_WEIGHT", "0.01")),
        usage_boost_ttl_days=usage_boost_ttl_days,
        worker_poll_sec=float(os.getenv("WORKER_POLL_SEC", "2")),
        worker_batch=worker_batch,
        worker_lease_sec=worker_lease_sec,
        cleanup_interval_sec=float(os.getenv("CLEANUP_INTERVAL_SEC", "3600")),
        cuecard_api_key=api_key.strip() if api_key and api_key.strip() else None,
        api_key_header=os.getenv("API_KEY_HEADER", "X-API-Key").strip() or "X-API-Key",
        cors_origins=cors_origins,
    )
