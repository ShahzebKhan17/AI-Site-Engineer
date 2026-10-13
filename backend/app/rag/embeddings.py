"""Embedding generation module for pgvector compatibility (1536 dimensions)."""

import hashlib
import math
import os
from typing import Sequence

import httpx

EMBEDDING_DIMENSION = 1536
OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"
DEFAULT_MODEL = "text-embedding-3-small"


def generate_deterministic_vector(text: str, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    """Generate a deterministic, unit-normalized vector for testing and offline environments."""
    raw = [0.0] * dim
    # Hash tokens and accumulate into slots
    tokens = text.lower().split()
    if not tokens:
        tokens = ["empty"]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for idx in range(0, min(len(digest), 32)):
            slot = (idx * 47) % dim
            val = (digest[idx] - 128) / 128.0
            raw[slot] += val

    # Normalize to unit length for cosine similarity
    norm = math.sqrt(sum(x * x for x in raw))
    if norm == 0:
        raw[0] = 1.0
        return raw
    return [round(x / norm, 6) for x in raw]


def generate_embeddings(
    texts: Sequence[str],
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> list[list[float]]:
    """Generate 1536-dim embeddings via OpenAI if API key exists, otherwise deterministic vectors."""
    effective_key = api_key or os.getenv("OPENAI_API_KEY")
    clean_texts = [text.strip() if text.strip() else "empty" for text in texts]

    if not clean_texts:
        return []

    if effective_key:
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    OPENAI_EMBEDDING_URL,
                    headers={
                        "Authorization": f"Bearer {effective_key}",
                        "Content-Type": "application/json",
                    },
                    json={"input": clean_texts, "model": model},
                )
                if response.status_code == 200:
                    data = response.json()
                    # Return sorted by index
                    sorted_records = sorted(data["data"], key=lambda item: item["index"])
                    return [item["embedding"] for item in sorted_records]
        except Exception:
            # Fall back gracefully to deterministic vectors if network or API key fails
            pass

    return [generate_deterministic_vector(text) for text in clean_texts]


def generate_embedding(text: str, api_key: str | None = None) -> list[float]:
    """Generate a single 1536-dim embedding vector."""
    results = generate_embeddings([text], api_key=api_key)
    return results[0]
