import pytest
from app.engineering.calculators.slab import SlabScheduleRequest, calculate_slab_bbs


def test_slab_one_way_and_two_way_classification() -> None:
    # Two-way slab (Ly/Lx = 4500/3000 = 1.5 <= 2)
    two_way_req = SlabScheduleRequest(
        member_id="S1",
        length_ly_mm=4500.0,
        width_lx_mm=3000.0,
        thickness_mm=150.0,
        support_width_mm=230.0,
        main_bar_dia_mm=10.0,
        main_bar_spacing_mm=150.0,
        dist_bar_dia_mm=8.0,
        dist_bar_spacing_mm=175.0,
        clear_cover_mm=20.0,
        is_cranked=True,
        concrete_grade="M25",
        steel_grade="FE500",
        source_references=["drawing:slab-details.pdf#page=1"],
    )
    result = calculate_slab_bbs(two_way_req)
    assert result.member_id == "S1"
    assert result.member_type == "SLAB"
    assert "Two-Way Slab" in result.is_code_provisions["Aspect Ratio (Ly/Lx)"]
    assert len(result.items) >= 3  # straight, cranked, distribution, chairs
    assert result.total_weight_kg > 0
    assert result.cutting_length_m > 3.0


def test_slab_one_way_span() -> None:
    # One-way slab (Ly/Lx = 7000/3000 = 2.33 > 2)
    one_way_req = SlabScheduleRequest(
        member_id="S2",
        length_ly_mm=7000.0,
        width_lx_mm=3000.0,
        thickness_mm=125.0,
        support_width_mm=230.0,
        main_bar_dia_mm=10.0,
        main_bar_spacing_mm=150.0,
        dist_bar_dia_mm=8.0,
        dist_bar_spacing_mm=200.0,
        is_cranked=False,
        source_references=["drawing:slab.pdf#page=2"],
    )
    result = calculate_slab_bbs(one_way_req)
    assert "One-Way Slab" in result.is_code_provisions["Aspect Ratio (Ly/Lx)"]
    # Main straight bars + distribution + chairs
    bar_marks = [it.bar_mark for it in result.items]
    assert any("Main Bottom" in m for m in bar_marks)
    assert any("Distribution" in m for m in bar_marks)
