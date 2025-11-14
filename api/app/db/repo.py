from __future__ import annotations
from typing import Sequence, List, Optional
from sqlalchemy import select, text, bindparam, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pgvector.sqlalchemy import Vector
from .models import CtxDoc, IngestQueue, ToolLog, DocVote, DocUsageBoost, EMBEDDING_DIM
from ..embedding import embed_texts
import datetime as dt
import os

RERANK_WEIGHT = float(os.getenv("RERANK_WEIGHT", "0.1"))         # success-rate boost (0 = off)
RETRIEVAL_OVERFETCH = int(os.getenv("RETRIEVAL_OVERFETCH", "8")) # fetch then rerank
VOTE_BOOST_WEIGHT = float(os.getenv("VOTE_BOOST_WEIGHT", "1.0"))  # permanent vote boost weight
USAGE_BOOST_WEIGHT = float(os.getenv("USAGE_BOOST_WEIGHT", "0.01"))  # temporary usage boost weight (tiny)
USAGE_BOOST_TTL_DAYS = int(os.getenv("USAGE_BOOST_TTL_DAYS", "14"))  # default 2 weeks

async def insert_docs(session: AsyncSession, docs: List[CtxDoc]) -> None:
    session.add_all(docs)
    await session.commit()

# --- QUEUE ---

async def enqueue_items(session: AsyncSession, items: List[dict]) -> List[int]:
    rows = [IngestQueue(**i) for i in items]
    session.add_all(rows)
    await session.commit()
    return [r.id for r in rows]

async def claim_queue_batch(session: AsyncSession, batch_size: int = 32) -> List[IngestQueue]:
    # SELECT ... FOR UPDATE SKIP LOCKED
    stmt = text("""
        UPDATE ingest_queue
        SET status = 'processing'
        WHERE id IN (
            SELECT id FROM ingest_queue WHERE status='queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT :lim
        )
        RETURNING id, source, op_key, title, content, tags, status, error_text
    """)
    res = await session.execute(stmt, {"lim": batch_size})
    rows = res.fetchall()
    return [IngestQueue(id=r[0], source=r[1], op_key=r[2], title=r[3], content=r[4], tags=r[5], status=r[6], error_text=r[7]) for r in rows]

async def complete_queue_item(session: AsyncSession, qid: int, ok: bool, error_text: Optional[str] = None) -> None:
    if ok:
        await session.execute(text("UPDATE ingest_queue SET status='done' WHERE id=:id"), {"id": qid})
    else:
        await session.execute(text("UPDATE ingest_queue SET status='error', error_text=:e WHERE id=:id"), {"id": qid, "e": error_text})
    await session.commit()

async def process_queue_items(session: AsyncSession, items: List[IngestQueue]) -> None:
    if not items:
        return
    contents = [i.content for i in items]
    embeddings = embed_texts(contents)
    docs = []
    for it, emb in zip(items, embeddings):
        docs.append(CtxDoc(source=it.source, op_key=it.op_key, title=it.title, content=it.content, tags=it.tags, embedding=emb))
    session.add_all(docs)
    await session.commit()
    for it in items:
        await complete_queue_item(session, it.id, ok=True)

# --- SEARCH (with voting and usage boosts) ---

