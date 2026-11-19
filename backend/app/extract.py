"""Text extraction and chunking. Keeps page numbers for PDFs so answers can cite them."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}


class ExtractionError(ValueError):
    pass


@dataclass
class Chunk:
    text: str
    page: int | None
    index: int


def extract_pages(content: bytes, ext: str) -> list[tuple[int | None, str]]:
    """Returns [(page_number_or_None, text)]."""
    try:
        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise ExtractionError("Encrypted PDFs are not supported.")
            pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
        elif ext == ".docx":
            from docx import Document

            doc = Document(io.BytesIO(content))
            parts = [p.text for p in doc.paragraphs]
            for t in doc.tables:
                parts += [" | ".join(c.text for c in row.cells) for row in t.rows]
            pages = [(None, "\n".join(parts))]
        elif ext in (".txt", ".md"):
            pages = [(None, content.decode("utf-8", errors="replace"))]
        else:
            raise ExtractionError(f"Unsupported file type '{ext}'. Use PDF, DOCX, TXT or Markdown.")
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Could not read the document: {exc}") from exc
    pages = [(n, _clean(t)) for n, t in pages]
    if not any(t for _, t in pages):
        raise ExtractionError("No text could be extracted. Scanned (image-only) PDFs need OCR, which is not supported.")
    return pages


def _clean(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunk_pages(pages: list[tuple[int | None, str]], size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page, text in pages:
        if not text:
            continue
        sentences = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
        buf = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            while len(s) > size:  # very long sentence/table row
                if buf:
                    chunks.append(Chunk(buf, page, len(chunks)))
                    buf = ""
                chunks.append(Chunk(s[:size], page, len(chunks)))
                s = s[size - overlap :]
            if len(buf) + len(s) + 1 > size and buf:
                chunks.append(Chunk(buf, page, len(chunks)))
                buf = buf[-overlap:].split(" ", 1)[-1] if overlap else ""
            buf = f"{buf} {s}".strip()
        if buf:
            chunks.append(Chunk(buf, page, len(chunks)))
    return chunks
