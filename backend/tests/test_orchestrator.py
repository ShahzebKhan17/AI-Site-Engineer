from app.rag.orchestrator import AskQuestionRequest, orchestrate_drawing_question
from app.rag.supabase_client import SupabaseRAGClient


def test_end_to_end_orchestration_flow() -> None:
    client = SupabaseRAGClient(supabase_url="", supabase_key="")

    mock_chunks = [
        {
            "id": "chunk-101",
            "drawing_id": "dwg-col-sched",
            "content": (
                "SCHEDULE OF COLUMNS (REV 03)\n"
                "Column C12: 4-T16 bars (Fe500 grade steel).\n"
                "Storey height: 3000 mm, Footing embedment: 500 mm.\n"
                "Concrete grade: M25. Clear cover: 40 mm."
            ),
            "page_number": 2,
            "entity_code": "C12",
            "metadata": {"source_reference": "drawing:column-schedule.pdf#page=2"},
        }
    ]

    req = AskQuestionRequest(
        question="What is the cutting length of the column C12 reinforcement bars?",
        filter_entity_code="C12",
        candidate_chunks_cache=mock_chunks,
    )

    response = orchestrate_drawing_question(req, client=client)

    assert response.status == "completed"
    assert response.parsed_question.member_id == "C12"
    assert response.parsed_question.calculation_intent == "cutting_length"
    assert len(response.evidence_chunks) > 0
    assert response.extraction.member_id == "C12"
    assert response.extraction.confidence >= 0.8
    assert response.calculation is not None
    assert response.calculation.member_id == "C12"
    # Storey(3000) + Footing(500) + Bend(300) + Lap(621.4) - Bend deduction(32) = 4389.4 mm
    assert response.calculation.cutting_length_mm == 4389.4
    assert response.calculation.cutting_length_m == 4.389
    assert len(response.calculation.source_references) > 0
    assert "drawing:column-schedule.pdf#page=2" in response.calculation.source_references[0]


def test_orchestration_flags_unresolved_drawing() -> None:
    client = SupabaseRAGClient(supabase_url="", supabase_key="")

    # Incomplete drawing content missing column dimensions
    mock_chunks = [
        {
            "id": "chunk-102",
            "drawing_id": "dwg-general",
            "content": "General notes: All dimensions in mm. Concrete grades shall be specified in schedule.",
            "page_number": 1,
            "entity_code": "GEN",
            "metadata": {"source_reference": "drawing:notes.pdf#page=1"},
        }
    ]

    req = AskQuestionRequest(
        question="What is the cutting length of Column C99?",
        filter_entity_code="C99",
        candidate_chunks_cache=mock_chunks,
    )

    response = orchestrate_drawing_question(req, client=client)

    assert response.status == "needs_review"
    assert len(response.review_warnings) > 0
    assert response.calculation is None