async def search_snippets(
    session: AsyncSession,
    qvec: list[float],
    op_key: Optional[str],
    tags: Optional[List[str]],
    k: int = 5,
    track_usage: bool = True,
) -> Sequence[CtxDoc]:
    # Overfetch by vector distance
    stmt = select(CtxDoc)
    if op_key:
        stmt = stmt.where(CtxDoc.op_key == op_key)
    if tags:
        stmt = stmt.where(CtxDoc.tags.op("&&")(tags))
    order_expr = text("embedding <=> :qvec").bindparams(
        bindparam("qvec", type_=Vector(EMBEDDING_DIM))
    )
    stmt = stmt.order_by(order_expr).limit(max(k, RETRIEVAL_OVERFETCH))
    res = await session.execute(stmt, {"qvec": qvec})
    rows = list(res.scalars())

    if not rows:
        return rows

    doc_ids = [r.id for r in rows]

    # Pull simple success stats for candidates (old rerank logic)
    stats_stmt = select(
        ToolLog.doc_id,
        func.sum(case((ToolLog.status.between(200, 299), 1), else_=0)).label("succ"),
        func.count().label("uses"),
    ).where(ToolLog.doc_id.in_(doc_ids)).group_by(ToolLog.doc_id)
    stats = {doc_id: (succ or 0, uses or 0) for doc_id, succ, uses in (await session.execute(stats_stmt)).all()}

    # Pull permanent vote boosts
    votes_stmt = select(DocVote.doc_id, DocVote.vote_count).where(DocVote.doc_id.in_(doc_ids))
    votes = {doc_id: vote_count for doc_id, vote_count in (await session.execute(votes_stmt)).all()}

    # Pull active temporary usage boosts (not expired)
    now = dt.datetime.now(dt.UTC)
    usage_boost_stmt = select(
        DocUsageBoost.doc_id,
        func.sum(DocUsageBoost.boost_count).label("total_boost")
    ).where(
        and_(DocUsageBoost.doc_id.in_(doc_ids), DocUsageBoost.expires_at > now)
    ).group_by(DocUsageBoost.doc_id)
    usage_boosts = {doc_id: total_boost or 0 for doc_id, total_boost in (await session.execute(usage_boost_stmt)).all()}

    # Re-rank by combining vector distance with boosts
    def effective_score(idx, row):
        # Old success rate boost
        succ, uses = stats.get(row.id, (0, 0))
        sr = (succ / uses) if uses else 0.0
        sr_boost = RERANK_WEIGHT * sr

        # Permanent vote boost
        vote_boost = VOTE_BOOST_WEIGHT * votes.get(row.id, 0)

        # Temporary usage boost
        usage_boost = USAGE_BOOST_WEIGHT * usage_boosts.get(row.id, 0)

        # Lower score is better (closer distance), so subtract boosts
        return idx - sr_boost - vote_boost - usage_boost

    rescored = sorted(enumerate(rows), key=lambda t: effective_score(t[0], t[1]))
    final_results = [r for _, r in rescored[:k]]

    # Track usage for returned results (tiny temporary boost)
    if track_usage:
        await increment_usage_boosts(session, [r.id for r in final_results])

    return final_results

# --- LOGGING ---

async def log_tool_use(session: AsyncSession, op_key: Optional[str], doc_ids: List[int], status: Optional[int], latency_ms: Optional[int]) -> int:
    rows = [ToolLog(op_key=op_key, doc_id=did, status=status, latency_ms=latency_ms) for did in (doc_ids or [None])]
    session.add_all(rows)
    await session.commit()
    return len(rows)

