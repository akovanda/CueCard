# CueCard Examples

This directory contains example code and documentation showing how to use CueCard for RAG (Retrieval-Augmented Generation).

## Running the Examples

### Prerequisites

Make sure CueCard is running:

```bash
# From the repository root
cp .env.example .env
docker compose up -d --build
```

### Install Python Dependencies for Examples

```bash
pip install httpx pyyaml
```

## Example Scripts

### 1. RAG Chatbot Example (`rag_chatbot_example.py`)

Demonstrates a complete RAG workflow for a chatbot:
- Ingesting documentation
- Retrieving relevant context for user questions
- Using context with an LLM (simulated)
- Logging usage statistics
- Collecting user feedback

**Run it:**
```bash
python rag_chatbot_example.py
```

**What it shows:**
- How to use `/record` to ingest documents
- How to use `/retrieve` to get relevant context
- How to format context for LLM prompts
- How to use `/log` to track usage
- How to use `/vote` to collect feedback
- How to use `/stats` to monitor the system

### 2. Chat History Example (`chat_history_example.py`)

Shows how to query raw logs by timestamp and op_key to render a chatbot session timeline.
It demonstrates using `/log` to associate events with a `SESSION_OP_KEY`, then `/logs` to fetch
those events within a time window.

**Run it:**
```bash
python chat_history_example.py
```

**What it shows:**
- How to tag a chat session with `op_key` (e.g. `chat::session-<id>`) and log usage
- How to query `/logs` with `start_time`, `end_time`, `op_key`, and pagination
- How to render a simple event list for UI display

### 3. OpenAPI Ingestion Example (`openapi_ingestion_example.py`)

Shows how to ingest OpenAPI specifications for API documentation RAG:
- Parsing OpenAPI/Swagger specs
- Converting operations to CueCard documents
- Filtering by operation key and tags
- Testing retrieval for API-specific queries

**Run it:**
```bash
python openapi_ingestion_example.py
```

**What it shows:**
- How to parse and structure OpenAPI specs
- How to use `op_key` for operation-specific filtering
- How to use tags for categorization
- How to test RAG retrieval for API documentation

## Sample Documentation

The `docs/` directory contains sample markdown files that can be ingested using the CLI:

```bash
# Ingest sample docs
docker compose exec api python -m app.cli ingest-md \
  --md /data/docs \
  --tag example \
  --tag documentation
```

## Manual Testing with cURL

### Health Check
```bash
curl http://localhost:8000/health
```

### View Configuration
```bash
curl http://localhost:8000/config | jq
```

### Ingest a Document
```bash
curl -X POST http://localhost:8000/record \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "source": "md",
        "title": "Test Doc",
        "content": "This is a test document.",
        "tags": ["test"]
      }
    ]
  }'
```

### Retrieve Context
```bash
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "test document",
    "k": 3
  }' | jq
```

### List Documents
```bash
curl "http://localhost:8000/documents?limit=10" | jq
```

### Get Document Details
```bash
curl http://localhost:8000/documents/1 | jq
```

### Vote for a Document
```bash
curl -X POST http://localhost:8000/vote \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": 1,
    "increment": 1
  }' | jq
```

### View Statistics
```bash
curl http://localhost:8000/stats | jq
```

### Delete a Document
```bash
curl -X DELETE http://localhost:8000/documents/1 | jq
```

## Integration Patterns

See `../RAG-GUIDE.md` for detailed integration patterns including:
- LLM tool augmentation
- Q&A chatbots
- User feedback loops
- Batch document ingestion
- Configuration tuning

## Tips

1. **Wait for Ingestion**: After calling `/record`, wait a few seconds for background processing before retrieving
2. **Use Tags**: Always tag documents for better filtering and organization
3. **Track Everything**: Use `/log` to track all retrievals for analytics and ranking improvements
4. **Collect Feedback**: Use `/vote` to learn which snippets are most helpful
5. **Monitor Stats**: Check `/stats` regularly to monitor system health and usage
