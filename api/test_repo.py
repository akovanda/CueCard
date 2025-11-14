import asyncio
import os
import time
from datetime import datetime, timedelta
from typing import List

import pytest

from app.db.session import SessionLocal
from app.db.models import CtxDoc, IngestQueue, ToolLog, DocVote, DocUsageBoost
from app.db import repo as repo
from app.embedding import embed_texts


def _uniq(s: str) -> str:
    return f"{s}-{int(time.time() * 1000)}"


@pytest.mark.asyncio
async def test_enqueue_and_process_queue_items():
    items = [
        {
            "source": "test",
            "op_key": None,
            "title": _uniq("Q1"),
            "content": "Hello World",
            "tags": ["repo", "queue"],
        },
        {
            "source": "test",
            "op_key": "opA",
            "title": _uniq("Q2"),
            "content": "Goodbye World",
            "tags": ["repo", "queue"],
        },
    ]
    async with SessionLocal() as session:
        ids = await repo.enqueue_items(session, items)
        assert len(ids) == 2

        batch = await repo.claim_queue_batch(session, batch_size=10)
        assert len(batch) >= 2  # may include previous test items

        # Process only the ones we just enqueued
        ids_set = set(ids)
        to_process = [b for b in batch if b.id in ids_set]
        await repo.process_queue_items(session, to_process)

        # Verify docs ingested
        q = await session.execute(
            repo.select(CtxDoc).where(CtxDoc.title.in_([items[0]["title"], items[1]["title"]]))
        )
        docs = q.scalars().all()
        assert len(docs) == 2

        # Verify queue status updated
        q2 = await session.execute(
            repo.select(IngestQueue.status).where(IngestQueue.id.in_(ids))
        )
        statuses = [s for (s,) in q2.all()]
        assert all(s == "done" for s in statuses)


@pytest.mark.asyncio
async def test_search_snippets_filters_and_usage_boost():
    title1 = _uniq("DocAuth")
    title2 = _uniq("DocRate")
    contents = [
        "Authentication with API key in Authorization header",
        "Rate limited to 100 requests per minute",
    ]
    embs = embed_texts(contents)

    async with SessionLocal() as session:
        unique_op = _uniq("op_test_unique")
        d1 = CtxDoc(source="test", op_key=unique_op, title=title1, content=contents[0], tags=["auth", "api"], embedding=embs[0])
        d2 = CtxDoc(source="test", op_key=unique_op, title=title2, content=contents[1], tags=["limits", "api"], embedding=embs[1])
        session.add_all([d1, d2])
        await session.commit()

        # use embedding of first doc to ensure it appears in results deterministically
        qvec = embs[0]
        rows = await repo.search_snippets(session, qvec, op_key=unique_op, tags=None, k=2, track_usage=True)
        assert isinstance(rows, list)
        assert any(r.title == title1 for r in rows)

        # filter by tag within the op_key
        rows_tag = await repo.search_snippets(session, qvec, op_key=unique_op, tags=["api"], k=5, track_usage=False)
        assert all("api" in (r.tags or []) for r in rows_tag)

        # filter by op_key
        rows_op = await repo.search_snippets(session, qvec, op_key=unique_op, tags=None, k=5, track_usage=False)
        assert all(r.op_key == unique_op for r in rows_op)

        # usage boost should have been created for the first call
        res = await session.execute(repo.select(DocUsageBoost).order_by(DocUsageBoost.id.desc()).limit(1))
        boost = res.scalar_one_or_none()
        assert boost is not None
        assert boost.boost_count >= 1


@pytest.mark.asyncio
async def test_vote_and_log_and_cleanup():
    title = _uniq("VoteMe")
    emb = embed_texts(["some content"])[0]
    async with SessionLocal() as session:
        doc = CtxDoc(source="test", op_key=None, title=title, content="vote content", tags=["vote"], embedding=emb)
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        # vote twice
        c1 = await repo.vote_for_doc(session, doc.id, 1)
        c2 = await repo.vote_for_doc(session, doc.id, 1)
        assert c2 == c1 + 1

        # log tool use with and without doc_ids
        n1 = await repo.log_tool_use(session, op_key="op1", doc_ids=[doc.id], status=200, latency_ms=10)
        n2 = await repo.log_tool_use(session, op_key="op2", doc_ids=[], status=500, latency_ms=5)
        assert n1 == 1 and n2 == 1

        # create an expired boost and cleanup
        old = DocUsageBoost(doc_id=doc.id, boost_count=1, expires_at=datetime.utcnow() - timedelta(days=1))
        session.add(old)
        await session.commit()
        deleted = await repo.cleanup_expired_boosts(session)
        assert deleted >= 1


@pytest.mark.asyncio
async def test_list_get_delete_documents_cycle():
    titles = [_uniq("ListA"), _uniq("ListB")]
    embs = embed_texts(["A", "B"])
    async with SessionLocal() as session:
        d1 = CtxDoc(source="md", op_key="op_a", title=titles[0], content="A", tags=["x", "y"], embedding=embs[0])
        d2 = CtxDoc(source="md", op_key="op_b", title=titles[1], content="B", tags=["y"], embedding=embs[1])
        session.add_all([d1, d2])
        await session.commit()
        await session.refresh(d1)
        await session.refresh(d2)

        # list by source and tags
        docs, total = await repo.list_documents(session, source="md", op_key=None, tags=["y"], limit=10, offset=0)
        assert total >= 2
        assert all("y" in (d.tags or []) for d in docs)

        # get and delete one
        got = await repo.get_document(session, d1.id)
        assert got and got.title == titles[0]
        ok = await repo.delete_document(session, d1.id)
        assert ok is True
        none = await repo.get_document(session, d1.id)
        assert none is None


@pytest.mark.asyncio
async def test_cli_ingest_md(tmp_path, monkeypatch):
    # Prepare markdown files
    md_dir = tmp_path / "docs"
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / "a.md").write_text("Alpha\n\nContent A", encoding="utf-8")
    (md_dir / "b.md").write_text("Beta\n\nContent B", encoding="utf-8")

    # Run CLI ingestion directly
    from app.cli import ingest_md
    await ingest_md(str(md_dir), op_key="cli_op", tags=["cli", "ingest"])

    # Verify the docs were inserted
    async with SessionLocal() as session:
        docs, total = await repo.list_documents(session, source="md", tags=["cli"], limit=100, offset=0)
        # Should find at least 2 with 'cli' tag
        assert len(docs) >= 2


@pytest.mark.asyncio
async def test_query_tool_logs_time_range_and_filters():
    async with SessionLocal() as session:
        # Insert some logs with op_key and status
        n = await repo.log_tool_use(session, op_key="chat", doc_ids=[None], status=200, latency_ms=50)
        assert n == 1
        await asyncio.sleep(0.1)  # ensure different timestamps
        n2 = await repo.log_tool_use(session, op_key="chat", doc_ids=[None], status=500, latency_ms=75)
        assert n2 == 1

        # Query recent logs
        now = datetime.utcnow()
        start = now - timedelta(minutes=5)
        logs, total = await repo.query_tool_logs(session, start_time=start, end_time=now, op_key="chat")
        assert total >= 2
        assert all(l.op_key == "chat" for l in logs)
        assert len(logs) <= total

        # Pagination
        logs_page1, total1 = await repo.query_tool_logs(session, op_key="chat", limit=1, offset=0)
        logs_page2, total2 = await repo.query_tool_logs(session, op_key="chat", limit=1, offset=1)
        assert total1 == total2 >= 2
        assert len(logs_page1) == 1 and len(logs_page2) == 1
        assert logs_page1[0].id != logs_page2[0].id

