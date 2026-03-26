from __future__ import annotations

import datetime as dt
import secrets
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .db.repo import (
    delete_document,
    enqueue_items,
    get_document,
    get_statistics,
    list_documents,
    log_tool_use,
    query_tool_logs,
    search_snippets,
    vote_for_doc,
)
from .db.session import dispose_engines, session_scope, verify_database_compatibility
from .embedding import embed_texts
from .schemas import (
    ConfigResponse,
    CorsConfig,
    DeleteResponse,
    DocumentListResponse,
    DocumentOut,
    DocumentSummary,
    EmbeddingConfig,
    HealthResponse,
    LogReq,
    LogResponse,
    LogsResponse,
    RankingConfig,
    RecordBatch,
    RecordResponse,
    RetrieveReq,
    RetrieveResponse,
    RetrievalConfig,
    SecurityConfig,
    SnippetOut,
    StatsResponse,
    VoteReq,
    VoteResponse,
    WorkerConfig,
)
from .settings import Settings, load_settings


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await verify_database_compatibility(settings)
        try:
            yield
        finally:
            await dispose_engines()

    async def api_key_auth(request: Request):
        if not settings.cuecard_api_key:
            return
        if request.url.path == "/health":
            return

        provided = request.headers.get(settings.api_key_header)
        if provided is None or not secrets.compare_digest(provided, settings.cuecard_api_key):
            raise HTTPException(status_code=401, detail="Unauthorized")

    app = FastAPI(
        title="CueCard",
        version="0.2",
        dependencies=[Depends(api_key_auth)],
        lifespan=lifespan,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(ok=True)

    @app.post("/retrieve", response_model=RetrieveResponse)
    async def retrieve(req: RetrieveReq) -> RetrieveResponse:
        query_text = " ".join([value for value in [req.goal, req.role, req.op_key] if value])
        qvec = embed_texts([query_text], settings=settings)[0]
        async with session_scope(settings) as session:
            rows = await search_snippets(
                session,
                qvec,
                req.op_key,
                req.tags,
                req.k,
                settings=settings,
            )

        max_chars = 1200
        return RetrieveResponse(
            snippets=[
                SnippetOut(
                    id=row.id,
                    source=row.source,
                    op_key=row.op_key,
                    title=row.title,
                    content=(row.content or "")[:max_chars],
                )
                for row in rows
            ]
        )

    @app.post("/record", response_model=RecordResponse, status_code=202)
    async def record(batch: RecordBatch) -> RecordResponse:
        payload = [
            {
                "source": item.source,
                "op_key": item.op_key,
                "title": item.title,
                "content": item.content,
                "tags": item.tags or [],
            }
            for item in batch.items
        ]
        async with session_scope(settings) as session:
            queued = await enqueue_items(session, payload)
        return RecordResponse(queued=queued)

    @app.post("/log", response_model=LogResponse)
    async def log(req: LogReq) -> LogResponse:
        async with session_scope(settings) as session:
            logged = await log_tool_use(
                session,
                req.op_key,
                req.doc_ids or [],
                req.status,
                req.latency_ms,
            )
        return LogResponse(logged=logged)

    @app.get("/logs", response_model=LogsResponse)
    async def get_logs(
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        op_key: Optional[str] = None,
        doc_id: Optional[int] = None,
        status_min: Optional[int] = None,
        status_max: Optional[int] = None,
        limit: int = Query(default=100, ge=1, le=settings.max_pagination_limit),
        offset: int = Query(default=0, ge=0),
    ) -> LogsResponse:
        def parse_ts(value: Optional[str]) -> Optional[dt.datetime]:
            if not value:
                return None
            try:
                parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid timestamp format; use ISO 8601",
                ) from exc
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=dt.timezone.utc)
            return parsed

        async with session_scope(settings) as session:
            rows, total = await query_tool_logs(
                session,
                start_time=parse_ts(start_time),
                end_time=parse_ts(end_time),
                op_key=op_key,
                doc_id=doc_id,
                status_min=status_min,
                status_max=status_max,
                limit=limit,
                offset=offset,
            )

        return LogsResponse(
            logs=[
                {
                    "id": row.id,
                    "op_key": row.op_key,
                    "doc_id": row.doc_id,
                    "status": row.status,
                    "latency_ms": row.latency_ms,
                    "created_at": row.created_at,
                }
                for row in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    @app.post("/vote", response_model=VoteResponse)
    async def vote(req: VoteReq) -> VoteResponse:
        async with session_scope(settings) as session:
            try:
                vote_count = await vote_for_doc(session, req.doc_id, req.increment)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail="Document not found") from exc
        return VoteResponse(doc_id=req.doc_id, vote_count=vote_count)

    @app.get("/documents", response_model=DocumentListResponse)
    async def list_docs(
        source: Optional[str] = None,
        op_key: Optional[str] = None,
        tags: Optional[str] = None,
        limit: int = Query(default=100, ge=1, le=settings.max_pagination_limit),
        offset: int = Query(default=0, ge=0),
    ) -> DocumentListResponse:
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else None
        async with session_scope(settings) as session:
            docs, total = await list_documents(
                session,
                source=source,
                op_key=op_key,
                tags=tag_list,
                limit=limit,
                offset=offset,
            )

        return DocumentListResponse(
            documents=[
                DocumentSummary(
                    id=doc.id,
                    source=doc.source,
                    op_key=doc.op_key,
                    title=doc.title,
                    content=(doc.content or "")[:500],
                    tags=doc.tags or [],
                )
                for doc in docs
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    @app.get("/documents/{doc_id}", response_model=DocumentOut)
    async def get_doc(doc_id: int) -> DocumentOut:
        async with session_scope(settings) as session:
            doc = await get_document(session, doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        return DocumentOut(
            id=doc.id,
            source=doc.source,
            op_key=doc.op_key,
            title=doc.title,
            content=doc.content,
            tags=doc.tags or [],
        )

    @app.delete("/documents/{doc_id}", response_model=DeleteResponse)
    async def delete_doc(doc_id: int) -> DeleteResponse:
        async with session_scope(settings) as session:
            deleted = await delete_document(session, doc_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found")
        return DeleteResponse(deleted=True, doc_id=doc_id)

    @app.get("/stats", response_model=StatsResponse)
    async def stats() -> StatsResponse:
        async with session_scope(settings) as session:
            return StatsResponse.model_validate(await get_statistics(session))

    @app.get("/config", response_model=ConfigResponse)
    async def config() -> ConfigResponse:
        return ConfigResponse(
            embedding=EmbeddingConfig(
                provider=settings.embedding_provider,
                model=settings.embedding_model,
                dimension=settings.embedding_dimension,
            ),
            retrieval=RetrievalConfig(
                rerank_weight=settings.rerank_weight,
                retrieval_overfetch=settings.retrieval_overfetch,
            ),
            ranking=RankingConfig(
                vote_boost_weight=settings.vote_boost_weight,
                usage_boost_weight=settings.usage_boost_weight,
                usage_boost_ttl_days=settings.usage_boost_ttl_days,
            ),
            workers=WorkerConfig(
                worker_poll_sec=settings.worker_poll_sec,
                worker_batch=settings.worker_batch,
                worker_lease_sec=settings.worker_lease_sec,
                cleanup_interval_sec=settings.cleanup_interval_sec,
            ),
            security=SecurityConfig(
                auth_enabled=bool(settings.cuecard_api_key),
                api_key_header=settings.api_key_header,
            ),
            cors=CorsConfig(
                enabled=bool(settings.cors_origins),
                origins=list(settings.cors_origins),
            ),
        )

    return app


app = create_app()