async def query_tool_logs(
    session: AsyncSession,
    start_time: Optional[dt.datetime] = None,
    end_time: Optional[dt.datetime] = None,
    op_key: Optional[str] = None,
    doc_id: Optional[int] = None,
    status_min: Optional[int] = None,
    status_max: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[Sequence[ToolLog], int]:
    """
    Query raw tool logs with optional time range and filters.
    Returns (logs, total_count) with pagination.
    """
    stmt = select(ToolLog)
    count_stmt = select(func.count()).select_from(ToolLog)

    if start_time:
        stmt = stmt.where(ToolLog.created_at >= start_time)
        count_stmt = count_stmt.where(ToolLog.created_at >= start_time)
    if end_time:
        stmt = stmt.where(ToolLog.created_at <= end_time)
        count_stmt = count_stmt.where(ToolLog.created_at <= end_time)
    if op_key:
        stmt = stmt.where(ToolLog.op_key == op_key)
        count_stmt = count_stmt.where(ToolLog.op_key == op_key)
    if doc_id is not None:
        stmt = stmt.where(ToolLog.doc_id == doc_id)
        count_stmt = count_stmt.where(ToolLog.doc_id == doc_id)
    if status_min is not None:
        stmt = stmt.where(ToolLog.status >= status_min)
        count_stmt = count_stmt.where(ToolLog.status >= status_min)
    if status_max is not None:
        stmt = stmt.where(ToolLog.status <= status_max)
        count_stmt = count_stmt.where(ToolLog.status <= status_max)

    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(ToolLog.created_at.desc(), ToolLog.id.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    logs = result.scalars().all()
    return logs, total

# --- VOTING ---

async def vote_for_doc(session: AsyncSession, doc_id: int, increment: int = 1) -> int:
    """
    Increment permanent vote count for a document.
    Returns the new vote count.
    """
    # Try to get existing vote record
    stmt = select(DocVote).where(DocVote.doc_id == doc_id)
    result = await session.execute(stmt)
    vote = result.scalar_one_or_none()

    if vote:
        vote.vote_count += increment
        vote.updated_at = dt.datetime.now(dt.UTC)
    else:
        vote = DocVote(doc_id=doc_id, vote_count=increment)
        session.add(vote)

    await session.commit()
    return vote.vote_count

# --- USAGE BOOSTS ---

async def increment_usage_boosts(session: AsyncSession, doc_ids: List[int]) -> None:
    """
    Increment tiny temporary usage boost for documents returned in search.
    Creates or updates boost records with expiration.
    """
    if not doc_ids:
        return

    now = dt.datetime.now(dt.UTC)
    expires_at = now + dt.timedelta(days=USAGE_BOOST_TTL_DAYS)

    for doc_id in doc_ids:
        # Try to find an active (non-expired) boost for this doc
        stmt = select(DocUsageBoost).where(
            and_(DocUsageBoost.doc_id == doc_id, DocUsageBoost.expires_at > now)
        ).order_by(DocUsageBoost.expires_at.desc()).limit(1)
        result = await session.execute(stmt)
        boost = result.scalar_one_or_none()

        if boost:
            # Increment existing active boost
            boost.boost_count += 1
        else:
            # Create new boost record
            boost = DocUsageBoost(doc_id=doc_id, boost_count=1, expires_at=expires_at)
            session.add(boost)

    await session.commit()

async def cleanup_expired_boosts(session: AsyncSession) -> int:
    """
    Delete expired usage boosts.
    Returns number of records deleted.
    """
    now = dt.datetime.now(dt.UTC)
    stmt = text("DELETE FROM doc_usage_boost WHERE expires_at <= :now")
    result = await session.execute(stmt, {"now": now})
    await session.commit()
    return result.rowcount

# --- DOCUMENT MANAGEMENT ---

async def list_documents(
    session: AsyncSession,
    source: Optional[str] = None,
    op_key: Optional[str] = None,
    tags: Optional[List[str]] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[Sequence[CtxDoc], int]:
    """
    List documents with optional filtering.
    Returns (documents, total_count).
    """
    stmt = select(CtxDoc)
    count_stmt = select(func.count()).select_from(CtxDoc)

    if source:
        stmt = stmt.where(CtxDoc.source == source)
        count_stmt = count_stmt.where(CtxDoc.source == source)
    if op_key:
        stmt = stmt.where(CtxDoc.op_key == op_key)
        count_stmt = count_stmt.where(CtxDoc.op_key == op_key)
    if tags:
        stmt = stmt.where(CtxDoc.tags.op("&&")(tags))
        count_stmt = count_stmt.where(CtxDoc.tags.op("&&")(tags))

    # Get total count
    total = (await session.execute(count_stmt)).scalar()

    # Get paginated results
    stmt = stmt.order_by(CtxDoc.id.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    documents = result.scalars().all()

    return documents, total or 0

async def get_document(session: AsyncSession, doc_id: int) -> Optional[CtxDoc]:
    """Get a specific document by ID."""
    stmt = select(CtxDoc).where(CtxDoc.id == doc_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def delete_document(session: AsyncSession, doc_id: int) -> bool:
    """
    Delete a document and its associated votes/boosts.
    Returns True if document was deleted, False if not found.
    """
    # Check if document exists
    doc = await get_document(session, doc_id)
    if not doc:
        return False

    # Delete associated records
    await session.execute(text("DELETE FROM doc_vote WHERE doc_id = :id"), {"id": doc_id})
    await session.execute(text("DELETE FROM doc_usage_boost WHERE doc_id = :id"), {"id": doc_id})
    await session.execute(text("DELETE FROM tool_log WHERE doc_id = :id"), {"id": doc_id})

    # Delete the document
    await session.delete(doc)
    await session.commit()
    return True

# --- STATISTICS ---

async def get_statistics(session: AsyncSession) -> dict:
    """Get usage statistics for the system."""
    # Document counts
    total_docs = (await session.execute(select(func.count()).select_from(CtxDoc))).scalar()

    # Source breakdown
    source_counts = await session.execute(
        select(CtxDoc.source, func.count()).group_by(CtxDoc.source)
    )
    sources = {source: count for source, count in source_counts.all()}

    # Queue stats
    queue_stats = await session.execute(
        select(IngestQueue.status, func.count()).group_by(IngestQueue.status)
    )
    queue = {status: count for status, count in queue_stats.all()}

    # Tool usage stats
    total_searches = (await session.execute(select(func.count()).select_from(ToolLog))).scalar()
    successful_searches = (await session.execute(
        select(func.count()).select_from(ToolLog).where(ToolLog.status.between(200, 299))
    )).scalar()

    # Vote and boost stats
    total_votes = (await session.execute(
        select(func.sum(DocVote.vote_count)).select_from(DocVote)
    )).scalar() or 0

    total_boosts = (await session.execute(
        select(func.count()).select_from(DocUsageBoost)
    )).scalar()

    return {
        "documents": {
            "total": total_docs or 0,
            "by_source": sources,
        },
        "queue": queue,
        "searches": {
            "total": total_searches or 0,
            "successful": successful_searches or 0,
        },
        "engagement": {
            "total_votes": int(total_votes),
            "active_boosts": total_boosts or 0,
        }
    }
