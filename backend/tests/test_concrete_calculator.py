import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.engineering.calculators.concrete import (
    calculate_concrete_materials,
    calculate_member_concrete_volume,
    DRY_VOLUME_FACTOR,
)
from app.engineering.project_bbs import generate_consolidated_project_bbs
from app.rag.extractor import ExtractionOutput
from app.rag.question_parser import parse_drawing_question
from app.rag.answer_generator import synthesize_engineering_answer
from app.rag.retrieval import RetrievedChunk


def test_calculate_concrete_materials_m25() -> None:
    # 10 m³ wet concrete of M25 (1:1:2)
    # Dry volume = 10 * 1.54 = 15.4 m³
    # Total parts = 4
    # Cement m³ = 1/4 * 15.4 = 3.85 m³ -> cement kg = 3.85 * 1440 = 5544 kg -> 110.88 bags
    # Sand m³ = 1/4 * 15.4 = 3.85 m³ -> sand kg = 3.85 * 1600 = 6160 kg
    # Aggregate m³ = 2/4 * 15.4 = 7.7 m³ -> agg kg = 7.7 * 1500 = 11550 kg
    # Water = 5544 * 0.45 = 2494.8 liters
    mat = calculate_concrete_materials(volume_m3=10.0, concrete_grade="M25")

    assert mat.dry_volume_factor == DRY_VOLUME_FACTOR
    assert mat.cement_bags == 110.88
    assert mat.cement_kg == 5544.0
    assert mat.sand_m3 == 3.85
    assert mat.aggregate_m3 == 7.7
    assert mat.water_cement_ratio == 0.45
    assert mat.water_liters == 2494.8
    assert mat.mix_ratio == "1 : 1 : 2"


def test_calculate_concrete_materials_all_grades() -> None:
    grades = ["M15", "M20", "M25", "M30", "M35", "M40"]
    for g in grades:
        mat = calculate_concrete_materials(volume_m3=1.0, concrete_grade=g)
        assert mat.cement_bags > 0
        assert mat.sand_m3 > 0
        assert mat.aggregate_m3 > 0
        assert mat.water_liters > 0
        assert mat.water_cement_ratio <= 0.55


def test_calculate_all_nine_members_concrete_volume() -> None:
    # 1. Column (300 x 450 x 3000 mm) = 0.405 m³
    col = calculate_member_concrete_volume("column", "C1", "M25", {"width_mm": 300, "depth_mm": 450, "storey_height_mm": 3000})
    assert col.volume_m3 == 0.405
    assert col.member_type == "COLUMN"
    assert col.materials.cement_bags > 0

    # 2. Beam (230 x 450 x (5000 + 300 + 300) mm) = 0.5796 m³
    beam = calculate_member_concrete_volume("beam", "B1", "M25", {"beam_width_mm": 230, "beam_depth_mm": 450, "clear_span_mm": 5000, "left_support_width_mm": 300, "right_support_width_mm": 300})
    assert beam.volume_m3 == 0.5796
    assert beam.member_type == "BEAM"

    # 3. Footing / Raft (2000 x 2000 x 600 mm) = 2.4 m³
    footing = calculate_member_concrete_volume("footing", "F1", "M25", {"length_mm": 2000, "width_mm": 2000, "depth_mm": 600})
    assert footing.volume_m3 == 2.4
    assert footing.member_type == "FOOTING"

    # 4. Slab (3000 x 4500 x 150 mm) = 2.025 m³
    slab = calculate_member_concrete_volume("slab", "S1", "M25", {"width_lx_mm": 3000, "length_ly_mm": 4500, "thickness_mm": 150})
    assert slab.volume_m3 == 2.025
    assert slab.member_type == "SLAB"

    # 5. Pile (600 mm dia x 12 m depth) -> pi * 0.3^2 * 12 = 3.3929 m³
    pile = calculate_member_concrete_volume("pile", "P1", "M25", {"pile_diameter_mm": 600, "pile_length_m": 12.0})
    assert pile.volume_m3 == pytest.approx(3.3929, rel=1e-3)
    assert pile.member_type == "PILE"

    # 6. Pile Cap (2400 x 2400 x 1000 mm) = 5.76 m³
    pcap = calculate_member_concrete_volume("pile_cap", "PC1", "M25", {"length_mm": 2400, "width_mm": 2400, "depth_mm": 1000})
    assert pcap.volume_m3 == 5.76
    assert pcap.member_type == "PILE_CAP"

    # 7. Pier (800 x 800 x 3000 mm) = 1.92 m³
    pier = calculate_member_concrete_volume("pier", "PR1", "M25", {"dimension_1_mm": 800, "dimension_2_mm": 800, "height_mm": 3000})
    assert pier.volume_m3 == 1.92
    assert pier.member_type == "PIER"

    # 8. Retaining Wall (Base 2.4m x 0.4m x 10m = 9.6m³, Stem 0.4m x 3.5m x 10m = 14.0m³ -> 23.6 m³)
    rw = calculate_member_concrete_volume("retaining_wall", "RW1", "M25", {
        "wall_length_m": 10.0,
        "base_slab_width_mm": 2400,
        "base_slab_thickness_mm": 400,
        "stem_height_mm": 3500,
        "stem_base_thickness_mm": 400,
    })
    assert rw.volume_m3 == 23.6
    assert rw.member_type == "RETAINING_WALL"

    # 9. Staircase
    sc = calculate_member_concrete_volume("staircase", "ST1", "M25", {
        "flight_width_mm": 1200,
        "waist_slab_thickness_mm": 150,
        "riser_mm": 150,
        "tread_mm": 250,
        "num_risers": 10,
        "num_treads": 9,
        "bottom_landing_length_mm": 1200,
        "top_landing_length_mm": 1200,
    })
    assert sc.volume_m3 > 0
    assert sc.member_type == "STAIRCASE"


