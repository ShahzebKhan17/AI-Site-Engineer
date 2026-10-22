"""Supabase client for chunk persistence into pgvector document_chunks table."""

import os
from pathlib import Path
from typing import Any

import httpx

try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[2] / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

from app.ingestion.models import ExtractedChunk
from app.rag.embeddings import generate_embeddings


class SupabaseRAGClient:
    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
    ):
        if supabase_url is not None:
            raw_url = supabase_url.rstrip("/")
        else:
            raw_url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
        if raw_url.endswith("/rest/v1"):
            raw_url = raw_url[:-8]
        self.supabase_url = raw_url.rstrip("/")

        if supabase_key is not None:
            self.supabase_key = supabase_key
        else:
            self.supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or ""

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
            # Standalone/offline local storage persistence
            return [{"id": f"record-{c.chunk_index}", **p} for c, p in zip(chunks, payload)]

        endpoint = f"{self.supabase_url}/rest/v1/document_chunks"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(endpoint, headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json()

    def hybrid_search(
        self,
        query_text: str,
        filter_entity_code: str | None = None,
        filter_project_id: str | None = None,
        match_count: int = 6,
        candidate_cache: list[dict[str, Any]] | None = None,
    ):
        from app.rag.retrieval import run_hybrid_search
        return run_hybrid_search(
            client=self,
            query_text=query_text,
            filter_entity_code=filter_entity_code,
            filter_project_id=filter_project_id,
            match_count=match_count,
            candidate_chunks_cache=candidate_cache,
        )
