import pytest
from app.engineering.calculators.pier import PierScheduleRequest, calculate_pier_bbs


def test_rectangular_pier_bbs_calculation() -> None:
    req = PierScheduleRequest(
        member_id="PR1",
        shape="rectangular",
        dimension_1_mm=800.0,
        dimension_2_mm=800.0,
        height_mm=3000.0,
        starter_embedment_mm=800.0,
        cap_anchorage_mm=800.0,
        main_bar_dia_mm=25.0,
        num_main_bars=12,
        tie_bar_dia_mm=10.0,
        tie_spacing_mm=150.0,
        clear_cover_mm=40.0,
        concrete_grade="M35",
        steel_grade="FE500",
        source_references=["drawing:pier-details.pdf#page=1"],
    )
    result = calculate_pier_bbs(req)

    assert result.member_id == "PR1"
    assert result.member_type == "PIER"
    assert result.total_weight_kg > 0

    bar_marks = [it.bar_mark for it in result.items]
    assert any("Main Vertical" in m for m in bar_marks)
    assert any("Lateral Confining Ties" in m for m in bar_marks)


def test_circular_pier_bbs_calculation() -> None:
    req = PierScheduleRequest(
        member_id="PR2",
        shape="circular",
        dimension_1_mm=900.0,
        dimension_2_mm=900.0,
        height_mm=4000.0,
        starter_embedment_mm=1000.0,
        cap_anchorage_mm=1000.0,
        main_bar_dia_mm=25.0,
        num_main_bars=16,
        tie_bar_dia_mm=10.0,
        tie_spacing_mm=150.0,
        clear_cover_mm=40.0,
        concrete_grade="M35",
        steel_grade="FE500",
        source_references=["drawing:bridge-pier.pdf#page=2"],
    )
    result = calculate_pier_bbs(req)
    assert result.member_type == "PIER"
    tie_item = [it for it in result.items if "Lateral Confining Ties" in it.bar_mark][0]
    assert "Circular hoop tie" in tie_item.shape_description
