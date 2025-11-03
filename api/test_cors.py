import os
import contextlib
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

# We import after setting env within tests

@contextlib.asynccontextmanager
async def lifespan_app(app: FastAPI):
    # Utility if we ever need custom startup/shutdown in this test module
    yield

@pytest.mark.asyncio
async def test_cors_disabled_by_default(monkeypatch):
    # Ensure CORS_ORIGINS unset/empty
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    from app.server import create_app
    app = create_app()
    assert isinstance(app, FastAPI)

    # Preflight should not set CORS headers when disabled
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Simulate browser CORS preflight
        headers = {
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
        }
        resp = await client.options("/retrieve", headers=headers)
        # FastAPI returns 200/204 for OPTIONS depending on route; check header absence
        assert "access-control-allow-origin" not in resp.headers

@pytest.mark.asyncio
async def test_cors_enabled_with_origin(monkeypatch):
    # Enable CORS for a specific origin
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    from app.server import create_app
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        }
        resp = await client.options("/retrieve", headers=headers)
        # When CORS is enabled and origin matches, header should echo origin
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

@pytest.mark.asyncio
async def test_cors_denies_unlisted_origin(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://allowed.example")
    from app.server import create_app
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {
            "Origin": "http://not-allowed.example",
            "Access-Control-Request-Method": "POST",
        }
        resp = await client.options("/retrieve", headers=headers)
        # Origin not listed -> header should not be present
        assert "access-control-allow-origin" not in resp.headers
