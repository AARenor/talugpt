from __future__ import annotations

from .claude_client import answer_question
from .config import settings
from .embedder import embed_query
from .models import Citation, ChatResponse
from .qdrant_store import search_chunks


def chat(query: str, top_k: int | None = None) -> ChatResponse:
    limit = top_k or settings.search_limit
    query_vector = embed_query(query)
    hits = search_chunks(query_vector, limit)

    citations = [
        Citation(
            document_id=hit.payload["document_id"],
            file_name=hit.payload["file_name"],
            source=hit.payload["source"],
            chunk_index=hit.payload["chunk_index"],
            score=float(hit.score),
            snippet=_compact_snippet(hit.payload["text"]),
        )
        for hit in hits
    ]

    if not citations:
        return ChatResponse(
            answer="I don't have any indexed documents yet. Ingest files first, then ask again.",
            citations=[],
        )

    context = "\n\n".join(
        f"[Document {index + 1}] file={citation.file_name} source={citation.source} chunk={citation.chunk_index}\n{citation.snippet}"
        for index, citation in enumerate(citations)
    )
    answer = answer_question(query=query, context=context)
    return ChatResponse(answer=answer, citations=citations)


def _compact_snippet(text: str, max_chars: int = 900) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."

