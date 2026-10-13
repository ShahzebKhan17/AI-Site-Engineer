from app.ingestion.models import ExtractedChunk
from app.rag.embeddings import EMBEDDING_DIMENSION, generate_deterministic_vector, generate_embeddings
from app.rag.supabase_client import SupabaseRAGClient


def test_embedding_dimension_and_normalization() -> None:
    vec = generate_deterministic_vector("Column C12 Storey Height 3200mm")
    assert len(vec) == EMBEDDING_DIMENSION
    # Check unit norm approx 1.0
    norm_sq = sum(x * x for x in vec)
    assert abs(norm_sq - 1.0) < 0.01


def test_batch_embedding_generation() -> None:
    texts = [
        "Column C12 footing embedment 500mm",
        "Beam B4 lap length 750mm",
        "General structural notes rev 03",
    ]
    vectors = generate_embeddings(texts)
    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == EMBEDDING_DIMENSION


def test_supabase_rag_client_persistence_offline() -> None:
    client = SupabaseRAGClient(supabase_url="", supabase_key="")
    chunks = [
        ExtractedChunk(
            content="Column C12: 16mm dia bars, 4 numbers, M25 Fe500",
            page_number=1,
            chunk_index=0,
            source_reference="drawing:c12.pdf#page=1",
            entity_code="C12",
            entity_type="column",
        )
    ]
    persisted = client.persist_chunks(drawing_id="test-drawing-123", chunks=chunks)
    assert len(persisted) == 1
    assert persisted[0]["entity_code"] == "C12"
    assert len(persisted[0]["embedding"]) == EMBEDDING_DIMENSION
