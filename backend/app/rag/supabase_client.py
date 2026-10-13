"""Supabase client for chunk persistence into pgvector document_chunks table."""

import os
from typing import Any

import httpx

from app.ingestion.models import ExtractedChunk
from app.rag.embeddings import generate_embeddings


class SupabaseRAGClient:
    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
    ):
        self.supabase_url = (supabase_url or os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or ""

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def persist_chunks(
        self,
        drawing_id: str,
        chunks: list[ExtractedChunk],
        generate_missing_embeddings: bool = True,
    ) -> list[dict[str, Any]]:
        """Persist extracted chunks with pgvector embeddings to Supabase document_chunks."""
        if not chunks:
            return []

        # Generate embeddings if not already attached
        texts_needing_embeddings = [c.content for c in chunks if c.embedding is None]
        if generate_missing_embeddings and texts_needing_embeddings:
            computed_vectors = generate_embeddings(texts_needing_embeddings)
            vec_idx = 0
            for chunk in chunks:
                if chunk.embedding is None:
                    chunk.embedding = computed_vectors[vec_idx]
                    vec_idx += 1

        payload = [
            {
                "drawing_id": drawing_id,
                "content": chunk.content,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "entity_code": chunk.entity_code,
                "entity_type": chunk.entity_type,
                "metadata": {"source_reference": chunk.source_reference},
                "embedding": chunk.embedding,
            }
            for chunk in chunks
        ]

        if not self.is_configured:
            # Standalone/offline simulated persistence
            return [{"id": f"simulated-{c.chunk_index}", **p} for c, p in zip(chunks, payload)]

        endpoint = f"{self.supabase_url}/rest/v1/document_chunks"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(endpoint, headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json()
