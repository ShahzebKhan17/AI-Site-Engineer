import pytest
from app.engineering.calculators.column import ColumnBarRequest, calculate_longitudinal_bar
from app.rag.answer_generator import synthesize_engineering_answer
from app.rag.extractor import ExtractionOutput
from app.rag.retrieval import RetrievedChunk


def test_synthesize_answer_with_calculation():
    req = ColumnBarRequest(
        member_id="C12",
        bar_diameter_mm=16,
        storey_height_mm=3000,
        footing_embedment_mm=500,
        top_extension_mm=0,
        concrete_grade="M25",
        steel_grade="Fe500",
        source_references=["Sheet S-02/Page 2"],
        use_is_code_rules=True,
        deduct_bends=True,
    )
    calc = calculate_longitudinal_bar(req)
    chunk = RetrievedChunk(
        chunk_id="c1",
        drawing_id="d1",
        content="Column C12 has 4-T16 bars, storey height 3000 mm, footing embedment 500 mm.",
        page_number=2,
        source_reference="Sheet S-02/Page 2",
    )
    extraction = ExtractionOutput(
        member_id="C12",
        column_request=req,
        confidence=0.95,
        citations=["Sheet S-02/Page 2"],
    )

    answer = synthesize_engineering_answer(
        question="What is the cutting length of column C12?",
        chunks=[chunk],
        extraction=extraction,
        calculation=calc,
        warnings=[],
    )

    assert "Member C12 Bar Bending Schedule" in answer
    assert "Total Cutting Length:" in answer
    assert "3000 mm" in answer
    assert "16 mm" in answer


def test_synthesize_answer_general_drawing_query():
    chunk = RetrievedChunk(
        chunk_id="c2",
        drawing_id="d2",
        content="General Notes: Concrete grade for all foundation pads and footings shall be M25 minimum with clear cover 50 mm.",
        page_number=1,
        source_reference="Sheet S-00/Notes",
    )
    extraction = ExtractionOutput(
        member_id="UNKNOWN",
        confidence=0.5,
        citations=["Sheet S-00/Notes"],
    )

    answer = synthesize_engineering_answer(
        question="What concrete grade is required for footings?",
        chunks=[chunk],
        extraction=extraction,
        calculation=None,
        warnings=[],
    )

    assert "M25" in answer or "Drawing Intelligence" in answer
    assert "Sheet S-00/Notes" in answer
