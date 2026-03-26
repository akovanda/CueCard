from __future__ import annotations

import datetime as dt

import httpx
import pytest


async def record_and_process(
    client: httpx.AsyncClient,
    process_queue,
    items: list[dict],
) -> list[int]:
    response = await client.post("/record", json={"items": items})
    assert response.status_code == 202
    queued = response.json()["queued"]
    processed = await process_queue()
    assert processed == len(items)
    return queued


class TestHealthAndConfig:
    @pytest.mark.asyncio
    async def test_health(self, client: httpx.AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_config_reflects_derived_embedding_dimension(self, client: httpx.AsyncClient):
        response = await client.get("/config")
        assert response.status_code == 200
        config = response.json()
        assert config["embedding"]["provider"] == "local"
        assert config["embedding"]["model"] == "text-embedding-3-small"
        assert config["embedding"]["dimension"] == 1536
        assert config["workers"]["worker_lease_sec"] > 0

    @pytest.mark.asyncio
    async def test_stats_empty(self, client: httpx.AsyncClient):
        response = await client.get("/stats")
        assert response.status_code == 200
        assert response.json()["documents"]["total"] == 0


class TestRecordAndRetrieve:
    @pytest.mark.asyncio
    async def test_record_and_retrieve_basic(self, client: httpx.AsyncClient, process_queue):
        await record_and_process(
            client,
            process_queue,
            [
                {
                    "source": "test",
                    "title": "Authentication Guide",
                    "content": "Authentication requires an API key in the Authorization header.",
                    "tags": ["auth", "api"],
                },
                {
                    "source": "test",
                    "title": "Rate Limits",
                    "content": "Requests are limited to 100 per minute.",
                    "tags": ["limits", "api"],
                },
            ],
        )

        response = await client.post(
            "/retrieve",
            json={"goal": "Authentication requires an API key in the Authorization header.", "k": 2},
        )
        assert response.status_code == 200

        snippets = response.json()["snippets"]
        assert len(snippets) == 2
        assert snippets[0]["title"] == "Authentication Guide"

    @pytest.mark.asyncio
    async def test_retrieve_filters_by_tags_and_op_key(
        self,
        client: httpx.AsyncClient,
        process_queue,
    ):
        await record_and_process(
            client,
            process_queue,
            [
                {
                    "source": "test",
                    "title": "Create User",
                    "op_key": "create_user",
                    "content": "POST /users creates a user.",
                    "tags": ["users", "api"],
                },
                {
                    "source": "test",
                    "title": "Delete User",
                    "op_key": "delete_user",
                    "content": "DELETE /users/{id} deletes a user.",
                    "tags": ["users", "dangerous"],
                },
            ],
        )

        by_tag = await client.post("/retrieve", json={"goal": "user", "tags": ["api"], "k": 5})
        assert by_tag.status_code == 200
        assert [snippet["title"] for snippet in by_tag.json()["snippets"]] == ["Create User"]

        by_op = await client.post(
            "/retrieve",
            json={"goal": "delete a user", "op_key": "delete_user", "k": 5},
        )
        assert by_op.status_code == 200
        snippets = by_op.json()["snippets"]
        assert len(snippets) == 1
        assert snippets[0]["op_key"] == "delete_user"

    @pytest.mark.asyncio
    async def test_retrieve_truncates_content(self, client: httpx.AsyncClient, process_queue):
        await record_and_process(
            client,
            process_queue,
            [
                {
                    "source": "test",
                    "title": "Long Doc",
                    "content": "x" * 5000,
                    "tags": ["long"],
                }
            ],
        )

        response = await client.post("/retrieve", json={"goal": "x", "k": 1})
        assert response.status_code == 200
        snippet = response.json()["snippets"][0]
        assert len(snippet["content"]) == 1200

    @pytest.mark.asyncio
    async def test_retrieve_rejects_invalid_k(self, client: httpx.AsyncClient):
        response = await client.post("/retrieve", json={"goal": "x", "k": 0})
        assert response.status_code == 422


class TestDocuments:
    @pytest.mark.asyncio
    async def test_documents_cycle(self, client: httpx.AsyncClient, process_queue):
        await record_and_process(
            client,
            process_queue,
            [
                {
                    "source": "md",
                    "title": "One",
                    "content": "Alpha",
                    "tags": ["alpha", "shared"],
                },
                {
                    "source": "md",
                    "title": "Two",
                    "content": "Beta",
                    "tags": ["beta", "shared"],
                },
            ],
        )

        listed = await client.get("/documents?source=md&tags=shared&limit=10")
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["total"] == 2
        doc_id = payload["documents"][0]["id"]

        fetched = await client.get(f"/documents/{doc_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == doc_id

        deleted = await client.delete(f"/documents/{doc_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True

        missing = await client.get(f"/documents/{doc_id}")
        assert missing.status_code == 404

    @pytest.mark.asyncio
    async def test_documents_reject_invalid_limit(self, client: httpx.AsyncClient):
        response = await client.get("/documents?limit=0")
        assert response.status_code == 422


class TestVotingAndLogging:
    @pytest.mark.asyncio
    async def test_vote_and_log_flow(self, client: httpx.AsyncClient, process_queue):
        await record_and_process(
            client,
            process_queue,
            [
                {
                    "source": "test",
                    "title": "Helpful Doc",
                    "content": "This doc can be voted on.",
                    "tags": ["vote"],
                }
            ],
        )
        doc_id = (await client.get("/documents")).json()["documents"][0]["id"]

        vote = await client.post("/vote", json={"doc_id": doc_id, "increment": 2})
        assert vote.status_code == 200
        assert vote.json()["vote_count"] == 2

        logged = await client.post(
            "/log",
            json={"op_key": "chat::session", "doc_ids": [doc_id], "status": 200, "latency_ms": 45},
        )
        assert logged.status_code == 200
        assert logged.json()["logged"] == 1

        logs = await client.get("/logs?op_key=chat::session&limit=10")
        assert logs.status_code == 200
        payload = logs.json()
        assert payload["total"] == 1
        assert payload["logs"][0]["doc_id"] == doc_id

    @pytest.mark.asyncio
    async def test_vote_rejects_negative_increment(self, client: httpx.AsyncClient):
        response = await client.post("/vote", json={"doc_id": 1, "increment": -1})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_vote_rejects_missing_document(self, client: httpx.AsyncClient):
        response = await client.post("/vote", json={"doc_id": 9999, "increment": 1})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_logs_reject_invalid_timestamp(self, client: httpx.AsyncClient):
        response = await client.get("/logs?start_time=not-a-timestamp")
        assert response.status_code == 400


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_complete_rag_workflow(self, client: httpx.AsyncClient, process_queue):
        await record_and_process(
            client,
            process_queue,
            [
                {
                    "source": "test",
                    "title": "Create Orders",
                    "op_key": "create_order",
                    "content": "POST /orders creates a new order with line items.",
                    "tags": ["orders", "api"],
                },
                {
                    "source": "test",
                    "title": "Order Authentication",
                    "content": "You must send a bearer token before creating orders.",
                    "tags": ["orders", "auth"],
                },
            ],
        )

        retrieval = await client.post(
            "/retrieve",
            json={"goal": "how do I create an authenticated order", "k": 2},
        )
        assert retrieval.status_code == 200
        snippets = retrieval.json()["snippets"]
        assert len(snippets) == 2

        log_response = await client.post(
            "/log",
            json={
                "op_key": "workflow::1",
                "doc_ids": [snippet["id"] for snippet in snippets],
                "status": 200,
                "latency_ms": 80,
            },
        )
        assert log_response.status_code == 200
        assert log_response.json()["logged"] == 2

        vote_response = await client.post(
            "/vote",
            json={"doc_id": snippets[0]["id"], "increment": 1},
        )
        assert vote_response.status_code == 200

        now = dt.datetime.now(dt.timezone.utc)
        start = (now - dt.timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        end = now.isoformat().replace("+00:00", "Z")
        logs = await client.get(f"/logs?op_key=workflow::1&start_time={start}&end_time={end}")
        assert logs.status_code == 200
        assert logs.json()["total"] == 2

        stats = await client.get("/stats")
        assert stats.status_code == 200
        payload = stats.json()
        assert payload["documents"]["total"] == 2
        assert payload["searches"]["total"] == 2
        assert payload["engagement"]["total_votes"] == 1
