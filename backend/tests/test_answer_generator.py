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


def test_synthesize_answer_raft_rebar_schedule():
    from app.rag.extractor import ScheduleTableRow

    schedule_chunk = RetrievedChunk(
        chunk_id="c3",
        drawing_id="d3",
        content=(
            "PROJECT: G+8 RESIDENTIAL APARTMENTS (REV 03). "
            "1. All dimensions are in mm unless otherwise specified. "
            "REINFORCEMENT TYPICAL SCHEDULE\n"
            "BAR ID   REINFORCEMENT        LOCATION   LAYER\n"
            "01       Y16 AT 150 C/C       RAFT       BOTTOM\n"
            "02       Y12 AT 150 C/C       RAFT       TOP\n"
            "03       Y8 AT 150 C/C        RAFT       SHEAR LINKS\n"
            "2. Grade of concrete M25."
        ),
        page_number=1,
        source_reference="Sheet S-01/Page 1",
    )

    schedule_rows = [
        ScheduleTableRow(bar_id="01", reinforcement="Y16 AT 150 C/C", location="RAFT", layer="BOTTOM", bar_diameter_mm=16.0, spacing_mm=150.0),
        ScheduleTableRow(bar_id="02", reinforcement="Y12 AT 150 C/C", location="RAFT", layer="TOP", bar_diameter_mm=12.0, spacing_mm=150.0),
        ScheduleTableRow(bar_id="03", reinforcement="Y8 AT 150 C/C", location="RAFT", layer="SHEAR LINKS", bar_diameter_mm=8.0, spacing_mm=150.0),
    ]

    extraction = ExtractionOutput(
        member_id="RAFT",
        member_type="footing",
        schedule_rows=schedule_rows,
        confidence=1.0,
        citations=["Sheet S-01/Page 1"],
    )

    answer = synthesize_engineering_answer(
        question="What is the dia of steel in raft?",
        chunks=[schedule_chunk],
        extraction=extraction,
        calculation=None,
        warnings=[],
    )

    # Must contain the schedule rows
    assert "Bottom: Y16 @ 150 c/c" in answer
    assert "Top: Y12 @ 150 c/c" in answer
    assert "Shear links: Y8 @ 150 c/c" in answer
    assert "(Bottom: Y16 @ 150 c/c, Top: Y12 @ 150 c/c, Shear links: Y8 @ 150 c/c)" in answer

    # Must NOT dump title block sentences
    assert "PROJECT: G+8 RESIDENTIAL APARTMENTS" not in answer
    assert "All dimensions are in mm unless otherwise specified" not in answer


def test_synthesize_answer_column_diameter_query():
    chunk = RetrievedChunk(
        chunk_id="col-chunk-1",
        drawing_id="col-dwg",
        content="REINFORCED CONCRETE COLUMN C-01. Main reinforcement: 8 bars Ø16 mm Fe500. Lateral ties: 8 mm dia @ 150 mm c/c. Clear cover 40 mm.",
        page_number=1,
        source_reference="Sheet S-02/Page 1",
    )
    extraction = ExtractionOutput(
        member_id="C-01",
        member_type="column",
        confidence=1.0,
        citations=["Sheet S-02/Page 1"],
    )

    answer = synthesize_engineering_answer(
        question="what is the Diameter of the steel bars used in the column",
        chunks=[chunk],
        extraction=extraction,
        calculation=None,
        warnings=[],
    )

    assert "16 mm" in answer
    assert "8 mm" in answer
    assert "Main Longitudinal Bars" in answer or "Main Longitudinal Reinforcement" in answer
    assert "Transverse Lateral Ties" in answer or "Lateral Ties" in answer
