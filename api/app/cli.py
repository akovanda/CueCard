import argparse, os, glob, asyncio
from tqdm import tqdm
from .db.models import CtxDoc
from .db.session import SessionLocal
from .embedding import embed_texts

async def ingest_md(path: str, op_key: str | None, tags: list[str]):
    files = sorted(glob.glob(os.path.join(path, "**/*.md"), recursive=True)) \
         or sorted(glob.glob(os.path.join(path, "*.md")))
    if not files:
        print(f"No markdown files found under {path}")
        return

    rows = []
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                continue
            title = os.path.basename(fp)
            rows.append(("md", op_key, title, content, tags))

    embs = embed_texts([r[3] for r in rows])

    async with SessionLocal() as session:
        docs = [
            CtxDoc(source=r[0], op_key=r[1], title=r[2], content=r[3], tags=r[4], embedding=e)
            for r, e in zip(rows, embs)
        ]
        CHUNK = 128
        for i in tqdm(range(0, len(docs), CHUNK), desc="ingest-md"):
            session.add_all(docs[i:i + CHUNK])
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
