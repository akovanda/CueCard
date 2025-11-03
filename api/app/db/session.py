import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Connection URL comes from .env via docker-compose
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://ctx:ctxpw@db:5432/ctx")

# Async engine (SQLAlchemy 2.x + Psycopg 3)
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# Session factory for use across the app
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)
