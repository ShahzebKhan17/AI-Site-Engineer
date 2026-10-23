from app.ingestion.pdf import extract_pdf
from app.rag.orchestrator import AskQuestionRequest, orchestrate_drawing_question
from app.rag.supabase_client import SupabaseRAGClient
from tests.fixtures.sample_drawings import generate_sample_drawing_pdf


def test_end_to_end_pdf_fixture_ingestion_and_calculation() -> None:
    # 1. Generate realistic multi-page PDF bytes
    pdf_bytes = generate_sample_drawing_pdf()
    assert len(pdf_bytes) > 0

    # 2. Run PDF extraction
    extraction = extract_pdf(pdf_bytes, "structural_column_schedule_rev03.pdf")
    assert extraction.page_count == 3
    assert len(extraction.chunks) >= 3

    # Verify drawing mentions C12 on schedule (page 2) and foundation details (page 3)
    c12_chunks = [c for c in extraction.chunks if "C12" in c.content]
    assert len(c12_chunks) >= 2
    sched_chunk = [c for c in c12_chunks if c.page_number == 2][0]
    assert "3000 mm" in sched_chunk.content
    assert "Footing embedment 500 mm" in sched_chunk.content

    # 3. Build candidate cache mimicking Supabase persistence
    client = SupabaseRAGClient(supabase_url="", supabase_key="")
    mock_candidates = [
        {
            "id": f"chunk-{c.chunk_index}",
            "drawing_id": "dwg-rev-03",
            "content": c.content,
            "page_number": c.page_number,
            "entity_code": c.entity_code,
            "metadata": {"source_reference": c.source_reference},
        }
        for c in extraction.chunks
    ]

    # 4. Orchestrate engineer's question for C12
    req = AskQuestionRequest(
        question="What is the cutting length of column C12 main reinforcement?",
        filter_entity_code="C12",
        candidate_chunks_cache=mock_candidates,
    )
    result = orchestrate_drawing_question(req, client=client)

    # 5. Assert deterministic civil engineering BBS outcome
    assert result.status == "completed"
    assert result.parsed_question.member_id == "C12"
    assert result.calculation is not None
    assert result.calculation.member_id == "C12"
    assert result.calculation.cutting_length_mm == 4389.4
    assert result.calculation.cutting_length_m == 4.389
    assert len(result.calculation.breakdown) == 6
    assert any(b.label == "Lap length" for b in result.calculation.breakdown)
    assert any("Bend deduction" in b.label for b in result.calculation.breakdown)


def test_end_to_end_raft_drawing_schedule_qa() -> None:
    raft_page_text = (
        "PROJECT: COMMERCIAL TOWER COMPLEX (REV 02)\n"
        "NOTES ON FOUNDATION:\n"
        "1. All dimensions are in mm. Concrete grade M30.\n"
        "REINFORCEMENT TYPICAL SCHEDULE\n"
        "BAR ID   REINFORCEMENT        LOCATION   LAYER\n"
        "01       Y16 AT 150 C/C       RAFT       BOTTOM\n"
        "02       Y12 AT 150 C/C       RAFT       TOP\n"
        "03       Y8 AT 150 C/C        RAFT       SHEAR LINKS\n"
        "2. Clear cover to raft bottom = 50 mm."
    )

    pdf_bytes = generate_sample_drawing_pdf(pages=[raft_page_text])
    extraction = extract_pdf(pdf_bytes, "commercial_tower_foundation_s01.pdf")
    assert extraction.page_count == 1
    assert len(extraction.chunks) >= 1

    raft_chunk = extraction.chunks[0]
    assert raft_chunk.entity_code == "RAFT"
    assert raft_chunk.entity_type == "footing"

    client = SupabaseRAGClient(supabase_url="", supabase_key="")
    mock_candidates = [
        {
            "id": f"chunk-{c.chunk_index}",
            "drawing_id": "dwg-raft-01",
            "content": c.content,
            "page_number": c.page_number,
            "entity_code": c.entity_code,
            "metadata": {"source_reference": c.source_reference},
        }
        for c in extraction.chunks
    ]

    # Query 1: Dia of steel
    req1 = AskQuestionRequest(
        question="What is the dia of steel in raft?",
        candidate_chunks_cache=mock_candidates,
    )
    res1 = orchestrate_drawing_question(req1, client=client)

    assert res1.parsed_question.member_type == "footing"
    assert res1.parsed_question.member_id == "RAFT"
    assert "Bottom: Y16 @ 150 c/c" in res1.answer
    assert "Top: Y12 @ 150 c/c" in res1.answer
    assert "Shear links: Y8 @ 150 c/c" in res1.answer
    assert "(Bottom: Y16 @ 150 c/c, Top: Y12 @ 150 c/c, Shear links: Y8 @ 150 c/c)" in res1.answer
    assert "PROJECT: COMMERCIAL TOWER COMPLEX" not in res1.answer
    assert "All dimensions are in mm" not in res1.answer

    # Query 2: Reinforcement
    req2 = AskQuestionRequest(
        question="What is the reinforcement for the raft foundation?",
        candidate_chunks_cache=mock_candidates,
    )
    res2 = orchestrate_drawing_question(req2, client=client)
    assert "Bottom: Y16 @ 150 c/c" in res2.answer
    assert "Top: Y12 @ 150 c/c" in res2.answer
    assert "Shear links: Y8 @ 150 c/c" in res2.answer
