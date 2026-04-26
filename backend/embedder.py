from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from .config import settings


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.embed_model)


def embed_query(text: str) -> list[float]:
    return get_model().encode(f"query: {text}", normalize_embeddings=True).tolist()


def embed_passages(texts: list[str]) -> list[list[float]]:
    prefixed = [f"passage: {text}" for text in texts]
    return get_model().encode(prefixed, normalize_embeddings=True, batch_size=16).tolist()

