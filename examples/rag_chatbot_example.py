#!/usr/bin/env python3
"""
Example: Using CueCard for a RAG-powered chatbot

This example shows how to:
1. Ingest documentation
2. Retrieve relevant context for user questions
3. Use context with an LLM (simulated)
4. Log usage and collect feedback
"""

import asyncio
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
CUECARD_API = "http://localhost:8000"
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")
CUECARD_API_KEY = os.getenv("CUECARD_API_KEY")


def auth_headers() -> dict[str, str]:
    if not CUECARD_API_KEY:
        return {}
    return {API_KEY_HEADER: CUECARD_API_KEY}


async def setup_documentation():
    """Step 1: Ingest sample documentation"""
    print("📚 Ingesting documentation...")
    
    async with httpx.AsyncClient(headers=auth_headers()) as client:
        response = await client.post(f"{CUECARD_API}/record", json={
            "items": [
                {
                    "source": "md",
                    "title": "Authentication",
                    "content": """
                    To authenticate with the API, include your API key in the Authorization header:
                    
                    Authorization: Bearer YOUR_API_KEY
                    
                    You can obtain an API key from your account dashboard.
                    """,
                    "tags": ["auth", "security", "api"]
                },
                {
                    "source": "md",
                    "title": "Rate Limits",
                    "content": """
                    API rate limits:
                    - Free tier: 100 requests/hour
                    - Pro tier: 1000 requests/hour
                    - Enterprise: Unlimited
                    
                    When you hit the rate limit, you'll receive a 429 status code.
                    """,
                    "tags": ["limits", "api"]
                },
                {
                    "source": "md",
                    "title": "Creating Users",
                    "content": """
                    POST /api/v1/users
                    
                    Create a new user account:
                    {
                        "email": "user@example.com",
                        "password": "secure-password",
                        "name": "John Doe"
                    }
                    
                    Returns the created user with a unique ID.
                    """,
                    "tags": ["users", "api"]
                },
                {
                    "source": "md",
                    "title": "Error Handling",
                    "content": """
                    Common error codes:
                    - 400: Bad request (invalid parameters)
                    - 401: Unauthorized (missing or invalid API key)
                    - 403: Forbidden (insufficient permissions)
                    - 404: Not found
                    - 429: Rate limit exceeded
                    - 500: Server error
                    """,
                    "tags": ["errors", "api"]
                }
            ]
        })
        
        if response.status_code == 202:
            queued_ids = response.json()["queued"]
            print(f"✅ Queued {len(queued_ids)} documents for ingestion")
            print("⏳ Waiting for ingestion to complete...")
            await asyncio.sleep(5)  # Wait for background processing
        else:
            print(f"❌ Failed to queue documents: {response.status_code}")


async def retrieve_context(question: str) -> list:
    """Step 2: Retrieve relevant context for a question"""
    print(f"\n🔍 Retrieving context for: '{question}'")
    
    async with httpx.AsyncClient(headers=auth_headers()) as client:
        response = await client.post(f"{CUECARD_API}/retrieve", json={
            "goal": question,
            "k": 3  # Get top 3 most relevant snippets
        })
        
        if response.status_code == 200:
            snippets = response.json()["snippets"]
            print(f"📄 Retrieved {len(snippets)} relevant snippets")
            return snippets
        else:
            print(f"❌ Failed to retrieve: {response.status_code}")
            return []


def format_context_for_llm(snippets: list) -> str:
    """Format retrieved snippets as context for LLM"""
    if not snippets:
        return ""
    
    context_parts = []
    for i, snippet in enumerate(snippets, 1):
        context_parts.append(f"[Source {i}: {snippet['title']}]")
        context_parts.append(snippet['content'])
        context_parts.append("")
    
    return "\n".join(context_parts)


async def simulate_llm_response(question: str, context: str) -> str:
    """Step 3: Simulate using context with an LLM"""
    # In a real application, you would call your LLM API here
    # For this example, we'll just return a simulated response
    
    print("\n🤖 Generating response with LLM (simulated)...")
    print(f"\n--- Context provided to LLM ---")
    print(context[:300] + "..." if len(context) > 300 else context)
    print(f"--- End context ---\n")
    
    # Simulated response
    return f"Based on the documentation, here's what I found about '{question}'..."


async def log_usage(snippets: list, success: bool):
    """Step 4: Log the retrieval usage"""
    if not snippets:
        return
    
    print("\n📊 Logging usage...")
    
    async with httpx.AsyncClient(headers=auth_headers()) as client:
        response = await client.post(f"{CUECARD_API}/log", json={
            "doc_ids": [s["id"] for s in snippets],
            "status": 200 if success else 500,
            "latency_ms": 150
        })
        
        if response.status_code == 200:
            print(f"✅ Logged usage for {len(snippets)} snippets")


async def collect_feedback(snippet_id: int, helpful: bool):
    """Step 5: Collect user feedback"""
    print(f"\n👍 Recording feedback (helpful: {helpful})...")
    
    if not helpful:
        return  # Only record positive feedback in this example
    
    async with httpx.AsyncClient(headers=auth_headers()) as client:
        response = await client.post(f"{CUECARD_API}/vote", json={
            "doc_id": snippet_id,
            "increment": 1
        })
        
        if response.status_code == 200:
            vote_count = response.json()["vote_count"]
            print(f"✅ Snippet now has {vote_count} votes")


async def answer_question(question: str):
    """Complete RAG workflow for answering a question"""
    print("\n" + "="*60)
    print(f"Question: {question}")
    print("="*60)
    
    # 1. Retrieve relevant context
    snippets = await retrieve_context(question)
    
    if not snippets:
        print("❌ No relevant context found")
        return
    
    # 2. Format context for LLM
    context = format_context_for_llm(snippets)
    
    # 3. Generate response (simulated)
    answer = await simulate_llm_response(question, context)
    print(f"\n💬 Answer: {answer}")
    
    # 4. Log usage
    await log_usage(snippets, success=True)
    
    # 5. Simulate user finding the answer helpful
    if snippets:
        await collect_feedback(snippets[0]["id"], helpful=True)


async def show_statistics():
    """Display system statistics"""
    print("\n" + "="*60)
    print("System Statistics")
    print("="*60)
    
    async with httpx.AsyncClient(headers=auth_headers()) as client:
        response = await client.get(f"{CUECARD_API}/stats")
        
        if response.status_code == 200:
            stats = response.json()
            print(f"\n📊 Documents:")
            print(f"  Total: {stats['documents']['total']}")
            for source, count in stats['documents']['by_source'].items():
                print(f"  - {source}: {count}")
            
            print(f"\n📈 Searches:")
            print(f"  Total: {stats['searches']['total']}")
            print(f"  Successful: {stats['searches']['successful']}")
            
            print(f"\n💬 Engagement:")
            print(f"  Total votes: {stats['engagement']['total_votes']}")
            print(f"  Active boosts: {stats['engagement']['active_boosts']}")


async def main():
    """Run the complete example"""
    print("🚀 CueCard RAG Chatbot Example")
    print("="*60)
    
    # Setup: Ingest documentation
    await setup_documentation()
    
    # Example questions
    questions = [
        "How do I authenticate with the API?",
        "What are the rate limits?",
        "How do I create a new user?"
    ]
    
    # Answer each question using RAG
    for question in questions:
        await answer_question(question)
        await asyncio.sleep(1)  # Brief pause between questions
    
    # Show final statistics
    await show_statistics()
    
    print("\n" + "="*60)
    print("✅ Example complete!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
