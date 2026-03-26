from __future__ import annotations

from contextlib import asynccontextmanager
import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..settings import Settings, load_settings


_ENGINE_CACHE: dict[str, AsyncEngine] = {}
_SESSIONMAKER_CACHE: dict[str, async_sessionmaker[AsyncSession]] = {}
_VECTOR_TYPE_PATTERN = re.compile(r"vector\((\d+)\)")


def get_engine(settings: Optional[Settings] = None) -> AsyncEngine:
    settings = settings or load_settings()
    engine = _ENGINE_CACHE.get(settings.database_url)
    if engine is None:
        engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _ENGINE_CACHE[settings.database_url] = engine
    return engine


def get_session_maker(
    settings: Optional[Settings] = None,
) -> async_sessionmaker[AsyncSession]:
    settings = settings or load_settings()
    session_maker = _SESSIONMAKER_CACHE.get(settings.database_url)
    if session_maker is None:
        session_maker = async_sessionmaker(
            bind=get_engine(settings),
            expire_on_commit=False,
        )
        _SESSIONMAKER_CACHE[settings.database_url] = session_maker
    return session_maker


@asynccontextmanager
async def session_scope(settings: Optional[Settings] = None):
    session_maker = get_session_maker(settings)
    async with session_maker() as session:
        yield session


async def dispose_engines() -> None:
    while _ENGINE_CACHE:
        _, engine = _ENGINE_CACHE.popitem()
        await engine.dispose()
    _SESSIONMAKER_CACHE.clear()


async def fetch_embedding_column_dimension(session: AsyncSession) -> Optional[int]:
    stmt = text(
        """
        SELECT format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        WHERE c.relname = 'ctx_doc'
          AND a.attname = 'embedding'
          AND a.attnum > 0
          AND NOT a.attisdropped
        LIMIT 1
        """
    )
    raw_type = (await session.execute(stmt)).scalar_one_or_none()
    if not raw_type:
        return None

    match = _VECTOR_TYPE_PATTERN.search(raw_type)
    if not match:
        return None
    return int(match.group(1))


async def verify_database_compatibility(settings: Optional[Settings] = None) -> None:
    settings = settings or load_settings()
    async with session_scope(settings) as session:
        column_dimension = await fetch_embedding_column_dimension(session)

    if column_dimension is None:
        raise RuntimeError(
            "CueCard schema is not initialized. Run Alembic migrations before starting the API or worker."
        )
    if column_dimension != settings.embedding_dimension:
        raise RuntimeError(
            "Embedding configuration does not match the database schema: "
            f"model {settings.embedding_model!r} expects vector({settings.embedding_dimension}) "
            f"but ctx_doc.embedding is vector({column_dimension})."
        )
