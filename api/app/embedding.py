import os, hashlib, math, random
from typing import List

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local").lower()
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM      = int(os.getenv("EMBEDDING_DIM","1536"))

def _norm(v):
    s = math.sqrt(sum(x*x for x in v)) or 1.0
    return [x/s for x in v]

def embed_texts(texts: List[str]) -> List[List[float]]:
    if EMBEDDING_PROVIDER == "openai":
        from openai import OpenAI
        client = OpenAI()
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return [e.embedding for e in resp.data]
    # Deterministic local fallback (no external dependency)
    out = []
    for t in texts:
        seed = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        v = [rng.uniform(-1,1) for _ in range(EMBEDDING_DIM)]
        out.append(_norm(v))
    return out
