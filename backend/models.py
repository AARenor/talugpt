from __future__ import annotations

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    document_id: str
    external_id: str
    file_name: str
    chunk_count: int
    characters_indexed: int
    source: str


class Citation(BaseModel):
    document_id: str
    file_name: str
    source: str
    chunk_index: int
    score: float
    snippet: str


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=12)


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]

