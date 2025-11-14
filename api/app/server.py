from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import os
import datetime as dt  # use module alias for datetime operations

from fastapi.middleware.cors import CORSMiddleware

from .db.session import SessionLocal
from .db.repo import (
    search_snippets, enqueue_items, claim_queue_batch, process_queue_items, log_tool_use,
    vote_for_doc, cleanup_expired_boosts, list_documents, get_document, delete_document,
    get_statistics, query_tool_logs
)
from .embedding import embed_texts

def create_app() -> FastAPI:
    """Application factory to allow testing with different env configs (e.g., CORS)."""
    # Security & CORS configuration (read on creation)
    api_key_header_name: str = os.getenv("API_KEY_HEADER", "X-API-Key")
    cors_origins_raw: str = os.getenv("CORS_ORIGINS", "").strip()
    cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

    async def api_key_auth(request: Request):
        # Read API key dynamically so changes in environment can be observed in tests if needed
        api_key = os.getenv("CUECARD_API_KEY")
        if not api_key:
            return
        if request.url.path in ("/health",):
            return
        provided = request.headers.get(api_key_header_name)
        if not provided or provided != api_key:
            raise HTTPException(status_code=401, detail="Unauthorized")

    app = FastAPI(title="CueCard", version="0.2", dependencies=[Depends(api_key_auth)])

    # CORS middleware (enable only if origins provided)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    class RetrieveReq(BaseModel):
        goal: str
        op_key: Optional[str] = None
        role: Optional[str] = None
        tags: Optional[List[str]] = None
        k: int = 5

    class RecordItem(BaseModel):
        source: str
        op_key: Optional[str] = None
        title: Optional[str] = None
        content: str
        tags: Optional[List[str]] = None

    class RecordBatch(BaseModel):
        items: List[RecordItem]

    class LogReq(BaseModel):
        op_key: Optional[str] = None
        doc_ids: Optional[List[int]] = None
        status: Optional[int] = None
        latency_ms: Optional[int] = None

    class VoteReq(BaseModel):
        doc_id: int
        increment: int = 1

    # Query logs response model (inline dict shaping)
    def _serialize_log(row):
        return {
            "id": row.id,
            "op_key": row.op_key,
            "doc_id": row.doc_id,
            "status": row.status,
            "latency_ms": row.latency_ms,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # Background queue worker
    _worker_task: asyncio.Task | None = None
    _cleanup_task: asyncio.Task | None = None
    WORKER_POLL_SEC = float(os.getenv("WORKER_POLL_SEC", "2"))
    WORKER_BATCH = int(os.getenv("WORKER_BATCH", "32"))
    CLEANUP_INTERVAL_SEC = float(os.getenv("CLEANUP_INTERVAL_SEC", "3600"))  # 1 hour default

    async def _worker_loop():  # pragma: no cover
        await asyncio.sleep(0.1)
        while True:
            try:
                async with SessionLocal() as session:
                    items = await claim_queue_batch(session, batch_size=WORKER_BATCH)
                    if items:
                        await process_queue_items(session, items)
            except Exception as e:
                print(f"[worker] error: {e}", flush=True)
            await asyncio.sleep(WORKER_POLL_SEC)

    async def _cleanup_loop():  # pragma: no cover
        """Background task to clean up expired usage boosts"""
        await asyncio.sleep(10)  # Initial delay
        while True:
            try:
                async with SessionLocal() as session:
                    deleted = await cleanup_expired_boosts(session)
                    if deleted > 0:
                        print(f"[cleanup] deleted {deleted} expired usage boosts", flush=True)
            except Exception as e:
                print(f"[cleanup] error: {e}", flush=True)
            await asyncio.sleep(CLEANUP_INTERVAL_SEC)

    @app.on_event("startup")
    async def startup():  # pragma: no cover
        nonlocal _worker_task, _cleanup_task
        if _worker_task is None:
            _worker_task = asyncio.create_task(_worker_loop())
        if _cleanup_task is None:
            _cleanup_task = asyncio.create_task(_cleanup_loop())

    @app.on_event("shutdown")
    async def shutdown():  # pragma: no cover
        nonlocal _worker_task, _cleanup_task
        if _worker_task:
            _worker_task.cancel()
            _worker_task = None
        if _cleanup_task:
            _cleanup_task.cancel()
            _cleanup_task = None

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/retrieve")
    async def retrieve(req: RetrieveReq):
        q = " ".join([x for x in [req.goal, req.role, req.op_key] if x])
        qvec = embed_texts([q])[0]
        async with SessionLocal() as session:
            rows = await search_snippets(session, qvec, req.op_key, req.tags, req.k)

        MAX_CHARS = 1200
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "source": r.source,
                "op_key": r.op_key,
                "title": r.title,
                "content": (r.content or "")[:MAX_CHARS]
            })
        return {"snippets": out}

    @app.post("/record", status_code=202)
    async def record(batch: RecordBatch):
        payload = [{
            "source": it.source,
            "op_key": it.op_key,
            "title": it.title,
            "content": it.content,
            "tags": it.tags or []
        } for it in batch.items]
        async with SessionLocal() as session:
            ids = await enqueue_items(session, payload)
        return {"queued": ids}

    @app.post("/log")
    async def log(req: LogReq):
        async with SessionLocal() as session:
            n = await log_tool_use(session, req.op_key, req.doc_ids or [], req.status, req.latency_ms)
        return {"logged": n}

    @app.get("/logs")
    async def get_logs(
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        op_key: Optional[str] = None,
        doc_id: Optional[int] = None,
        status_min: Optional[int] = None,
        status_max: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        """Query raw tool logs by time range and filters for UI display"""
        # Parse ISO timestamps if provided
        def parse_ts(s: Optional[str]):
            if not s:
                return None
            try:
                # Accept both with and without timezone; default to UTC
                return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid timestamp format; use ISO 8601")

        st = parse_ts(start_time)
        et = parse_ts(end_time)
        async with SessionLocal() as session:
            rows, total = await query_tool_logs(
                session,
                start_time=st,
                end_time=et,
                op_key=op_key,
                doc_id=doc_id,
                status_min=status_min,
                status_max=status_max,
                limit=limit,
                offset=offset,
            )
        return {
            "logs": [_serialize_log(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.post("/vote")
    async def vote(req: VoteReq):
        """Mark a document as 'good' by incrementing its permanent vote count"""
        async with SessionLocal() as session:
            new_count = await vote_for_doc(session, req.doc_id, req.increment)
        return {"doc_id": req.doc_id, "vote_count": new_count}

    @app.get("/documents")
    async def list_docs(
        source: Optional[str] = None,
        op_key: Optional[str] = None,
        tags: Optional[str] = None,  # comma-separated
        limit: int = 100,
        offset: int = 0,
    ):
        """List documents with optional filtering and pagination"""
        tag_list = tags.split(",") if tags else None
        async with SessionLocal() as session:
            docs, total = await list_documents(session, source, op_key, tag_list, limit, offset)

        return {
            "documents": [
                {
                    "id": d.id,
                    "source": d.source,
                    "op_key": d.op_key,
                    "title": d.title,
                    "content": (d.content or "")[:500],  # Truncate for list view
                    "tags": d.tags or [],
                }
                for d in docs
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/documents/{doc_id}")
    async def get_doc(doc_id: int):
        """Get full details of a specific document"""
        async with SessionLocal() as session:
            doc = await get_document(session, doc_id)

        if not doc:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "id": doc.id,
            "source": doc.source,
            "op_key": doc.op_key,
            "title": doc.title,
            "content": doc.content,
            "tags": doc.tags or [],
        }

    @app.delete("/documents/{doc_id}")
    async def delete_doc(doc_id: int):
        """Delete a document and all associated data"""
        async with SessionLocal() as session:
            deleted = await delete_document(session, doc_id)

        if not deleted:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Document not found")

        return {"deleted": True, "doc_id": doc_id}

    @app.get("/stats")
    async def stats():
        """Get system usage statistics"""
        async with SessionLocal() as session:
            return await get_statistics(session)

    @app.get("/config")
    async def config():
        """Get current system configuration"""
        cfg_embedding = {
            "provider": os.getenv("EMBEDDING_PROVIDER", "local"),
            "model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            "dimension": int(os.getenv("EMBEDDING_DIM", "1536")),
        }
        cfg_retrieval = {
            "rerank_weight": float(os.getenv("RERANK_WEIGHT", "0.1")),
            "retrieval_overfetch": int(os.getenv("RETRIEVAL_OVERFETCH", "8")),
        }
        cfg_ranking = {
            "vote_boost_weight": float(os.getenv("VOTE_BOOST_WEIGHT", "1.0")),
            "usage_boost_weight": float(os.getenv("USAGE_BOOST_WEIGHT", "0.01")),
            "usage_boost_ttl_days": int(os.getenv("USAGE_BOOST_TTL_DAYS", "14")),
        }
        cfg_workers = {
            "worker_poll_sec": float(os.getenv("WORKER_POLL_SEC", "2")),
            "worker_batch": int(os.getenv("WORKER_BATCH", "32")),
            "cleanup_interval_sec": float(os.getenv("CLEANUP_INTERVAL_SEC", "3600")),
        }
        cfg_security = {
            "auth_enabled": bool(os.getenv("CUECARD_API_KEY")),
            "api_key_header": os.getenv("API_KEY_HEADER", "X-API-Key"),
        }
        cors_raw = os.getenv("CORS_ORIGINS", "").strip()
        cors_list = [o.strip() for o in cors_raw.split(",") if o.strip()]
        cfg_cors = {
            "enabled": bool(cors_list),
            "origins": cors_list,
        }
        return {
            "embedding": cfg_embedding,
            "retrieval": cfg_retrieval,
            "ranking": cfg_ranking,
            "workers": cfg_workers,
            "security": cfg_security,
            "cors": cfg_cors,
        }

    return app

# Module-level app for production servers (uvicorn target)
app = create_app()
