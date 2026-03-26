import json

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_health_is_public(monkeypatch):
    monkeypatch.setenv("CUECARD_API_KEY", "secret")
    from app.server import create_app
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json().get("ok") is True


@pytest.mark.asyncio
async def test_auth_required_when_key_set(monkeypatch):
    monkeypatch.setenv("CUECARD_API_KEY", "secret")
    from app.server import create_app
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing header should be unauthorized for protected endpoints
        resp = await client.post("/retrieve", json={"goal": "x"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_with_correct_header(monkeypatch):
    monkeypatch.setenv("CUECARD_API_KEY", "secret")
    monkeypatch.setenv("API_KEY_HEADER", "X-API-Key")
    from app.server import create_app
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"X-API-Key": "secret"}
        resp = await client.post("/retrieve", headers=headers, json={"goal": "x"})
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_with_custom_header(monkeypatch):
    monkeypatch.setenv("CUECARD_API_KEY", "secret")
    monkeypatch.setenv("API_KEY_HEADER", "X-Custom-Key")
    from app.server import create_app
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/retrieve", headers={"X-API-Key": "secret"}, json={"goal": "x"})
        assert resp.status_code == 401
        resp2 = await client.post("/retrieve", headers={"X-Custom-Key": "secret"}, json={"goal": "x"})
        assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_auth_uses_constant_time_compare(monkeypatch):
    monkeypatch.setenv("CUECARD_API_KEY", "constant-time-secret")
    monkeypatch.setenv("API_KEY_HEADER", "X-API-Key")
    import app.server as server

    compare_calls = []

    def fake_compare_digest(provided: str, expected: str) -> bool:
        compare_calls.append((provided, expected))
        return True

    monkeypatch.setattr(server.secrets, "compare_digest", fake_compare_digest)
    app = server.create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/retrieve",
            headers={"X-API-Key": "constant-time-secret"},
            json={"goal": "x"},
        )
        assert resp.status_code == 200

    assert compare_calls == [("constant-time-secret", "constant-time-secret")]


@pytest.mark.asyncio
async def test_config_never_exposes_secret_values(monkeypatch):
    monkeypatch.setenv("CUECARD_API_KEY", "cuecard-secret-value")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret-value")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://ctx:dbpass@db:5432/ctx")
    from app.server import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/config", headers={"X-API-Key": "cuecard-secret-value"})
        assert resp.status_code == 200
        payload = resp.json()

    serialized = json.dumps(payload)
    assert payload["security"]["auth_enabled"] is True
    assert payload["security"]["api_key_header"] == "X-API-Key"
    assert "openai-secret-value" not in serialized
    assert "dbpass" not in serialized
    assert "cuecard-secret-value" not in serialized
    assert "DATABASE_URL" not in serialized
