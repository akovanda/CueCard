from __future__ import annotations

import hashlib
import math
import random
from typing import Optional

from .settings import Settings, load_settings


def _norm(values: list[float]) -> list[float]:
    scale = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / scale for value in values]


def embed_texts(texts: list[str], settings: Optional[Settings] = None) -> list[list[float]]:
    settings = settings or load_settings()

    if settings.embedding_provider == "openai":
        from openai import OpenAI

        client = OpenAI()
        response = client.embeddings.create(model=settings.embedding_model, input=texts)
        return [item.embedding for item in response.data]

    out: list[list[float]] = []
    for text in texts:
        seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        vector = [rng.uniform(-1, 1) for _ in range(settings.embedding_dimension)]
        out.append(_norm(vector))
    return out
