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


def test_rebar_notations_support_y_tor_hash_dia() -> None:
    from app.rag.extractor import infer_member_type

    # Y notation
    out_y = regex_extract_drawing_dimensions(
        text="Footing F2: Size 2500 mm x 2500 mm x 750 mm. Reinforcement Y16 @ 150 c/c.",
        target_member_id="F2",
        citations=["dwg.pdf#page=1"],
        pages=[1],
    )
    assert out_y.footing_request is not None
    assert out_y.footing_request.bar_diameter_mm == 16.0

    # TOR notation
    out_tor = regex_extract_drawing_dimensions(
        text="Beam B5: Clear span 6000 mm. Main bottom bar TOR 25.",
        target_member_id="B5",
        citations=["dwg.pdf#page=2"],
        pages=[2],
    )
    assert out_tor.beam_request is not None
    assert out_tor.beam_request.bar_diameter_mm == 25.0

    # # notation
    out_hash = regex_extract_drawing_dimensions(
        text="Footing F3: Size 2000 mm x 2000 mm x 600 mm. Mesh #20 at 150 c/c.",
        target_member_id="F3",
        citations=["dwg.pdf#page=3"],
        pages=[3],
    )
    assert out_hash.footing_request is not None
    assert out_hash.footing_request.bar_diameter_mm == 20.0

    # dia notation
    out_dia = regex_extract_drawing_dimensions(
        text="Footing F4: Size 2000 mm x 2000 mm x 600 mm. Mesh 12 dia at 150 c/c.",
        target_member_id="F4",
        citations=["dwg.pdf#page=4"],
        pages=[4],
    )
    assert out_dia.footing_request is not None
    assert out_dia.footing_request.bar_diameter_mm == 12.0


def test_parse_reinforcement_typical_schedule_table() -> None:
    from app.rag.extractor import parse_reinforcement_schedule_table

    drawing_schedule_text = (
        "REINFORCEMENT TYPICAL SCHEDULE\n"
        "BAR ID   REINFORCEMENT        LOCATION   LAYER\n"
        "01       Y16 AT 150 C/C       RAFT       BOTTOM\n"
        "02       Y12 AT 150 C/C       RAFT       TOP\n"
        "03       Y8 AT 150 C/C        RAFT       SHEAR LINKS\n"
    )

    rows = parse_reinforcement_schedule_table(drawing_schedule_text)
    assert len(rows) == 3

    # Check mapping
    # Row 1: Bar ID 01, Y16 AT 150 C/C, RAFT, BOTTOM -> 16mm bottom mesh
    r1 = rows[0]
    assert r1.bar_id == "01"
    assert "Y16" in r1.reinforcement
    assert r1.location == "RAFT"
    assert r1.layer == "BOTTOM"
    assert r1.bar_diameter_mm == 16.0
    assert r1.spacing_mm == 150.0

    # Row 2: Bar ID 02, Y12 AT 150 C/C, RAFT, TOP -> 12mm top mesh
    r2 = rows[1]
    assert r2.bar_id == "02"
    assert "Y12" in r2.reinforcement
    assert r2.location == "RAFT"
    assert r2.layer == "TOP"
    assert r2.bar_diameter_mm == 12.0
    assert r2.spacing_mm == 150.0

    # Row 3: Bar ID 03, Y8 AT 150 C/C, RAFT, SHEAR LINKS -> 8mm shear links
    r3 = rows[2]
    assert r3.bar_id == "03"
    assert "Y8" in r3.reinforcement
    assert r3.location == "RAFT"
    assert "SHEAR" in r3.layer
    assert r3.bar_diameter_mm == 8.0
    assert r3.spacing_mm == 150.0


def test_raft_extraction_and_member_type() -> None:
    from app.rag.extractor import infer_member_type

    assert infer_member_type("RAFT") == "footing"
    assert infer_member_type("RF1") == "footing"
    assert infer_member_type("UNKNOWN", "General notes for raft foundation") == "footing"

    text = (
        "REINFORCEMENT TYPICAL SCHEDULE\n"
        "BAR ID   REINFORCEMENT        LOCATION   LAYER\n"
        "01       Y16 AT 150 C/C       RAFT       BOTTOM\n"
        "02       Y12 AT 150 C/C       RAFT       TOP\n"
        "03       Y8 AT 150 C/C        RAFT       SHEAR LINKS\n"
    )
    output = regex_extract_drawing_dimensions(
        text=text,
        target_member_id="RAFT",
        citations=["Sheet S-01/Page 1"],
        pages=[1],
    )

    assert output.member_type == "footing"
    assert len(output.schedule_rows) == 3
    assert output.footing_request is not None
    # Bottom mesh 16mm extracted for footing request
    assert output.footing_request.bar_diameter_mm == 16.0
    assert output.footing_request.spacing_mm == 150.0
    assert any("Bottom mesh 16mm" in note for note in output.notes)
    assert any("Top mesh 12mm" in note for note in output.notes)


def test_regex_extracts_column_dual_zone_ties() -> None:
    text = (
        "REINFORCED CONCRETE COLUMN — TEST DOCUMENT\n"
        "Member ID: C-01. Member type: RCC column.\n"
        "Overall size: 300 mm x 450 mm. Height: 3000 mm.\n"
        "Longitudinal reinforcement: 8 bars Ø16 mm. Steel grade: Fe500.\n"
        "Transverse reinforcement: Ø8 mm closed ties / stirrups.\n"
        "Tie spacing — end zones: 100 mm c/c for 300 mm at each end.\n"
        "Tie spacing — middle zone: 150 mm c/c.\n"
        "Nominal clear cover: 40 mm. Concrete grade: M25."
    )
    output = regex_extract_drawing_dimensions(
        text=text,
        target_member_id="C-01",
        citations=["drawing:TEST-COL-001"],
        pages=[1],
    )
    assert output.member_id == "C-01"
    assert output.column_request is not None
    assert output.column_request.bar_diameter_mm == 16.0
    assert output.column_request.num_bars == 8
    assert output.column_request.storey_height_mm == 3000.0
    assert output.column_request.tie_spacing_end_mm == 100.0
    assert output.column_request.end_zone_length_mm == 300.0
    assert output.column_request.tie_spacing_mid_mm == 150.0

    from app.engineering.calculators.column import calculate_longitudinal_bar
    calc = calculate_longitudinal_bar(output.column_request)
    assert calc.num_ties == 22

