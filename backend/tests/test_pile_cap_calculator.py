import pytest
from app.engineering.calculators.pile_cap import PileCapScheduleRequest, calculate_pile_cap_bbs


def test_pile_cap_bbs_calculation() -> None:
    req = PileCapScheduleRequest(
        member_id="PC1",
        length_mm=2400.0,
        width_mm=2400.0,
        depth_mm=1000.0,
        num_piles=4,
        bottom_mesh_dia_mm=20.0,
        bottom_mesh_spacing_mm=150.0,
        has_top_mesh=True,
        top_mesh_dia_mm=12.0,
        top_mesh_spacing_mm=200.0,
        num_starter_bars=8,
        starter_bar_dia_mm=20.0,
        clear_cover_mm=50.0,
        concrete_grade="M25",
        steel_grade="FE500",
        source_references=["drawing:pile-cap.pdf#page=1"],
    )
    result = calculate_pile_cap_bbs(req)

    assert result.member_id == "PC1"
    assert result.member_type == "PILE_CAP"
    assert result.total_weight_kg > 0

    bar_marks = [it.bar_mark for it in result.items]
    assert any("Bottom Mesh (X-Direction)" in m for m in bar_marks)
    assert any("Bottom Mesh (Y-Direction)" in m for m in bar_marks)
    assert any("Top Nominal Mesh" in m for m in bar_marks)
    assert any("Column Starter Dowels" in m for m in bar_marks)
