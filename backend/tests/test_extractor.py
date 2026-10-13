from app.rag.extractor import extract_parameters_from_evidence, regex_extract_drawing_dimensions
from app.rag.retrieval import RetrievedChunk


def test_regex_extracts_column_schedule_data() -> None:
    text = (
        "Project: G+8 Building. Column schedule rev 03.\n"
        "Column C12: Longitudinal reinforcement 4-T16 bars (Fe500).\n"
        "Clear storey height 3200 mm, footing embedment depth 500 mm.\n"
        "Grade of concrete: M25. Cover: 40mm."
    )
    output = regex_extract_drawing_dimensions(
        text=text,
        target_member_id="C12",
        citations=["drawing.pdf#page=2"],
        pages=[2],
    )

    assert output.member_id == "C12"
    assert output.confidence == 1.0
    assert len(output.missing_fields) == 0
    assert output.column_request is not None
    assert output.column_request.bar_diameter_mm == 16.0
    assert output.column_request.storey_height_mm == 3200.0
    assert output.column_request.footing_embedment_mm == 500.0
    assert output.column_request.concrete_grade == "M25"
    assert output.column_request.steel_grade == "FE500"


def test_extractor_flags_missing_fields_gracefully() -> None:
    # Incomplete drawing snippet (missing height)
    chunk = RetrievedChunk(
        chunk_id="chunk-1",
        drawing_id="dwg-1",
        content="Column C12: 4 numbers of 16mm diameter bars. Footing embedment 500mm.",
        page_number=1,
        source_reference="drawing.pdf#page=1",
    )
    output = extract_parameters_from_evidence(
        question="What is the cutting length of C12?",
        chunks=[chunk],
        member_id="C12",
    )

    assert output.member_id == "C12"
    assert "storey_height_mm" in output.missing_fields
    assert output.confidence < 1.0
