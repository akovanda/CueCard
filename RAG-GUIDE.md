# CueCard Integration Guide

CueCard is a retrieval sidecar for LLM applications. It lets you queue source material, retrieve the most relevant snippets for a prompt or tool call, and feed back usage and votes so ranking improves over time.

## Quick start

```bash
cp .env.example .env
docker compose up -d --build

curl -s http://localhost:8000/health
```

The sample `.env.example` enables API key auth with `X-API-Key: change-me`, so every endpoint except `/health` needs that header unless you override `CUECARD_API_KEY`.

## Common workflow

### 1. Queue source material

```bash
curl -s http://localhost:8000/record \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "source": "md",
        "title": "Authentication Guide",
        "content": "Use a bearer token in the Authorization header.",
        "tags": ["auth", "api"]
      }
    ]
  }'
```

`/record` is asynchronous. The API enqueues items and the worker writes embeddings and documents in the background.

### 2. Retrieve context

```bash
curl -s http://localhost:8000/retrieve \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "How do I authenticate requests?",
    "k": 3
  }' | jq
```

Request fields:
- `goal`: required retrieval query
- `op_key`: optional exact operation filter
- `role`: optional extra query context
- `tags`: optional tag filter
- `k`: number of results, `1..50`

### 3. Log actual usage

```bash
curl -s -X POST http://localhost:8000/log \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "op_key": "chat::session-123",
    "doc_ids": [1, 2],
    "status": 200,
    "latency_ms": 85
  }'
```

Usage logs are part of ranking. They also let you query raw activity later with `/logs`.

### 4. Vote on a useful snippet

```bash
curl -s http://localhost:8000/vote \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": 1,
    "increment": 1
  }'
```

`increment` must be `>= 1`. CueCard currently supports positive feedback only.

## Python integration

```python
import os
import httpx

API_URL = os.getenv("CUECARD_URL", "http://localhost:8000")
API_KEY = os.getenv("CUECARD_API_KEY", "change-me")
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")


def cuecard_headers() -> dict[str, str]:
    return {
        API_KEY_HEADER: API_KEY,
        "Content-Type": "application/json",
    }


async def retrieve_context(question: str, op_key: str | None = None) -> list[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/retrieve",
            headers=cuecard_headers(),
            json={
                "goal": question,
                "op_key": op_key,
                "k": 3,
            },
        )
        response.raise_for_status()
        return response.json()["snippets"]


async def log_usage(snippets: list[dict], session_key: str, status: int = 200) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/log",
            headers=cuecard_headers(),
            json={
                "op_key": session_key,
                "doc_ids": [snippet["id"] for snippet in snippets],
                "status": status,
            },
        )
        response.raise_for_status()
```

## Retrieval patterns

### Tool or function call augmentation

Use `op_key` when you have a stable operation name and want exact narrowing before similarity ranking.

```json
{
  "goal": "How should I create an order?",
  "op_key": "create_order",
  "k": 2
}
```

### Session-aware chat logging

Use a session-scoped `op_key` for `/log` and `/logs`, for example `chat::session-123`. That gives you a queryable timeline without changing retrieval semantics.

### Tag-based narrowing

Use tags when your corpus mixes product docs, internal notes, policies, or API references and you want retrieval limited to a subset.

```json
{
  "goal": "How do rate limits work?",
  "tags": ["api"],
  "k": 3
}
```

## Other endpoints

### `GET /documents`

Lists documents with optional filters:
- `source`
- `op_key`
- `tags` as a comma-separated query parameter
- `limit` in `1..200`
- `offset >= 0`

### `GET /documents/{id}`

Returns the full stored document.

### `DELETE /documents/{id}`

Deletes a document and its associated votes, boosts, and logs.

### `GET /logs`

Queries raw usage events. Useful filters:
- `start_time`
- `end_time`
- `op_key`
- `doc_id`
- `status_min`
- `status_max`
- `limit`
- `offset`

Example:

```bash
START=$(date -u -v-15M '+%Y-%m-%dT%H:%M:%SZ')
END=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

curl -s "http://localhost:8000/logs?op_key=chat::session-123&start_time=$START&end_time=$END&limit=50" \
  -H "X-API-Key: change-me" | jq
```

### `GET /stats`

Returns document counts, queue status, search counts, and engagement totals.

### `GET /config`

Returns effective runtime settings such as embedding model, worker timing, auth-enabled status, and configured header name. Secrets are intentionally omitted.

## Ranking model

CueCard ranks results with:
- vector distance
- optional success-rate reranking
- permanent vote boosts
- temporary usage boosts from recent retrieval activity

The worker periodically cleans up expired usage boosts. Queue items also have lease and retry metadata so abandoned work can be reclaimed safely.

## Operational notes

- The API starts only after database compatibility checks pass.
- Embedding dimension is derived from `EMBEDDING_MODEL` and must match the database schema.
- One deployment should use one embedding dimension at a time.
- CI and local containerized tests run against the same app/worker split used in deployment.

## Related files

- [README.md](README.md): project overview and quick start
- [README-DEPLOY.md](README-DEPLOY.md): deployment paths
- [examples/README.md](examples/README.md): runnable examples
- [compose/compose.cuecard.example.yml](compose/compose.cuecard.example.yml): sidecar compose example
