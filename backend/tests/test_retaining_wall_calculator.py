import pytest
from app.engineering.calculators.retaining_wall import RetainingWallScheduleRequest, calculate_retaining_wall_bbs


def test_retaining_wall_bbs_calculation() -> None:
    req = RetainingWallScheduleRequest(
        member_id="RW1",
        wall_length_m=10.0,
        stem_height_mm=3500.0,
        base_slab_width_mm=2400.0,
        base_slab_thickness_mm=400.0,
        stem_base_thickness_mm=400.0,
        toe_projection_mm=600.0,
        main_bar_dia_mm=16.0,
        main_bar_spacing_mm=150.0,
        dist_bar_dia_mm=10.0,
        dist_bar_spacing_mm=200.0,
        curtail_alternate_bars=True,
        clear_cover_mm=50.0,
        concrete_grade="M25",
        steel_grade="FE500",
        source_references=["drawing:retaining-wall.pdf#page=1"],
    )
    result = calculate_retaining_wall_bbs(req)

    assert result.member_id == "RW1"
    assert result.member_type == "RETAINING_WALL"
    assert result.total_weight_kg > 0

    bar_marks = [it.bar_mark for it in result.items]
    assert any("Full Height" in m for m in bar_marks)
    assert any("Curtailed" in m for m in bar_marks)
    assert any("Horizontal Distribution" in m for m in bar_marks)
    assert any("Base Slab Heel" in m for m in bar_marks)
