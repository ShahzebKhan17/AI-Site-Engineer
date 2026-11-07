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


def test_orchestration_beam_concrete_and_bbs_with_candidate_members_cache() -> None:
    client = SupabaseRAGClient(supabase_url="", supabase_key="")

    candidate_beam = {
        "member_id": "BM-01",
        "member_type": "beam",
        "dimensions": {
            "width_mm": 230.0,
            "depth_mm": 450.0,
            "clear_span_mm": 4000.0,
            "height_mm": 4000.0,
            "support_width_mm": 300.0,
            "clear_cover_mm": 25.0,
        },
        "bottom_bars_count": 3,
        "bottom_bar_dia_mm": 16.0,
        "top_bars_count": 2,
        "top_bar_dia_mm": 12.0,
        "stirrup_dia_mm": 8.0,
        "stirrup_spacing_mm": 150.0,
        "num_bars": 5,
        "main_bar_diameter_mm": 16.0,
        "secondary_bar_diameter_mm": 8.0,
        "spacing_mm": 150.0,
        "concrete_grade": "M25",
        "steel_grade": "FE500",
        "reinforcement_summary": "Bottom longitudinal bars: 3 bars x 16 mm diameter; Top longitudinal bars: 2 bars x 12 mm diameter; Stirrups: 8 mm diameter, 150 mm c/c throughout the 4,000 mm length",
        "citations": ["Page 1: Test Case BM-01 Table"],
    }

    mock_chunks = [
        {
            "id": "chunk-bm01",
            "drawing_id": "Beam.png",
            "content": "Test Case BM-01: Beam size 230 mm wide x 450 mm overall depth, Clear span: 4,000 mm, cover: 25 mm",
            "page_number": 1,
            "entity_code": "BM-01",
            "metadata": {"source_reference": "Page 1: Test Case BM-01 Table"},
        }
    ]

    req = AskQuestionRequest(
        question="what is the concrete required for this beam",
        filter_entity_code="BM-01",
        candidate_chunks_cache=mock_chunks,
        candidate_members_cache=[candidate_beam],
    )

    response = orchestrate_drawing_question(req, client=client)

    assert response.status == "completed"
    assert response.calculation is not None
    assert response.calculation.member_id == "BM-01"
    assert response.calculation.concrete_volume_m3 == 0.414
    assert response.calculation.cement_bags == 4.59
    assert len(response.calculation.items) == 3
    # Item 1: Bottom 3-T16
    assert response.calculation.items[0].bar_mark == "Bottom Longitudinal Bars"
    assert response.calculation.items[0].cutting_length_mm == 4840.0
    # Left support anchorage has 452 mm length: (300-40) + 12*16 = 260 + 192 = 452 mm
    assert any(b.length_mm == 452.0 for b in response.calculation.items[0].breakdown)
    # Item 3: Stirrups
    assert response.calculation.items[2].bar_mark == "Shear Stirrups / Links"
    assert response.calculation.items[2].num_bars == 27
    # Answer verification
    assert "0.414 m³" in response.answer
    assert "4.59 bags" in response.answer

