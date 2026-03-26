from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .settings import DEFAULT_MAX_PAGINATION_LIMIT, DEFAULT_MAX_RETRIEVE_K


class HealthResponse(BaseModel):
    ok: bool


class RetrieveReq(BaseModel):
    goal: str = Field(min_length=1)
    op_key: Optional[str] = None
    role: Optional[str] = None
    tags: Optional[list[str]] = None
    k: int = Field(default=5, ge=1, le=DEFAULT_MAX_RETRIEVE_K)


class RecordItem(BaseModel):
    source: str = Field(min_length=1, max_length=24)
    op_key: Optional[str] = Field(default=None, max_length=256)
    title: Optional[str] = Field(default=None, max_length=256)
    content: str = Field(min_length=1)
    tags: Optional[list[str]] = None


class RecordBatch(BaseModel):
    items: list[RecordItem] = Field(min_length=1)


class LogReq(BaseModel):
    op_key: Optional[str] = Field(default=None, max_length=256)
    doc_ids: Optional[list[int]] = None
    status: Optional[int] = None
    latency_ms: Optional[int] = Field(default=None, ge=0)


class VoteReq(BaseModel):
    doc_id: int
    increment: int = Field(default=1, ge=1)


class SnippetOut(BaseModel):
    id: int
    source: str
    op_key: Optional[str]
    title: Optional[str]
    content: str


class RetrieveResponse(BaseModel):
    snippets: list[SnippetOut]


class RecordResponse(BaseModel):
    queued: list[int]


class LogResponse(BaseModel):
    logged: int


class VoteResponse(BaseModel):
    doc_id: int
    vote_count: int


class DeleteResponse(BaseModel):
    deleted: bool
    doc_id: int


class DocumentSummary(BaseModel):
    id: int
    source: str
    op_key: Optional[str]
    title: Optional[str]
    content: str
    tags: list[str]


class DocumentOut(DocumentSummary):
    pass


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]
    total: int
    limit: int = Field(ge=1, le=DEFAULT_MAX_PAGINATION_LIMIT)
    offset: int = Field(ge=0)


class ToolLogOut(BaseModel):
    id: int
    op_key: Optional[str]
    doc_id: Optional[int]
    status: Optional[int]
    latency_ms: Optional[int]
    created_at: Optional[datetime]


class LogsResponse(BaseModel):
    logs: list[ToolLogOut]
    total: int
    limit: int = Field(ge=1, le=DEFAULT_MAX_PAGINATION_LIMIT)
    offset: int = Field(ge=0)


class DocumentsStats(BaseModel):
    total: int
    by_source: dict[str, int]


class SearchesStats(BaseModel):
    total: int
    successful: int


class EngagementStats(BaseModel):
    total_votes: int
    active_boosts: int


class StatsResponse(BaseModel):
    documents: DocumentsStats
    queue: dict[str, int]
    searches: SearchesStats
    engagement: EngagementStats


class EmbeddingConfig(BaseModel):
    provider: str
    model: str
    dimension: int


class RetrievalConfig(BaseModel):
    rerank_weight: float
    retrieval_overfetch: int


class RankingConfig(BaseModel):
    vote_boost_weight: float
    usage_boost_weight: float
    usage_boost_ttl_days: int


class WorkerConfig(BaseModel):
    worker_poll_sec: float
    worker_batch: int
    worker_lease_sec: int
    cleanup_interval_sec: float


class SecurityConfig(BaseModel):
    auth_enabled: bool
    api_key_header: str


class CorsConfig(BaseModel):
    enabled: bool
    origins: list[str]


class ConfigResponse(BaseModel):
    embedding: EmbeddingConfig
    retrieval: RetrievalConfig
    ranking: RankingConfig
    workers: WorkerConfig
    security: SecurityConfig
    cors: CorsConfig
