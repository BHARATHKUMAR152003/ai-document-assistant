"""SQLite-backed document and chunk store with an in-memory search index."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  ext TEXT NOT NULL,
  size INTEGER NOT NULL,
  status TEXT NOT NULL,           -- processing | ready | failed
  error TEXT,
  warning TEXT,
  pages INTEGER,
  chunks INTEGER DEFAULT 0,
  embedded INTEGER DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  page INTEGER,
  text TEXT NOT NULL,
  embedding BLOB
);
CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc_id);
"""


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self.version = 0  # bumps on every change so the search index can refresh
        with self._conn() as c:
            c.executescript(SCHEMA)
            # Documents interrupted by a restart can never finish.
            c.execute("UPDATE documents SET status='failed', error='Processing was interrupted by a server restart.' WHERE status='processing'")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def create_document(self, name: str, ext: str, size: int) -> str:
        doc_id = uuid.uuid4().hex
        with self._conn() as c:
            c.execute(
                "INSERT INTO documents (id, name, ext, size, status, created_at) VALUES (?, ?, ?, ?, 'processing', ?)",
                (doc_id, name, ext, size, time.time()),
            )
        self.version += 1
        return doc_id

    def finish_document(self, doc_id: str, pages: int | None, chunks: list[tuple[int, int | None, str]], embeddings: np.ndarray | None, warning: str | None) -> bool:
        with self._conn() as c:
            if not c.execute("SELECT 1 FROM documents WHERE id=?", (doc_id,)).fetchone():
                return False  # deleted while processing
            c.executemany(
                "INSERT INTO chunks (doc_id, idx, page, text, embedding) VALUES (?, ?, ?, ?, ?)",
                [(doc_id, i, p, t, embeddings[n].astype(np.float32).tobytes() if embeddings is not None else None) for n, (i, p, t) in enumerate(chunks)],
            )
            c.execute(
                "UPDATE documents SET status='ready', pages=?, chunks=?, embedded=?, warning=? WHERE id=?",
                (pages, len(chunks), int(embeddings is not None), warning, doc_id),
            )
        self.version += 1
        return True

    def fail_document(self, doc_id: str, error: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE documents SET status='failed', error=? WHERE id=?", (error, doc_id))
        self.version += 1

    def list_documents(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM documents ORDER BY created_at DESC")]

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            return dict(row) if row else None

    def delete_document(self, doc_id: str) -> bool:
        with self._conn() as c:
            c.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
            deleted = c.execute("DELETE FROM documents WHERE id=?", (doc_id,)).rowcount > 0
        self.version += 1
        return deleted

    def count_documents(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def all_chunks(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT ch.id, ch.doc_id, ch.idx, ch.page, ch.text, ch.embedding, d.name FROM chunks ch "
                "JOIN documents d ON d.id = ch.doc_id WHERE d.status='ready' ORDER BY ch.doc_id, ch.idx"
            ).fetchall()
            return [dict(r) for r in rows]
