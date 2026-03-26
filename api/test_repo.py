from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select, text

from app.db import repo
from app.db.models import CtxDoc, DocUsageBoost, IngestQueue
from app.db.session import session_scope
from app.embedding import embed_texts


@pytest.mark.asyncio
async def test_claim_queue_batch_reclaims_expired_leases(settings):
    async with session_scope(settings) as session:
        queued = await repo.enqueue_items(
            session,
            [
                {
                    "source": "test",
                    "title": "Queued",
                    "content": "hello world",
                    "tags": ["queue"],
                }
            ],
        )

    async with session_scope(settings) as session:
        batch = await repo.claim_queue_batch(session, batch_size=10, lease_seconds=1)
        assert [item.id for item in batch] == queued
        assert batch[0].attempt_count == 1

    async with session_scope(settings) as session:
        await session.execute(
            text(
                "UPDATE ingest_queue SET leased_until = :leased_until WHERE id = :id"
            ),
            {"id": queued[0], "leased_until": dt.datetime.now(dt.UTC) - dt.timedelta(seconds=5)},
        )
        await session.commit()

    async with session_scope(settings) as session:
        reclaimed = await repo.claim_queue_batch(session, batch_size=10, lease_seconds=30)
        assert [item.id for item in reclaimed] == queued
        assert reclaimed[0].attempt_count == 2
        await repo.process_queue_items(session, reclaimed, settings=settings)

    async with session_scope(settings) as session:
        docs = (
            await session.execute(select(CtxDoc).where(CtxDoc.title == "Queued"))
        ).scalars().all()
        status = (
            await session.execute(
                select(IngestQueue.status).where(IngestQueue.id == queued[0])
            )
        ).scalar_one()
        assert len(docs) == 1
        assert status == "done"


@pytest.mark.asyncio
async def test_search_snippets_tracks_usage_boosts(settings):
    embeddings = embed_texts(
        ["Authentication uses a bearer token", "Orders can be paginated"],
        settings=settings,
    )

    async with session_scope(settings) as session:
        auth = CtxDoc(
            source="test",
            title="Auth",
            content="Authentication uses a bearer token",
            tags=["auth"],
            embedding=embeddings[0],
        )
        orders = CtxDoc(
            source="test",
            title="Orders",
            content="Orders can be paginated",
            tags=["orders"],
            embedding=embeddings[1],
        )
        session.add_all([auth, orders])
        await session.commit()

        rows = await repo.search_snippets(
            session,
            embeddings[0],
            op_key=None,
            tags=None,
            k=2,
            track_usage=True,
            settings=settings,
        )
        assert [row.title for row in rows][0] == "Auth"

    async with session_scope(settings) as session:
        boosts = (
            await session.execute(select(DocUsageBoost).order_by(DocUsageBoost.id.asc()))
        ).scalars().all()
        assert len(boosts) == 2
        assert all(boost.boost_count == 1 for boost in boosts)


@pytest.mark.asyncio
async def test_vote_for_missing_document_raises(settings):
    async with session_scope(settings) as session:
        with pytest.raises(LookupError):
            await repo.vote_for_doc(session, 9999, 1)


@pytest.mark.asyncio
async def test_logs_documents_and_statistics(settings):
    embedding = embed_texts(["some content"], settings=settings)[0]
    async with session_scope(settings) as session:
        doc = CtxDoc(
            source="test",
            title="Stats",
            content="some content",
            tags=["stats"],
            embedding=embedding,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        await repo.vote_for_doc(session, doc.id, 1)
        await repo.log_tool_use(session, "chat", [doc.id], 200, 12)
        await repo.log_tool_use(session, "chat", [], 500, 5)

        logs, total = await repo.query_tool_logs(session, op_key="chat")
        stats = await repo.get_statistics(session)

        assert total == 2
        assert len(logs) == 2
        assert stats["documents"]["total"] == 1
        assert stats["searches"]["total"] == 2
        assert stats["searches"]["successful"] == 1
        assert stats["engagement"]["total_votes"] == 1
