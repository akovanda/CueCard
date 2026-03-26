from __future__ import annotations

import datetime as dt
import math
from typing import List, Optional, Sequence

from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CtxDoc, DocUsageBoost, DocVote, IngestQueue, ToolLog
from ..embedding import embed_texts
from ..settings import Settings, load_settings


async def insert_docs(session: AsyncSession, docs: List[CtxDoc]) -> None:
    session.add_all(docs)
    await session.commit()


async def enqueue_items(session: AsyncSession, items: List[dict]) -> List[int]:
    rows = [IngestQueue(**item) for item in items]
    session.add_all(rows)
    await session.commit()
    return [row.id for row in rows]


async def claim_queue_batch(
    session: AsyncSession,
    batch_size: int = 32,
    lease_seconds: int = 300,
) -> List[IngestQueue]:
    now = dt.datetime.now(dt.UTC)
    leased_until = now + dt.timedelta(seconds=lease_seconds)
    stmt = text(
        """
        UPDATE ingest_queue
        SET status = 'processing',
            leased_until = :leased_until,
            attempt_count = attempt_count + 1
        WHERE id IN (
            SELECT id
            FROM ingest_queue
            WHERE status = 'queued'
               OR (
                    status = 'processing'
                AND (leased_until IS NULL OR leased_until <= :now)
               )
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT :lim
        )
        RETURNING id, source, op_key, title, content, tags, status, error_text, attempt_count, leased_until, processed_at
        """
    )
    result = await session.execute(
        stmt,
        {"leased_until": leased_until, "now": now, "lim": batch_size},
    )
    await session.commit()
    rows = result.fetchall()
    return [
        IngestQueue(
            id=row[0],
            source=row[1],
            op_key=row[2],
            title=row[3],
            content=row[4],
            tags=row[5],
            status=row[6],
            error_text=row[7],
            attempt_count=row[8],
            leased_until=row[9],
            processed_at=row[10],
        )
        for row in rows
    ]


async def complete_queue_items(
    session: AsyncSession,
    queue_ids: List[int],
    *,
    commit: bool = True,
) -> None:
    if not queue_ids:
        return

    processed_at = dt.datetime.now(dt.UTC)
    for queue_id in queue_ids:
        await session.execute(
            text(
                """
                UPDATE ingest_queue
                SET status = 'done',
                    leased_until = NULL,
                    processed_at = :processed_at,
                    error_text = NULL
                WHERE id = :id
                """
            ),
            {"id": queue_id, "processed_at": processed_at},
        )

    if commit:
        await session.commit()


async def fail_queue_items(
    session: AsyncSession,
    queue_ids: List[int],
    error_text: str,
) -> None:
    processed_at = dt.datetime.now(dt.UTC)
    for queue_id in queue_ids:
        await session.execute(
            text(
                """
                UPDATE ingest_queue
                SET status = 'error',
                    leased_until = NULL,
                    processed_at = :processed_at,
                    error_text = :error_text
                WHERE id = :id
                """
            ),
            {"id": queue_id, "processed_at": processed_at, "error_text": error_text},
        )
    await session.commit()


async def process_queue_items(
    session: AsyncSession,
    items: List[IngestQueue],
    *,
    settings: Optional[Settings] = None,
) -> None:
    if not items:
        return

    settings = settings or load_settings()
    embeddings = embed_texts([item.content for item in items], settings=settings)
    docs = [
        CtxDoc(
            source=item.source,
            op_key=item.op_key,
            title=item.title,
            content=item.content,
            tags=item.tags,
            embedding=embedding,
        )
        for item, embedding in zip(items, embeddings)
    ]
    session.add_all(docs)
    await complete_queue_items(session, [item.id for item in items], commit=False)
    await session.commit()


async def search_snippets(
    session: AsyncSession,
    qvec: list[float],
    op_key: Optional[str],
    tags: Optional[List[str]],
    k: int = 5,
    track_usage: bool = True,
    *,
    settings: Optional[Settings] = None,
) -> Sequence[CtxDoc]:
    settings = settings or load_settings()

    distance_expr = CtxDoc.embedding.cosine_distance(qvec)
    stmt = select(CtxDoc, distance_expr.label("distance"))
    if op_key:
        stmt = stmt.where(CtxDoc.op_key == op_key)
    if tags:
        stmt = stmt.where(CtxDoc.tags.op("&&")(tags))

    stmt = stmt.order_by(distance_expr).limit(k + settings.retrieval_overfetch)
    result = await session.execute(stmt)
    rows = [(row[0], float(row[1])) for row in result.all()]

    if not rows:
        return []

    doc_ids = [doc.id for doc, _distance in rows]
    stats_stmt = (
        select(
            ToolLog.doc_id,
            func.sum(case((ToolLog.status.between(200, 299), 1), else_=0)).label("succ"),
            func.count().label("uses"),
        )
        .where(ToolLog.doc_id.in_(doc_ids))
        .group_by(ToolLog.doc_id)
    )
    stats = {
        doc_id: (succ or 0, uses or 0)
        for doc_id, succ, uses in (await session.execute(stats_stmt)).all()
    }

    votes_stmt = select(DocVote.doc_id, DocVote.vote_count).where(DocVote.doc_id.in_(doc_ids))
    votes = {
        doc_id: vote_count
        for doc_id, vote_count in (await session.execute(votes_stmt)).all()
    }

    now = dt.datetime.now(dt.UTC)
    usage_stmt = (
        select(
            DocUsageBoost.doc_id,
            func.sum(DocUsageBoost.boost_count).label("total_boost"),
        )
        .where(
            and_(DocUsageBoost.doc_id.in_(doc_ids), DocUsageBoost.expires_at > now)
        )
        .group_by(DocUsageBoost.doc_id)
    )
    usage_boosts = {
        doc_id: total_boost or 0
        for doc_id, total_boost in (await session.execute(usage_stmt)).all()
    }

    def effective_score(row_with_distance: tuple[CtxDoc, float]) -> float:
        row, distance = row_with_distance
        succ, uses = stats.get(row.id, (0, 0))
        success_signal = ((succ / uses) * math.log1p(uses)) if uses else 0.0
        vote_signal = math.log1p(max(votes.get(row.id, 0), 0))
        usage_signal = math.log1p(max(usage_boosts.get(row.id, 0), 0))
        return (
            distance
            - (settings.rerank_weight * success_signal)
            - (settings.vote_boost_weight * vote_signal)
            - (settings.usage_boost_weight * usage_signal)
        )

    rescored = sorted(rows, key=effective_score)
    final_results = [doc for doc, _distance in rescored[:k]]

    if track_usage:
        await increment_usage_boosts(
            session,
            [row.id for row in final_results],
            settings=settings,
        )

    return final_results


