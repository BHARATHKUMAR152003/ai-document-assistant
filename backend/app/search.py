"""Hybrid retrieval: BM25 keyword scoring + cosine similarity over local embeddings, fused with RRF."""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np

from .embeddings import Embedder, EmbeddingsUnavailable
from .store import Store

STOP = set(
    "a an and are as at be but by can do does for from has have how i in is it its of on or that the this to was what when where which who why will with you your about into than then there these those our we they them their not no".split()
)
RRF_K = 60


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 1]


@dataclass
class Hit:
    chunk: dict[str, Any]
    score: float
    keyword: float
    semantic: float | None
    matched_terms: list[str]


class SearchIndex:
    def __init__(self, store: Store, embedder: Embedder) -> None:
        self.store = store
        self.embedder = embedder
        self._version = -1
        self._lock = threading.Lock()
        self.chunks: list[dict[str, Any]] = []
        self.tfs: list[Counter[str]] = []
        self.df: Counter[str] = Counter()
        self.avg_len = 1.0
        self.vectors: np.ndarray | None = None
        self.vector_rows: list[int] = []

    def _refresh(self) -> None:
        with self._lock:
            if self._version == self.store.version:
                return
            chunks = self.store.all_chunks()
            tfs = [Counter(tokenize(c["text"])) for c in chunks]
            df: Counter[str] = Counter()
            for tf in tfs:
                df.update(tf.keys())
            rows = [i for i, c in enumerate(chunks) if c["embedding"] is not None]
            vectors = np.stack([np.frombuffer(chunks[i]["embedding"], dtype=np.float32) for i in rows]) if rows else None
            self.chunks, self.tfs, self.df = chunks, tfs, df
            self.avg_len = (sum(sum(tf.values()) for tf in tfs) / len(tfs)) if tfs else 1.0
            self.vectors, self.vector_rows = vectors, rows
            self._version = self.store.version

    def _bm25(self, terms: list[str], k1: float = 1.5, b: float = 0.75) -> np.ndarray:
        n = len(self.chunks)
        scores = np.zeros(n, dtype=np.float32)
        for t in set(terms):
            df = self.df.get(t, 0)
            if not df:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self.tfs):
                f = tf.get(t, 0)
                if f:
                    dl = sum(tf.values())
                    scores[i] += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self.avg_len))
        return scores

    def search(self, query: str, top_k: int, doc_ids: list[str] | None = None) -> tuple[list[Hit], str]:
        """Returns hits and the retrieval mode actually used: 'hybrid' or 'keyword'."""
        self._refresh()
        if not self.chunks:
            return [], "keyword"
        terms = tokenize(query)
        allowed = np.array([doc_ids is None or c["doc_id"] in doc_ids for c in self.chunks])
        kw = self._bm25(terms)

        sem = None
        if self.vectors is not None and self.embedder.enabled:
            try:
                q = self.embedder.embed_query(query)
                sem = np.full(len(self.chunks), np.nan, dtype=np.float32)
                sem[self.vector_rows] = self.vectors @ q
            except EmbeddingsUnavailable:
                sem = None

        candidates = np.where(allowed)[0]
        kw_rank = {int(i): r for r, i in enumerate(sorted(candidates, key=lambda i: -kw[i])) if kw[i] > 0}
        fused: dict[int, float] = {i: 1 / (RRF_K + r + 1) for i, r in kw_rank.items()}
        if sem is not None:
            sem_order = [int(i) for i in sorted(candidates, key=lambda i: -np.nan_to_num(sem[i], nan=-1)) if not np.isnan(sem[i])]
            for r, i in enumerate(sem_order[: max(top_k * 4, 20)]):
                fused[i] = fused.get(i, 0) + 1 / (RRF_K + r + 1)

        ranked = sorted(fused, key=lambda i: -fused[i])[:top_k]
        kw_max = float(kw.max()) if len(kw) and kw.max() > 0 else 1.0
        hits = [
            Hit(
                chunk=self.chunks[i],
                score=round(fused[i], 5),
                keyword=round(float(kw[i]) / kw_max, 3),
                semantic=None if sem is None or np.isnan(sem[i]) else round(float(sem[i]), 3),
                matched_terms=sorted({t for t in terms if self.tfs[i].get(t)}),
            )
            for i in ranked
        ]
        return hits, ("hybrid" if sem is not None else "keyword")
