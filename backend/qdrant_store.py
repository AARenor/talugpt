from __future__ import annotations

import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, FilterSelector, MatchValue, PointStruct, VectorParams

from .config import settings


_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        kwargs = {"url": settings.qdrant_url}
        if settings.qdrant_api_key:
            kwargs["api_key"] = settings.qdrant_api_key
        _client = QdrantClient(**kwargs)
    return _client


def ensure_collection(vector_size: int = 1024) -> None:
    client = get_client()
    if client.collection_exists(settings.qdrant_collection):
        return
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def replace_document_chunks(
    *,
    document_id: str,
    external_id: str,
    file_name: str,
    source: str,
    chunks: list[str],
    vectors: list[list[float]],
) -> None:
    _validate_vectors(vectors)
    client = get_client()
    ensure_collection(len(vectors[0]))
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(key="external_id", match=MatchValue(value=external_id)),
                ]
            )
        ),
        wait=True,
    )
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{external_id}:{index}")),
            vector=vector,
            payload={
                "document_id": document_id,
                "external_id": external_id,
                "file_name": file_name,
                "source": source,
                "chunk_index": index,
                "text": chunk,
            },
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=False))
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points, wait=True)


def _validate_vectors(vectors: list[list[float]]) -> None:
    if not vectors:
        raise ValueError("Embedding provider returned no vectors.")

    expected_size = len(vectors[0])
    if expected_size == 0:
        raise ValueError("Embedding provider returned an empty vector.")

    for index, vector in enumerate(vectors):
        if len(vector) == 0:
            raise ValueError(f"Embedding provider returned an empty vector at index {index}.")
        if len(vector) != expected_size:
            raise ValueError(
                f"Embedding dimension mismatch at index {index}: expected {expected_size}, got {len(vector)}."
            )


def search_chunks(query_vector: list[float], limit: int) -> list:
    client = get_client()
    ensure_collection(len(query_vector))
    return client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
