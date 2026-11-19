# AI Document Assistant

Upload PDF, DOCX, TXT or Markdown files and ask questions about them. Documents are extracted, chunked and indexed
**automatically on upload**; questions are answered with the most relevant passages, including the **document name,
page number (PDFs) and supporting excerpt**.

Everything runs locally and free:

| Capability | How | Needs |
| --- | --- | --- |
| Keyword search | BM25 over chunks | nothing |
| Semantic search | Local open-source embeddings — FastEmbed + `BAAI/bge-small-en-v1.5` (ONNX, CPU) | one-time ~70 MB model download |
| Retrieval | Hybrid: BM25 + cosine similarity, fused with reciprocal-rank fusion | — |
| Conversational answers | **Optional** local LLM via [Ollama](https://ollama.com) | Ollama + a model (e.g. `llama3.2:3b`, ~2 GB) |

**Without an LLM** the assistant says so clearly — *"No language model is configured, so conversational answers are
unavailable. Document search still works."* — and shows the retrieved passages. It never fabricates an answer.
When nothing relevant is retrieved (cosine similarity below `MIN_SEMANTIC_SCORE`, or no matching terms in keyword
mode) it replies *"I couldn't find this in your documents."*

```
backend/   FastAPI · pypdf · python-docx · FastEmbed · SQLite (port 8104)
frontend/  React + Vite + TypeScript + Tailwind (port 5104)
```

## Features

- Multi-file upload with client- and server-side validation (type, size ≤ 15 MB, max 50 documents)
- Background processing with live status (processing → ready / failed), passage counts, page counts
- Per-document include/exclude for questions; document removal deletes its chunks and vectors
- Chat with cited sources, similarity scores, matched terms, expandable full passages
- Sample documents (all fictional): a remote-work policy (Markdown), a product FAQ (TXT) and a 3-page onboarding
  handbook (PDF, regenerate with `python scripts/make_sample_pdf.py`)
- Data stored in `backend/data/assistant.db` (SQLite: extracted text + vectors). Original files are not kept.

Scanned (image-only) PDFs need OCR and are not supported.

## Setup

Prerequisites: Python 3.11+, Node.js 18+.

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8104

cd ../frontend
npm install
npm run dev                                            # http://localhost:5104
```

The embedding model downloads from Hugging Face on first use into `backend/data/models` and then works offline.
Behind a TLS-inspecting corporate proxy, the OS certificate store is used (via `truststore`); verification is never
disabled. Set `EMBEDDINGS=none` to run keyword-only without any download.

### Optional: conversational answers with a local LLM

```bash
ollama pull llama3.2:3b
# then start the backend with
LLM_PROVIDER=ollama uvicorn app.main:app --port 8104     # PowerShell: $env:LLM_PROVIDER="ollama"
```

The model receives only the retrieved passages and is instructed to cite them and to reply `NOT_FOUND` when they
don't contain the answer. The Ollama path is covered by a mocked test; it was **not** tested against a running
Ollama server in this environment.

## Tests

```bash
cd backend && pytest -q         # semantic test is skipped if the embedding model can't be loaded
cd frontend && npm test && npm run build
```

## Deployment

Needs ~300 MB RAM with the embedding model loaded and persistent disk for `data/` (Azure App Service with a mounted
file share, Render with a persistent disk — paid on most plans). Without persistent disk, documents are lost on
restart. Serve the frontend statically with `VITE_API_URL` set and add its origin to `CORS_ORIGINS`.
