"""Hybrid retrieval module combining vector similarity, full-text ranking, and entity boosts."""

from typing import Any
from pydantic import BaseModel, Field

from app.rag.embeddings import generate_embedding
from app.rag.supabase_client import SupabaseRAGClient


class RetrievedChunk(BaseModel):
    chunk_id: str
    drawing_id: str
    content: str
    page_number: int
    entity_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    keyword_score: float = 0.0
    semantic_score: float = 0.0
    combined_score: float = 0.0
    source_reference: str = ""


class RetrievalRequest(BaseModel):
    query_text: str = Field(min_length=1)
    filter_entity_code: str | None = None
    filter_project_id: str | None = None
    match_count: int = Field(default=6, ge=1, le=20)


class RetrievalResponse(BaseModel):
    query_text: str
    matched_entity_code: str | None
    chunks: list[RetrievedChunk]
    retrieval_mode: str


def run_hybrid_search(
    client: SupabaseRAGClient,
    query_text: str,
    filter_entity_code: str | None = None,
    filter_project_id: str | None = None,
    match_count: int = 6,
    candidate_chunks_cache: list[dict[str, Any]] | None = None,
) -> RetrievalResponse:
    """Execute hybrid search using Supabase RPC or fallback ranking."""
    query_vector = generate_embedding(query_text)

    if client.is_configured:
        import httpx

        endpoint = f"{client.supabase_url}/rest/v1/rpc/hybrid_search_document_chunks"
        payload = {
            "query_text": query_text,
            "query_embedding": query_vector,
            "match_count": match_count,
            "filter_project_id": filter_project_id,
            "filter_entity_code": filter_entity_code,
        }
        with httpx.Client(timeout=30.0) as http_client:
            response = http_client.post(endpoint, headers=client._headers(), json=payload)
            response.raise_for_status()
            raw_results = response.json()
            chunks = [
                RetrievedChunk(
                    chunk_id=r.get("chunk_id", ""),
                    drawing_id=r.get("drawing_id", ""),
                    content=r.get("content", ""),
                    page_number=r.get("page_number", 1),
                    entity_code=r.get("entity_code"),
                    metadata=r.get("metadata", {}),
                    keyword_score=round(r.get("keyword_score", 0.0), 3),
                    semantic_score=round(r.get("semantic_score", 0.0), 3),
                    combined_score=round(r.get("combined_score", 0.0), 3),
                    source_reference=r.get("metadata", {}).get("source_reference", f"page={r.get('page_number', 1)}"),
                )
                for r in raw_results
            ]
            return RetrievalResponse(
                query_text=query_text,
                matched_entity_code=filter_entity_code,
                chunks=chunks,
                retrieval_mode="supabase_rpc_hybrid",
            )

    # Offline simulated hybrid ranking
    from app.rag.store import get_all_chunks
    candidates = candidate_chunks_cache if candidate_chunks_cache else get_all_chunks()
    scored: list[RetrievedChunk] = []
    norm_query = query_text.lower()
    entity_target = (filter_entity_code or "").upper()
    query_tokens = [w.strip(".,;:?!()[]{}'\"") for w in norm_query.split() if len(w.strip(".,;:?!()[]{}'\"")) > 2]

    for idx, c in enumerate(candidates):
        content = c.get("content", "")
        c_entity = (c.get("entity_code") or "").upper()
        # Simulated keyword score based on token overlap
        matches = [tok for tok in query_tokens if tok in content.lower()]
        kw_score = min(round(len(matches) / max(len(query_tokens), 1) * 1.2, 2), 1.0) if query_tokens else 0.5
        # Exact entity boost (+0.35)
        entity_boost = 0.35 if (entity_target and (c_entity == entity_target or entity_target in content.upper())) else 0.0
        # Simulated semantic score
        sem_score = 0.7 if kw_score > 0.2 else (0.4 if kw_score > 0 else 0.15)
        comb = round(0.45 * kw_score + 0.55 * sem_score + entity_boost, 3)

        scored.append(
            RetrievedChunk(
                chunk_id=c.get("id", f"mock-{idx}"),
                drawing_id=c.get("drawing_id", "mock-drawing"),
                content=content,
                page_number=c.get("page_number", 1),
                entity_code=c_entity or None,
                metadata=c.get("metadata", {}),
                keyword_score=kw_score,
                semantic_score=sem_score,
                combined_score=comb,
                source_reference=c.get("metadata", {}).get("source_reference", f"mock#page={c.get('page_number', 1)}"),
            )
        )

    scored.sort(key=lambda x: x.combined_score, reverse=True)
    return RetrievalResponse(
        query_text=query_text,
        matched_entity_code=filter_entity_code,
        chunks=scored[:match_count],
        retrieval_mode="simulated_hybrid",
    )
