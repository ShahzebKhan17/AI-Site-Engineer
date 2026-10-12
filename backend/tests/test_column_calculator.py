from app.engineering.calculators.column import calculate_longitudinal_bar
from app.engineering.models import ColumnBarRequest


def test_calculates_total_from_reviewed_lengths() -> None:
    result = calculate_longitudinal_bar(ColumnBarRequest(
        member_id="c12",
        bar_diameter_mm=16,
        storey_height_mm=3200,
        footing_embedment_mm=500,
        top_extension_mm=300,
        bend_allowance_mm=75,
        lap_length_mm=800,
        concrete_grade="M25",
        steel_grade="Fe500",
        source_references=["drawing:column-schedule.pdf#page=2"],
    ))
    assert result.member_id == "C12"
    assert result.cutting_length_mm == 4875
    assert result.cutting_length_m == 4.875
