"""P4 tests. Use a temporary data dir. Semantic tests run only when the local embedding model can be loaded."""

import importlib
import io
import os
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    os.environ["DATA_DIR"] = str(data)
    os.environ.setdefault("EMBEDDINGS", "fastembed")
    # The embedding model cache is shared across runs so it downloads only once.
    from app import config

    importlib.reload(config)
    from app import main

    importlib.reload(main)
    model_cache = os.path.join(os.path.dirname(__file__), "..", "data", "models")
    main.embedder.cache_dir = os.path.abspath(model_cache)
    return main


@pytest.fixture(scope="module")
def client(env):
    return TestClient(env.app)


def _wait_ready(client, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        docs = client.get("/api/documents").json()
        if docs and all(d["status"] != "processing" for d in docs):
            return docs
        time.sleep(0.5)
    raise AssertionError("documents did not finish processing")


def test_extract_and_chunk_keeps_pages():
    from app.extract import chunk_pages, extract_pages

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "First page about apples.")
    c.showPage()
    c.drawString(72, 720, "Second page about oranges.")
    c.save()
    pages = extract_pages(buf.getvalue(), ".pdf")
    assert [p for p, _ in pages] == [1, 2]
    chunks = chunk_pages(pages, 900, 150)
    assert chunks[1].page == 2 and "oranges" in chunks[1].text


def test_chunking_overlaps_and_bounds():
    from app.extract import chunk_pages

    text = " ".join(f"Sentence number {i} talks about topic {i}." for i in range(200))
    chunks = chunk_pages([(None, text)], 300, 60)
    assert len(chunks) > 5
    assert all(len(c.text) <= 300 + 60 for c in chunks)


def test_rejects_bad_uploads(client):
    assert client.post("/api/documents", files={"file": ("a.exe", b"x", "application/octet-stream")}).status_code == 422
    assert client.post("/api/documents", files={"file": ("a.txt", b"", "text/plain")}).status_code == 422


def test_ask_without_documents(client):
    client.post("/api/reset")
    assert client.post("/api/ask", json={"question": "anything"}).status_code == 409


def test_upload_index_search_and_delete(client, env):
    client.post("/api/reset")
    txt = b"The cafeteria opens at 8 am and closes at 7 pm. Vegetarian meals are available every day."
    doc = client.post("/api/documents", files={"file": ("cafe.txt", txt, "text/plain")}).json()
    assert doc["status"] == "processing"
    docs = _wait_ready(client)
    assert docs[0]["status"] == "ready" and docs[0]["chunks"] == 1

    res = client.post("/api/ask", json={"question": "When does the cafeteria close?"}).json()
    assert res["found"]
    assert res["sources"][0]["document"] == "cafe.txt"
    assert "cafeteria" in res["sources"][0]["matched_terms"]
    assert res["answer"] is None and res["answer_mode"] == "search_only"
    assert "conversational answers are unavailable" in res["message"]

    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get("/api/documents").json() == []
    assert client.post("/api/ask", json={"question": "cafeteria"}).status_code == 409


def test_samples_with_page_citations_and_not_found(client, env):
    client.post("/api/reset")
    created = client.post("/api/documents/samples").json()
    assert len(created) == 3
    docs = _wait_ready(client)
    assert all(d["status"] == "ready" for d in docs)
    pdf = next(d for d in docs if d["ext"] == ".pdf")
    assert pdf["pages"] == 3

    res = client.post("/api/ask", json={"question": "How many days of sick leave do employees get?"}).json()
    assert res["found"]
    top = res["sources"][0]
    assert top["document"] == "onboarding-handbook.pdf" and top["page"] == 2
    assert "12 days" in top["text"]

    res = client.post("/api/ask", json={"question": "How long are deleted files kept in the recycle bin?"}).json()
    assert res["sources"][0]["document"] == "skyvault-faq.txt"

    filtered = client.post("/api/ask", json={"question": "home office allowance", "document_ids": [pdf["id"]]}).json()
    assert all(s["document_id"] == pdf["id"] for s in filtered["sources"])

    unrelated = client.post("/api/ask", json={"question": "What is the boiling point of mercury on Mars?"}).json()
    assert unrelated["found"] is False
    assert "couldn't find" in unrelated["message"]


def test_semantic_retrieval_handles_paraphrase(client, env):
    if not env.embedder.ready:
        pytest.skip(f"embedding model unavailable: {env.embedder.error}")
    docs = client.get("/api/documents").json()
    assert all(d["embedded"] for d in docs)
    # No shared keywords with "VPN", "public Wi-Fi": tests that semantic search, not BM25, finds it.
    res = client.post("/api/ask", json={"question": "Can I use the internet at a coffee shop for work?"}).json()
    assert res["retrieval"] == "hybrid"
    assert res["sources"][0]["document"] == "remote-work-policy.md"


def test_llm_answer_path(client, env, monkeypatch):
    from app import llm

    monkeypatch.setattr(env.config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm, "answer", lambda q, passages: "Employees get 12 days of paid sick leave [1].")
    res = client.post("/api/ask", json={"question": "How many days of sick leave do employees get?"}).json()
    assert res["answer_mode"] == "llm" and "[1]" in res["answer"]
    monkeypatch.setattr(llm, "answer", lambda q, passages: None)
    res = client.post("/api/ask", json={"question": "How many days of sick leave do employees get?"}).json()
    assert res["found"] is False and res["answer"] is None
