import os
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_is_public(monkeypatch):
    monkeypatch.setenv("CUECARD_API_KEY", "secret")
    from app.server import create_app
    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json().get("ok") is True


@pytest.mark.asyncio
async def test_auth_required_when_key_set(monkeypatch):
    monkeypatch.setenv("CUECARD_API_KEY", "secret")
    from app.server import create_app
    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Missing header should be unauthorized for protected endpoints
        resp = await client.post("/retrieve", json={"goal": "x"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_with_correct_header(monkeypatch):
    monkeypatch.setenv("CUECARD_API_KEY", "secret")
    monkeypatch.setenv("API_KEY_HEADER", "X-API-Key")
    from app.server import create_app
    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        headers = {"X-API-Key": "secret"}
        resp = await client.post("/retrieve", headers=headers, json={"goal": "x"})
        # 200 OK or 200-like since backend may return empty results but not unauthorized
        assert resp.status_code in (200, 422)


@pytest.mark.asyncio
async def test_auth_with_custom_header(monkeypatch):
    monkeypatch.setenv("CUECARD_API_KEY", "secret")
    monkeypatch.setenv("API_KEY_HEADER", "X-Custom-Key")
    from app.server import create_app
    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Wrong header name -> unauthorized
        resp = await client.post("/retrieve", headers={"X-API-Key": "secret"}, json={"goal": "x"})
        assert resp.status_code == 401
        # Correct header name -> allowed
        resp2 = await client.post("/retrieve", headers={"X-Custom-Key": "secret"}, json={"goal": "x"})
        assert resp2.status_code in (200, 422)