async def log_tool_use(
    session: AsyncSession,
    op_key: Optional[str],
    doc_ids: List[int],
    status: Optional[int],
    latency_ms: Optional[int],
) -> int:
    rows = [
        ToolLog(op_key=op_key, doc_id=doc_id, status=status, latency_ms=latency_ms)
        for doc_id in (doc_ids or [None])
    ]
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
    logs = (await session.execute(stmt)).scalars().all()
    return logs, total


async def vote_for_doc(session: AsyncSession, doc_id: int, increment: int = 1) -> int:
    doc = await get_document(session, doc_id)
    if doc is None:
        raise LookupError(f"Document {doc_id} does not exist")

    stmt = select(DocVote).where(DocVote.doc_id == doc_id)
    vote = (await session.execute(stmt)).scalar_one_or_none()
    if vote:
        vote.vote_count += increment
        vote.updated_at = dt.datetime.now(dt.UTC)
    else:
        vote = DocVote(doc_id=doc_id, vote_count=increment)
        session.add(vote)

    await session.commit()
    return vote.vote_count


async def increment_usage_boosts(
    session: AsyncSession,
    doc_ids: List[int],
    *,
    settings: Optional[Settings] = None,
) -> None:
    if not doc_ids:
        return

    settings = settings or load_settings()
    now = dt.datetime.now(dt.UTC)
    expires_at = now + dt.timedelta(days=settings.usage_boost_ttl_days)

    for doc_id in doc_ids:
        stmt = (
            select(DocUsageBoost)
            .where(and_(DocUsageBoost.doc_id == doc_id, DocUsageBoost.expires_at > now))
            .order_by(DocUsageBoost.expires_at.desc())
            .limit(1)
        )
        boost = (await session.execute(stmt)).scalar_one_or_none()
        if boost:
            boost.boost_count += 1
        else:
            session.add(
                DocUsageBoost(doc_id=doc_id, boost_count=1, expires_at=expires_at)
            )

    await session.commit()


async def cleanup_expired_boosts(session: AsyncSession) -> int:
    now = dt.datetime.now(dt.UTC)
    result = await session.execute(
        text("DELETE FROM doc_usage_boost WHERE expires_at <= :now"),
        {"now": now},
    )
    await session.commit()
    return result.rowcount


async def list_documents(
    session: AsyncSession,
    source: Optional[str] = None,
    op_key: Optional[str] = None,
    tags: Optional[List[str]] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[Sequence[CtxDoc], int]:
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

    total = (await session.execute(count_stmt)).scalar() or 0
    stmt = stmt.order_by(CtxDoc.id.desc()).limit(limit).offset(offset)
    documents = (await session.execute(stmt)).scalars().all()
    return documents, total


async def get_document(session: AsyncSession, doc_id: int) -> Optional[CtxDoc]:
    stmt = select(CtxDoc).where(CtxDoc.id == doc_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_document(session: AsyncSession, doc_id: int) -> bool:
    doc = await get_document(session, doc_id)
    if not doc:
        return False

    await session.execute(text("DELETE FROM doc_vote WHERE doc_id = :id"), {"id": doc_id})
    await session.execute(
        text("DELETE FROM doc_usage_boost WHERE doc_id = :id"),
        {"id": doc_id},
    )
    await session.execute(text("DELETE FROM tool_log WHERE doc_id = :id"), {"id": doc_id})
    await session.delete(doc)
    await session.commit()
    return True


async def get_statistics(session: AsyncSession) -> dict:
    total_docs = (await session.execute(select(func.count()).select_from(CtxDoc))).scalar()

    source_counts = await session.execute(
        select(CtxDoc.source, func.count()).group_by(CtxDoc.source)
    )
    sources = {source: count for source, count in source_counts.all()}

    queue_counts = await session.execute(
        select(IngestQueue.status, func.count()).group_by(IngestQueue.status)
    )
    queue = {status: count for status, count in queue_counts.all()}

    total_searches = (await session.execute(select(func.count()).select_from(ToolLog))).scalar()
    successful_searches = (
        await session.execute(
            select(func.count())
            .select_from(ToolLog)
            .where(ToolLog.status.between(200, 299))
        )
    ).scalar()

    total_votes = (
        await session.execute(select(func.sum(DocVote.vote_count)).select_from(DocVote))
    ).scalar() or 0
    active_boosts = (
        await session.execute(
            select(func.count())
            .select_from(DocUsageBoost)
            .where(DocUsageBoost.expires_at > dt.datetime.now(dt.UTC))
        )
    ).scalar()

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
            "active_boosts": active_boosts or 0,
        },
    }
