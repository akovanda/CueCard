import asyncio
import sys
import os
import pytest

from app.db.session import SessionLocal
from app.db import repo


@pytest.mark.asyncio
async def test_cli_main_happy_path(tmp_path, monkeypatch):
    # Prepare sample markdown files
    md_dir = tmp_path / "docs"
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / "x.md").write_text("Title X\n\nBody X", encoding="utf-8")
    (md_dir / "y.md").write_text("Title Y\n\nBody Y", encoding="utf-8")

    # Call ingest_md directly to avoid asyncio.run conflicts
    from app.cli import ingest_md
    await ingest_md(str(md_dir), op_key="cli_main", tags=["cli", "sample"])

    # Verify rows
    async with SessionLocal() as session:
        docs, total = await repo.list_documents(session, source="md", tags=["cli"], limit=10, offset=0)
        assert len(docs) >= 2


@pytest.mark.asyncio
async def test_cli_ingest_md_empty(tmp_path, capsys):
    # Directory with no md files
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir(parents=True, exist_ok=True)

    from app.cli import ingest_md
    await ingest_md(str(empty_dir), op_key=None, tags=["none"])

    # Ensure it printed a helpful message and returned without error
    out = capsys.readouterr().out
    assert "No markdown files found" in out


def test_cli_main_invocation(tmp_path, monkeypatch):
    md_dir = tmp_path / "docs2"
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / "m.md").write_text("Title M\n\nBody M", encoding="utf-8")

    argv = [
        "ctx",
        "ingest-md",
        "--md",
        str(md_dir),
        "--op-key",
        "cli_main_inv",
        "--tag",
        "cli",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    from app import cli as cli_mod
    cli_mod.main()

    # Verify at least one doc ingested
    import asyncio as _asyncio
    async def _check():
        async with SessionLocal() as session:
            docs, total = await repo.list_documents(session, source="md", tags=["cli"], limit=10, offset=0)
            assert total >= 1
    _asyncio.run(_check())
