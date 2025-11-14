from __future__ import annotations
from typing import Optional, List
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, ARRAY, Integer, BigInteger, TIMESTAMP, func
from pgvector.sqlalchemy import Vector
from datetime import datetime

EMBEDDING_DIM = 1536  # keep consistent with migration

class Base(DeclarativeBase):
    pass

class CtxDoc(Base):
    __tablename__ = "ctx_doc"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False)   # openapi|graphql|postman|md|...
    op_key: Mapped[Optional[str]] = mapped_column(String(256))
    title: Mapped[Optional[str]] = mapped_column(String(256))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), default=[])
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

class IngestQueue(Base):
    __tablename__ = "ingest_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    op_key: Mapped[Optional[str]] = mapped_column(String(256))
    title: Mapped[Optional[str]] = mapped_column(String(256))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), default=[])
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|processing|done|error
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class ToolLog(Base):
    __tablename__ = "tool_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    op_key: Mapped[Optional[str]] = mapped_column(String(256))
    doc_id: Mapped[Optional[int]] = mapped_column(BigInteger)  # references ctx_doc.id (not strict FK)
    status: Mapped[Optional[int]] = mapped_column(Integer)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    # Timestamp for when the log entry was created
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

class DocVote(Base):
    """Permanent boost votes - when user marks a doc as 'good'"""
    __tablename__ = "doc_vote"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # references ctx_doc.id
    vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # cumulative positive votes
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

class DocUsageBoost(Base):
    """Temporary boost from search usage - ages off over time"""
    __tablename__ = "doc_usage_boost"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # references ctx_doc.id
    boost_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # number of times returned in search
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)  # when this boost expires
