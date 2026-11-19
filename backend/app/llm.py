"""Optional local LLM (Ollama) for grounded answers. Off unless LLM_PROVIDER=ollama."""

from __future__ import annotations

import httpx

from . import config

SYSTEM = (
    "You answer questions using ONLY the numbered context passages from the user's documents. "
    "Cite passages like [1] or [2] after the sentences they support. If the passages do not contain the answer, "
    "reply exactly: NOT_FOUND. Do not use outside knowledge."
)


class LLMUnavailable(RuntimeError):
    pass


def status() -> dict[str, object]:
    if config.LLM_PROVIDER != "ollama":
        return {
            "enabled": False,
            "message": "No language model is configured, so conversational answers are unavailable. Document search still works. "
            "To enable answers, install Ollama and start the backend with LLM_PROVIDER=ollama.",
        }
    return {"enabled": True, "provider": "ollama", "model": config.OLLAMA_MODEL}


def answer(question: str, passages: list[str]) -> str | None:
    """Returns the model's answer, or None when the model says the documents don't contain it."""
    if config.LLM_PROVIDER != "ollama":
        raise LLMUnavailable(str(status()["message"]))
    context = "\n\n".join(f"[{i + 1}] {p}" for i, p in enumerate(passages))
    try:
        r = httpx.post(
            f"{config.OLLAMA_URL}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "system": SYSTEM,
                "prompt": f"Context:\n{context}\n\nQuestion: {question}\nAnswer:",
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=180,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMUnavailable(f"Could not reach Ollama at {config.OLLAMA_URL}. Is `ollama serve` running and '{config.OLLAMA_MODEL}' pulled?") from exc
    text = (r.json().get("response") or "").strip()
    if not text or "NOT_FOUND" in text:
        return None
    return text
