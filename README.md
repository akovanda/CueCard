# CueCard (v0.2)

A tiny sidecar that ingests docs and snippets (Markdown today; OpenAPI next), stores chunks in
Postgres + pgvector, and retrieves the top‑K relevant snippets to inject into an LLM
tool-use prompt right before an API call.

## What's included
- Dockerized stack: Postgres (with pgvector), API service (FastAPI), Alembic migrations
- SQLAlchemy 2.0 ORM, Psycopg 3 driver, `pgvector` SQLAlchemy type
- Deterministic local embeddings fallback (works without API keys)
- CLI to ingest Markdown: `ingest-md`
- **Complete RAG API endpoints:**
  - `/retrieve` - Get the best K snippets by semantic search (+ optional filters)
  - `/record` - Queue items for async ingestion
  - `/documents` - List, get, and delete documents
  - `/vote` - Vote for helpful snippets (permanent boost)
  - `/log` - Log retrieval usage for analytics
  - `/stats` - System statistics and usage metrics
  - `/config` - View current configuration
- Voting/boosting system for ranking snippets based on user feedback and usage
- Comprehensive test suite with pytest
- Example code for RAG integration (chatbot, OpenAPI ingestion)

## Quick start
```bash
# 0) Copy the sample env and edit as needed (URLs/keys)
cp .env.example .env

# 1) Build and run
docker compose up -d --build

# 2) Ingest sample docs
docker compose exec api python -m app.cli ingest-md --md /data/docs --tag howto --tag gotcha

# 3) Retrieve context
curl -s http://localhost:8000/retrieve -H "Content-Type: application/json"   -d '{"goal":"how do I page through orders","op_key":null,"role":"support_agent","k":3}' | jq

# 4) Vote for a snippet as "good" (permanent boost)
curl -s http://localhost:8000/vote -H "Content-Type: application/json" -d '{"doc_id":1,"increment":1}' | jq

# 5) View system stats
curl -s http://localhost:8000/stats | jq

# 6) List documents
curl -s "http://localhost:8000/documents?limit=10" | jq
```

> **Note:** If `OPENAI_API_KEY` is set in `.env`, real embeddings are used.
> Otherwise a deterministic local fallback is used so demos/tests work offline.

## Design
- **DB:** Postgres with `pgvector`, maintained via **Alembic** migrations.
- **Models:** SQLAlchemy 2.0 (see `api/app/db/models.py`).
- **Migrations:** `api/alembic` with an initial revision creating `ctx_doc` and HNSW index.
- **Service:** FastAPI app with complete RAG endpoints (see API reference below) and CLI (`ingest-md`).
- **Voting/Boosting:**
  - **Permanent boosts**: Users can vote for snippets via `/vote` endpoint. Each vote increments a permanent boost counter.
  - **Temporary boosts**: Each time a snippet is returned in search results, it receives a tiny temporary boost that expires after a configurable period (default: 14 days).
  - **Background cleanup**: A background task periodically removes expired temporary boosts.

## API Reference

### Core RAG Endpoints
- `GET /health` - Health check
- `POST /retrieve` - Retrieve relevant snippets (main RAG operation)
- `POST /record` - Queue documents for async ingestion
- `POST /log` - Log retrieval usage for analytics
- `POST /vote` - Vote for helpful snippets

### Document Management
- `GET /documents` - List documents with filtering (source, op_key, tags)
- `GET /documents/{id}` - Get specific document details
- `DELETE /documents/{id}` - Delete a document

### Analytics & Configuration
- `GET /stats` - System usage statistics
- `GET /config` - Current configuration settings

For detailed API documentation and integration patterns, see [RAG-GUIDE.md](RAG-GUIDE.md).

## Environment variables (see `.env.example`)
All URLs and passwords are provided via environment variables. The compose file reads `.env` and
passes it to containers. Users should only need to edit `.env`.

Key configuration categories:
- **Database**: PostgreSQL connection settings
- **Embeddings**: Provider (OpenAI/local), model, dimensions
- **Retrieval**: Reranking weights, overfetch settings
- **Ranking**: Vote boost weight, usage boost weight and TTL
- **Workers**: Background processing intervals and batch sizes

See `.env.example` for all available options with descriptions.

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
docker compose exec api pytest -v

# Run specific test class
docker compose exec api pytest -v -k TestRetrieveEndpoint

# Run with coverage
docker compose exec api pytest --cov=app
```

## Examples

See the `examples/` directory for:
- **RAG Chatbot Example**: Complete workflow from ingestion to retrieval to feedback
- **OpenAPI Ingestion Example**: Parse and ingest API specifications
- **Integration Patterns**: Best practices for using CueCard in your RAG pipeline

Run examples:
```bash
python examples/rag_chatbot_example.py
python examples/openapi_ingestion_example.py
```

## Roadmap
- ✅ Complete RAG API endpoints
- ✅ Comprehensive testing infrastructure
- ✅ Documentation and examples
- OpenAPI/GraphQL/Postman ingestion (examples provided, CLI coming soon)
- Goal-aware summarization to enforce a 1–2KB snippet budget
- GitHub Actions to build and publish an image to GHCR
