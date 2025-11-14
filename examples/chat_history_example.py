#!/usr/bin/env python3
"""
Example: Query raw logs by timestamp for chatbot history display

This example demonstrates how a chatbot UI can:
- Use op_key to tag a session (e.g., "chat::session-<id>")
- Retrieve context for each question
- Log usage for analytics and relevance ranking
- Query raw logs by time range and op_key to render a timeline of activity

It uses the new GET /logs endpoint with filters and pagination.
"""
import asyncio
import httpx
from datetime import datetime, timedelta, timezone

CUECARD_API = "http://localhost:8000"
SESSION_OP_KEY = f"chat::session-{int(datetime.now().timestamp())}"


async def ensure_docs():
    """Ingest a small set of docs so retrieval has substance."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{CUECARD_API}/record", json={
            "items": [
                {
                    "source": "md",
                    "title": "Auth Basics",
                    "content": "Use Bearer API key in Authorization header.",
                    "tags": ["auth", "api"],
                },
                {
                    "source": "md",
                    "title": "Rate Limits",
                    "content": "Free=100/h, Pro=1000/h, Enterprise=Unlimited.",
                    "tags": ["limits", "api"],
                },
            ]
        })
        if resp.status_code == 202:
            await asyncio.sleep(3)


async def ask(question: str) -> list:
    """Retrieve context for a question and log usage with op_key scoped to session."""
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CUECARD_API}/retrieve", json={
            "goal": question,
            "op_key": None,
            "k": 3,
        })
        snippets = r.json().get("snippets", []) if r.status_code == 200 else []

        # Log usage for this session (associate logs via op_key)
        await client.post(f"{CUECARD_API}/log", json={
            "op_key": SESSION_OP_KEY,
            "doc_ids": [s["id"] for s in snippets],
            "status": 200 if snippets else 404,
            "latency_ms": 80,
        })
        return snippets


async def show_timeline(start: datetime | None = None, end: datetime | None = None):
    """Query /logs for the session within a time window and print a timeline."""
    # Default to last 15 minutes UTC
    now = datetime.now(timezone.utc)
    st = start or (now - timedelta(minutes=15))
    et = end or now
    start_iso = st.isoformat().replace("+00:00", "Z")
    end_iso = et.isoformat().replace("+00:00", "Z")

    async with httpx.AsyncClient() as client:
        # Filter by op_key and time range
        url = (
            f"{CUECARD_API}/logs?op_key={SESSION_OP_KEY}"
            f"&start_time={start_iso}&end_time={end_iso}&limit=50"
        )
        r = await client.get(url)
        data = r.json() if r.status_code == 200 else {"logs": [], "total": 0}
        logs = data.get("logs", [])
        print("\n=== Chatbot Session Timeline ===")
        print(f"session op_key: {SESSION_OP_KEY}")
        print(f"window: {start_iso} -> {end_iso}")
        print(f"events: {len(logs)} (total={data.get('total')})\n")
        for i, ev in enumerate(reversed(logs), 1):  # oldest first
            ts = ev.get("created_at")
            status = ev.get("status")
            doc = ev.get("doc_id")
            print(f"{i:02d}. [{ts}] status={status} doc_id={doc}")


async def main():
    print("🚀 Chat History Example (using /logs)")
    await ensure_docs()

    # Simulate a short chat session of three questions
    questions = [
        "How do I authenticate?",
        "What are my rate limits?",
        "Any tips for avoiding 429 errors?",
    ]
    for q in questions:
        print(f"\nQ: {q}")
        snippets = await ask(q)
        if snippets:
            print(f"  -> got {len(snippets)} snippets; logged usage")
        else:
            print("  -> no snippets; logged as 404")
        await asyncio.sleep(0.2)

    # Render the timeline for the session
    await show_timeline()
    print("\n✅ Done")


if __name__ == "__main__":
    asyncio.run(main())

