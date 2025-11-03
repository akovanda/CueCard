#!/usr/bin/env python3
"""
Example: Ingesting OpenAPI documentation for RAG

This example shows how to parse an OpenAPI spec and ingest it
into CueCard for RAG retrieval.
"""

import asyncio
import httpx
import yaml
from typing import Dict, Any


CUECARD_API = "http://localhost:8000"


# Sample OpenAPI spec (simplified)
OPENAPI_SPEC = """
openapi: 3.0.0
info:
  title: Sample API
  version: 1.0.0

paths:
  /users:
    get:
      operationId: listUsers
      summary: List all users
      description: |
        Returns a paginated list of all users in the system.
        
        Use the 'limit' and 'offset' parameters for pagination.
        Maximum limit is 100 users per request.
      tags:
        - users
      parameters:
        - name: limit
          in: query
          schema:
            type: integer
            default: 25
            maximum: 100
        - name: offset
          in: query
          schema:
            type: integer
            default: 0
      responses:
        200:
          description: List of users
    
    post:
      operationId: createUser
      summary: Create a new user
      description: |
        Creates a new user account with email and password.
        
        Email must be unique. Password must be at least 8 characters.
        Returns the created user with a unique ID.
      tags:
        - users
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - email
                - password
              properties:
                email:
                  type: string
                  format: email
                password:
                  type: string
                  minLength: 8
                name:
                  type: string
      responses:
        201:
          description: User created
        400:
          description: Invalid input
  
  /users/{userId}:
    get:
      operationId: getUser
      summary: Get a specific user
      description: |
        Retrieves detailed information about a specific user by ID.
        
        Returns 404 if the user doesn't exist.
      tags:
        - users
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: integer
      responses:
        200:
          description: User details
        404:
          description: User not found
    
    delete:
      operationId: deleteUser
      summary: Delete a user
      description: |
        Permanently deletes a user account.
        
        This action cannot be undone. Requires admin permissions.
      tags:
        - users
        - admin
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: integer
      responses:
        204:
          description: User deleted
        403:
          description: Insufficient permissions
        404:
          description: User not found

  /auth/login:
    post:
      operationId: login
      summary: Authenticate user
      description: |
        Authenticates a user with email and password.
        
        Returns a JWT token valid for 24 hours.
        Include this token in the Authorization header for authenticated requests.
      tags:
        - auth
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - email
                - password
              properties:
                email:
                  type: string
                password:
                  type: string
      responses:
        200:
          description: Login successful
        401:
          description: Invalid credentials
"""


def parse_openapi_operation(
    path: str,
    method: str,
    operation: Dict[str, Any]
) -> Dict[str, Any]:
    """Parse an OpenAPI operation into a CueCard document"""
    
    # Build comprehensive content
    content_parts = [
        f"{method.upper()} {path}",
        "",
        operation.get("summary", ""),
        "",
        operation.get("description", ""),
    ]
    
    # Add parameters info
    if "parameters" in operation:
        content_parts.append("\nParameters:")
        for param in operation["parameters"]:
            content_parts.append(
                f"- {param['name']} ({param.get('in', 'query')}): "
                f"{param.get('description', 'No description')}"
            )
    
    # Add request body info
    if "requestBody" in operation:
        content_parts.append("\nRequest Body:")
        content_parts.append("See schema for required fields")
    
    # Add response info
    if "responses" in operation:
        content_parts.append("\nResponses:")
        for status, response in operation["responses"].items():
            content_parts.append(
                f"- {status}: {response.get('description', 'No description')}"
            )
    
    content = "\n".join(content_parts)
    
    return {
        "source": "openapi",
        "op_key": operation.get("operationId"),
        "title": f"{method.upper()} {path}",
        "content": content,
        "tags": operation.get("tags", [])
    }


async def ingest_openapi_spec(spec_content: str):
    """Parse OpenAPI spec and ingest into CueCard"""
    print("📖 Parsing OpenAPI specification...")
    
    # Parse YAML
    spec = yaml.safe_load(spec_content)
    
    # Extract all operations
    items = []
    for path, path_item in spec.get("paths", {}).items():
        for method in ["get", "post", "put", "patch", "delete"]:
            if method in path_item:
                operation = path_item[method]
                doc = parse_openapi_operation(path, method, operation)
                items.append(doc)
                print(f"  ✓ {doc['title']}")
    
    print(f"\n📚 Ingesting {len(items)} operations...")
    
    # Ingest into CueCard
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{CUECARD_API}/record", json={
            "items": items
        })
        
        if response.status_code == 202:
            queued_ids = response.json()["queued"]
            print(f"✅ Queued {len(queued_ids)} operations")
            print("⏳ Waiting for ingestion...")
            await asyncio.sleep(5)
        else:
            print(f"❌ Failed: {response.status_code}")
            print(response.text)


async def test_retrieval():
    """Test retrieving operations"""
    print("\n" + "="*60)
    print("Testing Retrieval")
    print("="*60)
    
    test_queries = [
        ("How do I create a user?", "createUser"),
        ("How to authenticate?", "login"),
        ("How to delete a user?", "deleteUser"),
    ]
    
    async with httpx.AsyncClient() as client:
        for query, expected_op_key in test_queries:
            print(f"\n🔍 Query: '{query}'")
            
            response = await client.post(f"{CUECARD_API}/retrieve", json={
                "goal": query,
                "k": 3
            })
            
            if response.status_code == 200:
                snippets = response.json()["snippets"]
                print(f"📄 Found {len(snippets)} results:")
                
                for i, snippet in enumerate(snippets, 1):
                    match = "✓" if snippet.get("op_key") == expected_op_key else " "
                    print(f"  [{match}] {snippet['title']}")
                    if snippet.get("op_key") == expected_op_key:
                        print(f"      (Correct match for {expected_op_key})")
            else:
                print(f"❌ Failed: {response.status_code}")


async def test_filtering():
    """Test filtering by operation key and tags"""
    print("\n" + "="*60)
    print("Testing Filtering")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        # Filter by operation key
        print("\n🔍 Filter by op_key='createUser'")
        response = await client.post(f"{CUECARD_API}/retrieve", json={
            "goal": "user",
            "op_key": "createUser",
            "k": 5
        })
        
        if response.status_code == 200:
            snippets = response.json()["snippets"]
            print(f"📄 Found {len(snippets)} results")
            for snippet in snippets:
                print(f"  - {snippet['title']} (op_key: {snippet.get('op_key', 'none')})")
        
        # Filter by tags
        print("\n🔍 Filter by tags=['auth']")
        response = await client.post(f"{CUECARD_API}/retrieve", json={
            "goal": "authentication",
            "tags": ["auth"],
            "k": 5
        })
        
        if response.status_code == 200:
            snippets = response.json()["snippets"]
            print(f"📄 Found {len(snippets)} results")
            for snippet in snippets:
                print(f"  - {snippet['title']}")


async def main():
    """Run the OpenAPI ingestion example"""
    print("🚀 OpenAPI Ingestion Example")
    print("="*60)
    
    # Ingest the OpenAPI spec
    await ingest_openapi_spec(OPENAPI_SPEC)
    
    # Test retrieval
    await test_retrieval()
    
    # Test filtering
    await test_filtering()
    
    print("\n" + "="*60)
    print("✅ Example complete!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
