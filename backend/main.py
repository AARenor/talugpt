from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .embedder import embed_passages
from .models import ChatRequest, ChatResponse, IngestResponse
from .parsers import extract_text, split_text
from .qdrant_store import ensure_collection, replace_document_chunks
from .rag import chat


app = FastAPI(title="Drive RAG Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

embed_dir = Path(__file__).resolve().parent.parent / "frontend" / "embed"
if embed_dir.exists():
    app.mount("/embed", StaticFiles(directory=str(embed_dir)), name="embed")

workflow_dir = Path(__file__).resolve().parent.parent / "n8n"
if workflow_dir.exists():
    app.mount("/workflows", StaticFiles(directory=str(workflow_dir)), name="workflows")


@app.on_event("startup")
def startup() -> None:
    ensure_collection()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest/file", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    source: str = "google-drive",
    external_id: str | None = None,
    title: str | None = None,
) -> IngestResponse:
    content = await file.read()
    return _ingest_bytes(
        content=content,
        file_name=title or file.filename or "document",
        content_type=file.content_type,
        source=source,
        external_id=external_id,
    )


@app.post("/ingest/raw", response_model=IngestResponse)
async def ingest_raw(
    request: Request,
    source: str = "google-drive",
    external_id: str | None = None,
    file_name: str = "document",
    content_type: str | None = Header(default=None, alias="Content-Type"),
) -> IngestResponse:
    content = await request.body()
    return _ingest_bytes(
        content=content,
        file_name=file_name,
        content_type=content_type,
        source=source,
        external_id=external_id,
    )


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest) -> ChatResponse:
    try:
        return chat(request.query, request.top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc


def _ingest_bytes(
    *,
    content: bytes,
    file_name: str,
    content_type: str | None,
    source: str,
    external_id: str | None,
) -> IngestResponse:
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    resolved_external_id = external_id or hashlib.sha256(content).hexdigest()
    document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, resolved_external_id))

    try:
        text = extract_text(file_name, content_type, content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}") from exc

    if not text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in file.")

    chunks = split_text(text, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks generated from file.")

    vectors = embed_passages(chunks)
    replace_document_chunks(
        document_id=document_id,
        external_id=resolved_external_id,
        file_name=file_name,
        source=source,
        chunks=chunks,
        vectors=vectors,
    )
    return IngestResponse(
        document_id=document_id,
        external_id=resolved_external_id,
        file_name=file_name,
        chunk_count=len(chunks),
        characters_indexed=len(text),
        source=source,
    )
