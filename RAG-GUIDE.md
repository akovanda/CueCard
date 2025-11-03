# RAG (Retrieval-Augmented Generation) Integration Guide

This guide shows how to integrate CueCard into your RAG-powered application.

## Overview

CueCard provides a complete RAG backend that:
- **Ingests** documentation, API specs, and other content
- **Embeds** content using OpenAI or local embeddings
- **Retrieves** the most relevant snippets for any query
- **Ranks** results using semantic similarity + user feedback + usage patterns
- **Tracks** usage and learns from feedback over time

## Quick Start

### 1. Setup Environment

```bash
# Copy and configure environment
cp .env.example .env

# Edit .env to configure:
# - Database credentials
# - Embedding provider (OpenAI or local)
# - Ranking/retrieval parameters
```

### 2. Start the Service

```bash
# Start all services (database, migrations, API)
docker compose up -d --build

# Check health
curl http://localhost:8000/health
```

### 3. Ingest Your Documentation

```bash
# Ingest markdown files
docker compose exec api python -m app.cli ingest-md \
  --md /data/docs \
  --tag product-docs \
  --tag v2.0

# Or use the API to queue items
curl -X POST http://localhost:8000/record \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "source": "md",
        "title": "Authentication Guide",
        "content": "To authenticate, include the API key in the Authorization header...",
        "tags": ["auth", "security"]
      }
    ]
  }'
```

## API Reference

### Core RAG Endpoints

#### POST /retrieve
Retrieve the most relevant snippets for a query (the core RAG retrieval operation).

**Request:**
```json
{
  "goal": "how do I authenticate API requests",
  "op_key": "authenticate_user",      // optional: filter by operation
  "role": "developer",                // optional: influences ranking
  "tags": ["auth", "security"],       // optional: filter by tags
  "k": 5                              // number of results (default: 5)
}
```

**Response:**
```json
{
  "snippets": [
    {
      "id": 42,
      "source": "md",
      "op_key": "authenticate_user",
      "title": "Authentication Guide",
      "content": "To authenticate, include the API key..."
    }
  ]
}
```

**Usage in RAG Pipeline:**
```python
import httpx

async def get_context_for_llm(user_question: str) -> str:
    """Retrieve relevant context to inject into LLM prompt"""
    response = await httpx.post(
        "http://localhost:8000/retrieve",
        json={
            "goal": user_question,
            "k": 3  # Get top 3 most relevant snippets
        }
    )
    snippets = response.json()["snippets"]
    
    # Format for LLM context
    context = "\n\n".join([
        f"[{s['title']}]\n{s['content']}"
        for s in snippets
    ])
    return context

# Use in your LLM prompt
question = "How do I authenticate?"
context = await get_context_for_llm(question)
prompt = f"""
Context:
{context}

Question: {question}

Answer:
"""
```

#### POST /record
Queue items for ingestion (async processing).

**Request:**
```json
{
  "items": [
    {
      "source": "openapi",
      "op_key": "create_order",
      "title": "Create Order API",
      "content": "POST /orders - Creates a new order...",
      "tags": ["api", "orders"]
    }
  ]
}
```

**Response:**
```json
{
  "queued": [101, 102, 103]  // IDs of queued items
}
```

#### POST /log
Log retrieval usage (used for analytics and ranking).

**Request:**
```json
{
  "op_key": "create_order",
  "doc_ids": [42, 43],
  "status": 200,              // HTTP status of operation
  "latency_ms": 150
}
```

#### POST /vote
Vote for a snippet as helpful (permanent boost).

**Request:**
```json
{
  "doc_id": 42,
  "increment": 1  // positive for upvote, negative for downvote
}
```

### Document Management Endpoints

#### GET /documents
List all documents with optional filtering.

**Query Parameters:**
- `source`: Filter by source type (md, openapi, etc.)
- `op_key`: Filter by operation key
- `tags`: Comma-separated tags to filter by
- `limit`: Max results (default: 100)
- `offset`: Pagination offset (default: 0)

**Example:**
```bash
curl "http://localhost:8000/documents?source=md&tags=auth&limit=10"
```

#### GET /documents/{id}
Get full details of a specific document.

**Example:**
```bash
curl http://localhost:8000/documents/42
```

#### DELETE /documents/{id}
Delete a document and all associated data.

**Example:**
```bash
curl -X DELETE http://localhost:8000/documents/42
```

### Analytics Endpoints

#### GET /stats
Get system usage statistics.

**Response:**
```json
{
  "documents": {
    "total": 150,
    "by_source": {
      "md": 100,
      "openapi": 50
    }
  },
  "queue": {
    "queued": 5,
    "processing": 2,
    "done": 1000
  },
  "searches": {
    "total": 5000,
    "successful": 4800
  },
  "engagement": {
    "total_votes": 250,
    "active_boosts": 75
  }
}
```

#### GET /config
Get current system configuration.

