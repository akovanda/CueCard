from __future__ import annotations

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

os.environ.setdefault("EMBEDDING_PROVIDER", "local")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://ctx:ctx@db:5432/ctx")

from app.db.session import dispose_engines, session_scope, verify_database_compatibility
from app.server import create_app
from app.settings import Settings, load_settings
from app.worker import run_worker_cycle


TRUNCATE_SQL = text(
    """
    TRUNCATE TABLE
        tool_log,
        doc_usage_boost,
        doc_vote,
        ingest_queue,
        ctx_doc
    RESTART IDENTITY
    """
)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return load_settings()


@pytest.fixture(scope="session", autouse=True)
def ensure_database_ready(settings: Settings):
    asyncio.run(verify_database_compatibility(settings))
    yield
    asyncio.run(dispose_engines())


@pytest.fixture(autouse=True)
async def clean_database(settings: Settings):
    async with session_scope(settings) as session:
        await session.execute(TRUNCATE_SQL)
        await session.commit()
    yield
    async with session_scope(settings) as session:
        await session.execute(TRUNCATE_SQL)
        await session.commit()


@pytest.fixture
async def app(settings: Settings):
    yield create_app(settings)


@pytest.fixture
async def client(app, settings: Settings) -> AsyncClient:
    default_headers = {}
    if settings.cuecard_api_key:
        default_headers[settings.api_key_header] = settings.cuecard_api_key

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=default_headers,
    ) as client:
        yield client


@pytest.fixture
def process_queue(settings: Settings):
    async def _process_queue() -> int:
        return await run_worker_cycle(settings)

    return _process_queue
