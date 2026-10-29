import pytest
from app.engineering.project_bbs import generate_consolidated_project_bbs


def test_consolidated_project_bbs_generates_all_members_and_tonnage() -> None:
    res = generate_consolidated_project_bbs(chunks=None, project_id="Test G+8 Project", allow_demo_fallback=True)

    assert res.project_id == "Test G+8 Project"
    assert res.total_members_count >= 8  # Columns, beams, footings, slabs, piles, pile caps, stairs, piers, retaining walls
    assert res.total_steel_kg > 0
    assert res.total_steel_tonnes > 0
    assert len(res.diameter_summaries) >= 4  # e.g. 8mm, 10mm, 12mm, 16mm, 20mm, 25mm

    # Verify diameter summaries have valid formula calculations
    for d in res.diameter_summaries:
        expected_unit_wt = round((d.bar_diameter_mm ** 2) / 162.0, 3)
        assert d.unit_weight_kg_m == expected_unit_wt
        assert d.total_weight_kg > 0
        assert d.total_weight_tonnes == round(d.total_weight_kg / 1000.0, 3)

    # Verify items have breakdown formulas populated for on-click inspection
    assert len(res.items) > 10
    sample_item = res.items[0]
    assert sample_item.cutting_length_mm > 0
    assert sample_item.unit_weight_kg_m > 0
    assert sample_item.total_weight_kg > 0
    assert len(sample_item.breakdown) > 0


def test_consolidated_project_bbs_zero_state_without_demo_fallback() -> None:
    res = generate_consolidated_project_bbs(chunks=[], project_id="Empty Project", allow_demo_fallback=False)
    assert res.total_members_count == 0
    assert res.total_steel_kg == 0.0
    assert res.total_steel_tonnes == 0.0
    assert len(res.items) == 0
    assert len(res.diameter_summaries) == 0


def test_consolidated_project_bbs_uses_candidate_members_cache_c01() -> None:
    candidate_c01 = {
        "member_id": "C-01",
        "member_type": "column",
        "num_bars": 8,
        "main_bar_diameter_mm": 16.0,
        "secondary_bar_diameter_mm": 8.0,
        "concrete_grade": "M25",
        "steel_grade": "FE500",
        "dimensions": {
            "width_mm": 300.0,
            "depth_mm": 450.0,
            "storey_height_mm": 3000.0,
            "tie_spacing_end_mm": 100.0,
            "end_zone_length_mm": 300.0,
            "tie_spacing_mid_mm": 150.0,
        },
    }
    res = generate_consolidated_project_bbs(
        chunks=[{"id": "c1", "content": "Column C-01 details", "entity_code": "C-01"}],
        project_id="Structural Project",
        candidate_members_cache=[candidate_c01],
    )
    assert res.total_members_count == 1
    assert len(res.items) == 2

    # Verify Main Longitudinal rebar is 16mm (NOT 8mm)
    main_item = next(it for it in res.items if it.bar_mark == "Main Longitudinal")
    assert main_item.bar_diameter_mm == 16.0
    assert main_item.num_bars == 8

    # Verify Lateral Ties cutting length is 1.244m (NOT 0.944m)
    tie_item = next(it for it in res.items if "Lateral Ties" in it.bar_mark)
    assert tie_item.bar_diameter_mm == 8.0
    assert tie_item.cutting_length_m == 1.244
    assert tie_item.cutting_length_mm == 1244.0