**Response:**
```json
{
  "embedding": {
    "provider": "openai",
    "model": "text-embedding-3-small",
    "dimension": 1536
  },
  "retrieval": {
    "rerank_weight": 0.1,
    "retrieval_overfetch": 8
  },
  "ranking": {
    "vote_boost_weight": 1.0,
    "usage_boost_weight": 0.01,
    "usage_boost_ttl_days": 14
  }
}
```

## Integration Patterns

### Pattern 1: LLM Tool Augmentation

Use CueCard to provide context for LLM function/tool calls:

```python
async def handle_llm_tool_call(tool_name: str, args: dict):
    # 1. Retrieve relevant documentation
    context = await httpx.post("http://localhost:8000/retrieve", json={
        "goal": f"How to use {tool_name}",
        "op_key": tool_name,
        "k": 2
    })
    
    # 2. Execute tool with context
    result = await execute_tool(tool_name, args, context=context)
    
    # 3. Log the usage
    await httpx.post("http://localhost:8000/log", json={
        "op_key": tool_name,
        "doc_ids": [s["id"] for s in context.json()["snippets"]],
        "status": 200 if result.success else 500
    })
    
    return result
```

### Pattern 2: Q&A Chatbot

Build a documentation chatbot:

```python
async def answer_question(question: str):
    # 1. Retrieve relevant docs
    response = await httpx.post("http://localhost:8000/retrieve", json={
        "goal": question,
        "k": 5
    })
    snippets = response.json()["snippets"]
    
    # 2. Build LLM prompt with retrieved context
    context = "\n\n".join([s["content"] for s in snippets])
    prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    
    # 3. Get LLM response
    answer = await call_llm(prompt)
    
    # 4. Log successful retrieval
    await httpx.post("http://localhost:8000/log", json={
        "doc_ids": [s["id"] for s in snippets],
        "status": 200
    })
    
    return answer
```

### Pattern 3: User Feedback Loop

Learn from user feedback:

```python
async def handle_user_feedback(doc_id: int, helpful: bool):
    # User indicates if a retrieved snippet was helpful
    if helpful:
        await httpx.post("http://localhost:8000/vote", json={
            "doc_id": doc_id,
            "increment": 1
        })
```

### Pattern 4: Batch Document Ingestion

Ingest documentation at scale:

```python
async def ingest_api_documentation(openapi_spec: dict):
    items = []
    for path, methods in openapi_spec["paths"].items():
        for method, details in methods.items():
            items.append({
                "source": "openapi",
                "op_key": details.get("operationId"),
                "title": f"{method.upper()} {path}",
                "content": details.get("description", ""),
                "tags": details.get("tags", [])
            })
    
    # Queue all items for async processing
    await httpx.post("http://localhost:8000/record", json={
        "items": items
    })
```

## Configuration Tuning

### Embedding Configuration

**Use OpenAI embeddings for best quality:**
```bash
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=sk-...
```

**Use local embeddings for offline/testing:**
```bash
EMBEDDING_PROVIDER=local
```

### Ranking Configuration

**Adjust ranking weights:**
```bash
# Permanent votes (user feedback)
VOTE_BOOST_WEIGHT=1.0

# Temporary usage boosts (popularity)
USAGE_BOOST_WEIGHT=0.01

# Success rate boost
RERANK_WEIGHT=0.1
```

**Tune retrieval:**
```bash
# Fetch more candidates before reranking
RETRIEVAL_OVERFETCH=8
```

## Monitoring

### Check System Health

```bash
curl http://localhost:8000/health
```

### View Statistics

```bash
curl http://localhost:8000/stats | jq
```

### View Configuration

```bash
curl http://localhost:8000/config | jq
```

### Monitor Ingestion Queue

```bash
# Check queue status in stats
curl http://localhost:8000/stats | jq '.queue'
```

## Best Practices

1. **Tag Everything**: Use tags to enable filtering and improve retrieval
2. **Log Usage**: Always log retrieval usage to improve ranking over time
3. **Collect Feedback**: Implement voting to learn which snippets are most helpful
4. **Filter by Context**: Use `op_key` and `tags` to narrow results for specific use cases
5. **Monitor Queue**: Check queue stats to ensure ingestion keeps up with demand
6. **Tune Weights**: Adjust boost weights based on your use case (docs vs API specs vs code)

## Troubleshooting

### Slow Retrievals
- Check `RETRIEVAL_OVERFETCH` (lower = faster but less accurate)
- Ensure database has proper indexes (migrations handle this)
- Consider using local embeddings for testing

### Queue Backlog
- Increase `WORKER_BATCH` to process more items at once
- Decrease `WORKER_POLL_SEC` to check queue more frequently
- Check for errors in queue items: `curl http://localhost:8000/stats | jq '.queue'`

### Poor Retrieval Quality
- Switch to OpenAI embeddings if using local
- Increase `k` to get more results
- Add more specific tags to documents
- Use `op_key` to filter results
- Collect user feedback via voting

## Examples

See `examples/` directory for:
- Sample markdown documentation
- Integration code samples
- OpenAPI ingestion scripts
