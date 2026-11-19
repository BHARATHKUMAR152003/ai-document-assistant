from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config, llm
from .embeddings import Embedder, EmbeddingsUnavailable
from .extract import SUPPORTED, ExtractionError, chunk_pages, extract_pages
from .search import SearchIndex
from .store import Store

app = FastAPI(title="AI Document Assistant API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])

store = Store(config.DATA_DIR / "assistant.db")
embedder = Embedder(config.EMBEDDING_MODEL, str(config.DATA_DIR / "models"))
index = SearchIndex(store, embedder)


def process_document(doc_id: str, content: bytes, ext: str) -> None:
    """Extract -> chunk -> embed -> store. Runs in a background task right after upload."""
    try:
        pages = extract_pages(content, ext)
        chunks = chunk_pages(pages, config.CHUNK_CHARS, config.CHUNK_OVERLAP)
        rows = [(c.index, c.page, c.text) for c in chunks]
        vectors, warning = None, None
        if embedder.enabled:
            try:
                vectors = embedder.embed([c.text for c in chunks])
            except EmbeddingsUnavailable as exc:
                warning = f"Indexed for keyword search only. {exc}"
        else:
            warning = "Indexed for keyword search only (semantic search disabled)."
        page_count = len(pages) if ext == ".pdf" else None
        store.finish_document(doc_id, page_count, rows, vectors, warning)
    except ExtractionError as exc:
        store.fail_document(doc_id, str(exc))
    except Exception as exc:  # keep the worker alive and surface the failure in the UI
        store.fail_document(doc_id, f"Unexpected processing error: {exc.__class__.__name__}")


def _public(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: doc[k] for k in ("id", "name", "ext", "size", "status", "error", "warning", "pages", "chunks", "embedded", "created_at")}


def _safe_name(name: str) -> str:
    base = Path(name).name
    return re.sub(r"[^\w .()-]", "_", base)[:120] or "document"


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "documents": store.count_documents(),
        "embeddings": {"enabled": embedder.enabled, "model": config.EMBEDDING_MODEL, "loaded": embedder.ready, "error": embedder.error},
        "llm": llm.status(),
    }


@app.get("/api/documents")
def list_documents() -> list[dict[str, Any]]:
    return [_public(d) for d in store.list_documents()]


@app.post("/api/documents", status_code=202)
async def upload(background: BackgroundTasks, file: UploadFile = File(...)) -> dict[str, Any]:
    name = _safe_name(file.filename or "")
    ext = Path(name).suffix.lower()
    if ext not in SUPPORTED:
        raise HTTPException(422, "Unsupported file type. Upload PDF, DOCX, TXT or Markdown (.md) files.")
    if store.count_documents() >= config.MAX_DOCUMENTS:
        raise HTTPException(409, f"Document limit reached ({config.MAX_DOCUMENTS}). Remove a document first.")
    content = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not content:
        raise HTTPException(422, "The uploaded file is empty.")
    doc_id = store.create_document(name, ext, len(content))
    background.add_task(process_document, doc_id, content, ext)
    return _public(store.get_document(doc_id))


@app.post("/api/documents/samples", status_code=202)
def load_samples(background: BackgroundTasks) -> list[dict[str, Any]]:
    existing = {d["name"] for d in store.list_documents()}
    created = []
    for path in sorted(config.SAMPLE_DIR.iterdir()):
        if path.suffix.lower() in SUPPORTED and path.name not in existing:
            doc_id = store.create_document(path.name, path.suffix.lower(), path.stat().st_size)
            background.add_task(process_document, doc_id, path.read_bytes(), path.suffix.lower())
            created.append(_public(store.get_document(doc_id)))
    return created


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str) -> dict[str, Any]:
    doc = store.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    return _public(doc)


@app.delete("/api/documents/{doc_id}", status_code=204, response_model=None)
def delete_document(doc_id: str) -> None:
    if not store.delete_document(doc_id):
        raise HTTPException(404, "Document not found.")


class AskBody(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    document_ids: list[str] | None = None
    top_k: int = Field(default=config.TOP_K, ge=1, le=10)


def _excerpt(text: str, terms: list[str], width: int = 320) -> str:
    lower = text.lower()
    pos = min((lower.find(t) for t in terms if t in lower), default=0)
    start = max(0, pos - width // 3)
    snippet = text[start : start + width]
    return ("…" if start else "") + snippet.strip() + ("…" if start + width < len(text) else "")


@app.post("/api/ask")
def ask(body: AskBody) -> dict[str, Any]:
    ready = [d for d in store.list_documents() if d["status"] == "ready"]
    if not ready:
        raise HTTPException(409, "No processed documents yet. Upload a document or load the samples first.")
    hits, mode = index.search(body.question, body.top_k, body.document_ids)

    if mode == "hybrid":
        best = max((h.semantic or 0 for h in hits), default=0)
        relevant = [h for h in hits if (h.semantic or 0) >= config.MIN_SEMANTIC_SCORE or h.keyword >= 0.5]
        found = best >= config.MIN_SEMANTIC_SCORE
    else:
        relevant = [h for h in hits if h.matched_terms]
        found = bool(relevant)

    sources = [
        {
            "n": i + 1,
            "document_id": h.chunk["doc_id"],
            "document": h.chunk["name"],
            "page": h.chunk["page"],
            "chunk": h.chunk["idx"],
            "excerpt": _excerpt(h.chunk["text"], h.matched_terms),
            "text": h.chunk["text"],
            "semantic_score": h.semantic,
            "keyword_score": h.keyword,
            "matched_terms": h.matched_terms,
        }
        for i, h in enumerate(relevant)
    ]
    result: dict[str, Any] = {"question": body.question, "retrieval": mode, "found": found and bool(sources), "sources": sources, "answer": None}

    if not result["found"]:
        result["message"] = "I couldn't find this in your documents. Try rephrasing, or upload a document that covers it."
        return result

    status = llm.status()
    if not status["enabled"]:
        result["answer_mode"] = "search_only"
        result["message"] = status["message"]
        return result
    try:
        text = llm.answer(body.question, [s["text"] for s in sources])
    except llm.LLMUnavailable as exc:
        result["answer_mode"] = "search_only"
        result["message"] = str(exc)
        return result
    if text is None:
        result.update(found=False, answer_mode="llm", message="The language model could not answer this from the retrieved passages.")
    else:
        result.update(answer=text, answer_mode="llm", model=status.get("model"))
    return result


@app.post("/api/reset", status_code=204, response_model=None)
def reset() -> None:
    """Removes every document and chunk (used by the 'Clear all' button)."""
    for d in store.list_documents():
        store.delete_document(d["id"])
