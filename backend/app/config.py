from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
SAMPLE_DIR = BASE_DIR / "sample_docs"

# "fastembed" = local open-source embeddings (downloaded once, then offline); "none" = keyword search only.
EMBEDDINGS = os.getenv("EMBEDDINGS", "fastembed").lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024
MAX_DOCUMENTS = int(os.getenv("MAX_DOCUMENTS", "50"))
CHUNK_CHARS = int(os.getenv("CHUNK_CHARS", "900"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
TOP_K = int(os.getenv("TOP_K", "5"))
# Minimum relevance before we admit "not found". Cosine for embeddings, normalised BM25 for keyword mode.
MIN_SEMANTIC_SCORE = float(os.getenv("MIN_SEMANTIC_SCORE", "0.55"))

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5104,http://127.0.0.1:5104").split(",") if o.strip()]
