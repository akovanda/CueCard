from __future__ import annotations

import asyncio
import sys

import pytest

from app.db import repo
from app.db.session import session_scope


@pytest.mark.asyncio
async def test_cli_ingest_md_happy_path(tmp_path, settings):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "x.md").write_text("Title X\n\nBody X", encoding="utf-8")
    (docs_dir / "y.md").write_text("Title Y\n\nBody Y", encoding="utf-8")

    from app.cli import ingest_md

    await ingest_md(str(docs_dir), op_key="cli_main", tags=["cli", "sample"])

    async with session_scope(settings) as session:
        docs, total = await repo.list_documents(
            session,
            source="md",
            tags=["cli"],
            limit=10,
            offset=0,
        )
        assert total == 2
        assert {doc.title for doc in docs} == {"x.md", "y.md"}


@pytest.mark.asyncio
async def test_cli_ingest_md_empty(tmp_path, capsys):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir(parents=True, exist_ok=True)

    from app.cli import ingest_md

    await ingest_md(str(empty_dir), op_key=None, tags=["none"])

    out = capsys.readouterr().out
    assert "No markdown files found" in out


def test_cli_main_invocation(tmp_path, settings):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "m.md").write_text("Title M\n\nBody M", encoding="utf-8")

    argv = [
        "ctx",
        "ingest-md",
        "--md",
        str(docs_dir),
        "--op-key",
        "cli_main_inv",
        "--tag",
        "cli",
    ]

    old_argv = sys.argv
    try:
        sys.argv = argv
        from app import cli as cli_mod

        cli_mod.main()
    finally:
        sys.argv = old_argv

    async def verify() -> None:
        async with session_scope(settings) as session:
            _docs, total = await repo.list_documents(
                session,
                source="md",
                tags=["cli"],
                limit=10,
                offset=0,
            )
            assert total == 1

    asyncio.run(verify())
