"""Local embedding model (FastEmbed / ONNX). Downloads the model once, then runs fully offline."""

from __future__ import annotations

import threading

import numpy as np

from . import config


class EmbeddingsUnavailable(RuntimeError):
    pass


class Embedder:
    def __init__(self, model_name: str, cache_dir: str) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._error: str | None = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return config.EMBEDDINGS == "fastembed"

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def ready(self) -> bool:
        return self._model is not None

    def _load(self):
        if self._model is not None:
            return self._model
        if not self.enabled:
            raise EmbeddingsUnavailable("Semantic search is disabled (EMBEDDINGS=none).")
        with self._lock:
            if self._model is None:
                try:
                    try:  # trust the OS certificate store for the one-time model download
                        import truststore

                        truststore.inject_into_ssl()
                    except ImportError:
                        pass
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
                    self._error = None
                except Exception as exc:
                    self._error = f"Embedding model '{self.model_name}' could not be loaded: {exc}"
                    raise EmbeddingsUnavailable(self._error) from exc
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        vecs = np.asarray(list(model.embed(texts, batch_size=32)), dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.clip(norms, 1e-9, None)

    def embed_query(self, text: str) -> np.ndarray:
        model = self._load()
        vec = np.asarray(next(iter(model.query_embed(text))), dtype=np.float32)
        return vec / max(float(np.linalg.norm(vec)), 1e-9)
