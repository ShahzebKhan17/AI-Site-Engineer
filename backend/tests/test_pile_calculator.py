import pytest
from app.engineering.calculators.pile import PileScheduleRequest, calculate_pile_bbs


def test_pile_bbs_calculation() -> None:
    req = PileScheduleRequest(
        member_id="P1",
        pile_diameter_mm=600.0,
        pile_length_m=12.0,
        embedment_into_cap_mm=800.0,
        main_bar_dia_mm=20.0,
        num_main_bars=8,
        spiral_bar_dia_mm=8.0,
        spiral_pitch_mm=150.0,
        stiffener_bar_dia_mm=16.0,
        stiffener_spacing_m=2.0,
        clear_cover_mm=50.0,
        concrete_grade="M25",
        steel_grade="FE500",
        source_references=["drawing:pile-foundation.pdf#page=1"],
    )
    result = calculate_pile_bbs(req)

    assert result.member_id == "P1"
    assert result.member_type == "PILE"
    assert result.total_weight_kg > 100.0  # Significant steel tonnage for 12m pile

    # Check that vertical bars, spiral ties, and stiffener rings exist in schedule
    bar_marks = [it.bar_mark for it in result.items]
    assert any("Main Vertical" in m for m in bar_marks)
    assert any("Helical Spiral" in m for m in bar_marks)
    assert any("Master Stiffener" in m for m in bar_marks)

    vert_item = [it for it in result.items if "Main Vertical" in it.bar_mark][0]
    # 12000 mm + max(800, 50*20=1000 mm embedment per IS 2911) - 50 mm cover = 12950.0 mm
    assert vert_item.cutting_length_mm == 12950.0
    assert vert_item.num_bars == 8

