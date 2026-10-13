from app.rag.retrieval import run_hybrid_search
from app.rag.supabase_client import SupabaseRAGClient


def test_hybrid_search_boosts_matching_entity() -> None:
    client = SupabaseRAGClient(supabase_url="", supabase_key="")
    mock_chunks = [
        {
            "id": "c-1",
            "drawing_id": "dwg-1",
            "content": "Column C11: 4T16, storey height 3000mm, M25 Fe500",
            "page_number": 1,
            "entity_code": "C11",
            "metadata": {"source_reference": "drawing.pdf#page=1"},
        },
        {
            "id": "c-2",
            "drawing_id": "dwg-1",
            "content": "Column C12: 4T16, storey height 3200mm, footing embedment 500mm, M25 Fe500",
            "page_number": 2,
            "entity_code": "C12",
            "metadata": {"source_reference": "drawing.pdf#page=2"},
        },
        {
            "id": "c-3",
            "drawing_id": "dwg-1",
            "content": "Beam B1: 3T20 top, 3T16 bottom, M25 Fe500",
            "page_number": 3,
            "entity_code": "B1",
            "metadata": {"source_reference": "drawing.pdf#page=3"},
        },
    ]

    # Query targeting C12
    response = run_hybrid_search(
        client=client,
        query_text="What is the cutting length of Column C12?",
        filter_entity_code="C12",
        candidate_chunks_cache=mock_chunks,
    )

    assert len(response.chunks) > 0
    # C12 should rank 1st due to the entity identifier boost
    top_chunk = response.chunks[0]
    assert top_chunk.entity_code == "C12"
    assert top_chunk.page_number == 2
    assert "3200mm" in top_chunk.content
    assert top_chunk.combined_score > response.chunks[1].combined_score
