import pytest
from app.engineering.calculators.staircase import StaircaseScheduleRequest, calculate_staircase_bbs


def test_staircase_bbs_calculation() -> None:
    req = StaircaseScheduleRequest(
        member_id="ST1",
        flight_width_mm=1200.0,
        waist_slab_thickness_mm=150.0,
        riser_mm=150.0,
        tread_mm=250.0,
        num_risers=10,
        num_treads=9,
        bottom_landing_length_mm=1200.0,
        top_landing_length_mm=1200.0,
        main_bar_dia_mm=12.0,
        main_bar_spacing_mm=150.0,
        dist_bar_dia_mm=8.0,
        dist_bar_spacing_mm=175.0,
        clear_cover_mm=20.0,
        concrete_grade="M25",
        steel_grade="FE500",
        source_references=["drawing:staircase.pdf#page=1"],
    )
    result = calculate_staircase_bbs(req)

    assert result.member_id == "ST1"
    assert result.member_type == "STAIRCASE"
    assert result.total_weight_kg > 0

    bar_marks = [it.bar_mark for it in result.items]
    assert any("Main Waist Tensile" in m for m in bar_marks)
    assert any("Top Negative Junction" in m for m in bar_marks)
    assert any("Transverse Distribution" in m for m in bar_marks)

    # Check that inclined flight length was calculated via Pythagorean theorem: sqrt((9*250)^2 + (10*150)^2)
    # sqrt(2250^2 + 1500^2) = sqrt(5062500 + 2250000) = sqrt(7312500) ≈ 2704.16 mm
    assert "2704.2 mm" in result.is_code_provisions["Inclined Flight Length"]