def test_concrete_calculation_rejects_missing_dynamic_dimensions() -> None:
    with pytest.raises(ValueError, match="Dynamic dimensions missing"):
        calculate_member_concrete_volume("column", "C1", "M25", {})

    with pytest.raises(ValueError, match="Dynamic dimensions missing"):
        calculate_member_concrete_volume("beam", "B1", "M25", {"clear_span_mm": 5000})

    with pytest.raises(ValueError, match="Dynamic dimensions missing"):
        calculate_member_concrete_volume("slab", "S1", "M25", {"thickness_mm": 150})


def test_concrete_volume_endpoint() -> None:
    client = TestClient(app)
    payload = {
        "member_type": "column",
        "member_id": "C10",
        "concrete_grade": "M30",
        "parameters": {
            "width_mm": 400,
            "depth_mm": 600,
            "storey_height_mm": 3500,
        },
    }
    response = client.post("/calculations/concrete-volume", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["member_id"] == "C10"
    assert data["member_type"] == "COLUMN"
    assert data["concrete_grade"] == "M30"
    assert data["volume_m3"] == 0.84  # (400 * 600 * 3500) / 1e9 = 0.84 m³
    assert data["materials"]["cement_bags"] > 0
    assert data["materials"]["sand_m3"] > 0
    assert data["materials"]["aggregate_m3"] > 0
    assert data["materials"]["water_liters"] > 0


def test_question_parser_detects_concrete_intent() -> None:
    q1 = parse_drawing_question("What is the concrete volume of column C12?")
    assert q1.member_type == "column"
    assert q1.member_id == "C12"
    assert q1.calculation_intent == "concrete_volume"
    assert not q1.needs_clarification

    q2 = parse_drawing_question("Calculate cement bags and sand for slab S1")
    assert q2.member_type == "slab"
    assert q2.member_id == "S1"
    assert q2.calculation_intent == "concrete_volume"

    q3 = parse_drawing_question("How much concrete volume is needed for raft foundation?")
    assert q3.member_type == "footing"
    assert q3.calculation_intent == "concrete_volume"


def test_answer_generator_synthesizes_concrete_report() -> None:
    chunk = RetrievedChunk(
        chunk_id="chk1",
        drawing_id="draw1",
        content="Column C12 Storey Height: 3000 mm, Cross section: 300x450 mm, Concrete M25",
        source_reference="drawing:structural_columns.pdf#page=1",
        page_number=1,
    )
    col = calculate_member_concrete_volume("column", "C12", "M25", {"width_mm": 300, "depth_mm": 450, "storey_height_mm": 3000})

    extraction = ExtractionOutput(member_id="C12", member_type="column", confidence=0.95)

    ans = synthesize_engineering_answer(
        question="What is the concrete volume and cement bags for column C12?",
        chunks=[chunk],
        extraction=extraction,
        calculation=col,
        warnings=[],
    )

    assert "Concrete Volume & Material Estimation" in ans
    assert "0.405" in ans
    assert "Cement Required" in ans
    assert "IS 456:2000" in ans


def test_project_bbs_aggregates_concrete_totals() -> None:
    res = generate_consolidated_project_bbs()
    assert res.total_concrete_volume_m3 > 0
    assert res.total_dry_volume_m3 > 0
    assert res.total_cement_bags > 0
    assert res.total_sand_m3 > 0
    assert res.total_aggregate_m3 > 0
