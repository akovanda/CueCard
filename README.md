# CueCard

[![CI](https://github.com/akovanda/CueCard/actions/workflows/ci.yml/badge.svg)](https://github.com/akovanda/CueCard/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/akovanda/CueCard?sort=semver)](https://github.com/akovanda/CueCard/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A sidecar retrieval service for LLM applications. CueCard ingests docs and snippets,
stores embeddings in Postgres + pgvector, and returns the best matching context right
before a model call or tool execution.

## What’s included
- FastAPI API with typed responses for retrieval, ingestion, analytics, and document management
- Dedicated worker process for queue ingestion and expired usage-boost cleanup
- Alembic migrations and pgvector-backed search in Postgres
- Deterministic local embeddings fallback for offline development and tests
- Simple API-key auth, CORS configuration, and secure-by-default deploy examples
- CLI Markdown ingestion with `python -m app.cli ingest-md`
- Containerized tests, Helm chart, static Kubernetes manifests, and CI workflows
- Automatic patch releases from `main`, with GHCR image publishing and GitHub Releases
- Working examples for chatbot retrieval, chat-history timelines, and OpenAPI ingestion

## Quick start
```bash
# 0) Copy the sample env
cp .env.example .env

# 1) Build and run
docker compose up -d --build

# 2) Ingest sample docs
docker compose exec api python -m app.cli ingest-md --md /data/docs --tag howto --tag gotcha

# 3) Retrieve context
curl -s http://localhost:8000/retrieve \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{"goal":"how do I page through orders","role":"support_agent","k":3}' | jq

# 4) Log usage and vote on a helpful result
curl -s -X POST http://localhost:8000/log \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{"op_key":"chat::session-123","doc_ids":[1,2],"status":200,"latency_ms":80}' | jq

curl -s http://localhost:8000/vote \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{"doc_id":1,"increment":1}' | jq
```

> **Note:** If `OPENAI_API_KEY` is set in `.env`, real embeddings are used.
> Otherwise a deterministic local fallback is used so demos/tests work offline.
> Embedding dimension is derived from `EMBEDDING_MODEL` and validated against the database schema on startup.
> The sample `.env.example` also enables API key auth with `X-API-Key: change-me`; rotate that value before shared use.

## Core endpoints
- `GET /health`
- `POST /retrieve`
- `POST /record`
- `POST /log`
- `POST /vote`
- `GET /logs`
- `GET /documents`
- `GET /documents/{id}`
- `DELETE /documents/{id}`
- `GET /stats`
- `GET /config`

## Retrieval model
- Retrieval is vector-first, then re-ranked with optional usage and vote boosts.
- `/record` is asynchronous: the API queues work and the worker writes embeddings/doc rows.
- `/log` records which documents were actually used so ranking can learn from real traffic.
- `/vote` is an explicit positive feedback signal with `increment >= 1`.
- `/config` exposes effective runtime settings but never returns secrets.

## More docs
- [RAG-GUIDE.md](RAG-GUIDE.md): integration patterns and API examples
- [examples/README.md](examples/README.md): runnable example scripts and curl snippets
- [README-DEPLOY.md](README-DEPLOY.md): Helm, Compose sidecar, and production notes
- [CONTRIBUTING.md](CONTRIBUTING.md): local development and test workflow

### /logs endpoint
Use `/logs` to retrieve raw usage events for UIs (e.g., chatbot history) and analytics:

Query params:
- `start_time` (ISO 8601, e.g., `2025-11-13T15:00:00Z`)
- `end_time` (ISO 8601)
- `op_key` (string) – associate logs with a session or operation
- `doc_id` (int) – filter by specific document ID
- `status_min`/`status_max` (int) – filter by status range (e.g., 200–299)
- `limit`/`offset` – pagination

Example:
```bash
curl -s "http://localhost:8000/logs?op_key=chat::session-123&start_time=2025-11-13T15:00:00Z&end_time=2025-11-13T15:30:00Z&limit=50" -H "X-API-Key: change-me" | jq
```
Response shape:
```json
{
  "logs": [
    {"id":1,"op_key":"chat::session-123","doc_id":42,"status":200,"latency_ms":85,"created_at":"2025-11-13T15:05:22.123Z"}
  ],
  "total": 12,
  "limit": 50,
  "offset": 0
}
```

## Examples

See the `examples/` directory for:
- **RAG Chatbot Example**: queue docs, retrieve context, log usage, and vote
- **Chat History Example**: use `/logs` to render a session timeline
- **OpenAPI Ingestion Example**: parse and ingest OpenAPI operations for retrieval

Run examples:
```bash
python examples/rag_chatbot_example.py
python examples/chat_history_example.py
python examples/openapi_ingestion_example.py
```

## Contributing
We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up your environment, run tests, and submit PRs. Be kind and review our [Code of Conduct](CODE_OF_CONDUCT.md).

## Security
If you believe you’ve found a security issue, please follow our [Security Policy](SECURITY.md) for responsible disclosure.

## License
This project is licensed under the MIT License – see [LICENSE](LICENSE) for details.
