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


def test_staircase_st01_single_flight_without_landings() -> None:
    """Verify RCC Staircase Test Case ST-01: single straight flight without landings."""
    req = StaircaseScheduleRequest(
        member_id="ST-01",
        flight_width_mm=1200.0,
        waist_slab_thickness_mm=150.0,
        riser_mm=150.0,
        tread_mm=270.0,
        num_risers=10,
        num_treads=10,
        bottom_landing_length_mm=0.0,
        top_landing_length_mm=0.0,
        main_bar_dia_mm=12.0,
        main_bar_spacing_mm=150.0,
        dist_bar_dia_mm=8.0,
        dist_bar_spacing_mm=200.0,
        clear_cover_mm=25.0,
        concrete_grade="M25",
        steel_grade="FE500",
        source_references=["drawing:ST-01_spec.png"],
    )
    result = calculate_staircase_bbs(req)

    assert result.member_id == "ST-01"
    assert result.member_type == "STAIRCASE"
    # Inclined flight length: sqrt((10*270)^2 + (10*150)^2) = sqrt(2700^2 + 1500^2) = sqrt(7290000 + 2250000) = sqrt(9540000) ≈ 3088.69 mm
    assert "3088.7 mm" in result.is_code_provisions["Inclined Flight Length"]

    # In single straight flight without landings, there are no waist-landing junction extra bars
    marks = [it.bar_mark for it in result.items]
    assert "Main Waist Tensile Rebar" in marks
    assert "Transverse Distribution Reinforcement" in marks
    assert "Top Negative Junction Extra Bars" not in marks

    # Concrete volume should be strictly waist + steps without landing slabs
    # Waist = 3.0887 * 1.2 * 0.15 = 0.556 m3
    # Steps = 10 * 0.5 * 0.15 * 0.27 * 1.2 = 0.243 m3
    # Total = ~0.799 m3
    assert result.concrete_volume_m3 is not None
    assert 0.79 <= result.concrete_volume_m3 <= 0.81

    # Verify breakdown contains mathematical formulas
    main_item = next(it for it in result.items if it.bar_mark == "Main Waist Tensile Rebar")
    for row in main_item.breakdown:
        assert row.formula is not None
        assert row.explanation is not None
