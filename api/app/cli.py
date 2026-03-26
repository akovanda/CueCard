from __future__ import annotations

import argparse
import asyncio
import glob
import os
from typing import Optional

from tqdm import tqdm

from .db.models import CtxDoc
from .db.session import session_scope
from .embedding import embed_texts
from .settings import load_settings


async def ingest_md(path: str, op_key: Optional[str], tags: list[str]):
    settings = load_settings()
    files = sorted(glob.glob(os.path.join(path, "**/*.md"), recursive=True)) or sorted(
        glob.glob(os.path.join(path, "*.md"))
    )
    if not files:
        print(f"No markdown files found under {path}")
        return

    rows = []
    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
            if not content:
                continue
            rows.append(("md", op_key, os.path.basename(file_path), content, tags))

    embeddings = embed_texts([row[3] for row in rows], settings=settings)

    async with session_scope(settings) as session:
        docs = [
            CtxDoc(
                source=row[0],
                op_key=row[1],
                title=row[2],
                content=row[3],
                tags=row[4],
                embedding=embedding,
            )
            for row, embedding in zip(rows, embeddings)
        ]
        chunk_size = 128
        for i in tqdm(range(0, len(docs), chunk_size), desc="ingest-md"):
            session.add_all(docs[i:i + chunk_size])
            await session.commit()

    print(f"Ingested {len(rows)} markdown files.")


def main():
    ap = argparse.ArgumentParser(prog="ctx")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_md = sub.add_parser("ingest-md", help="Ingest markdown snippets")
    ap_md.add_argument("--md", required=True, help="Path to folder or file(s)")
    ap_md.add_argument("--op-key", default=None, help="Operation key to associate")
    ap_md.add_argument("--tag", action="append", default=[], help="Repeatable tag")

    args = ap.parse_args()
    if args.cmd == "ingest-md":
        asyncio.run(ingest_md(args.md, args.op_key, args.tag))


if __name__ == "__main__":
    main()
