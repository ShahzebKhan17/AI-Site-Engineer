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


def test_column_c01_without_footing_embedment_and_lap() -> None:
    """Test Column C-01: 3000mm height, no footing embedment, default +300mm bend, 2D bend deduction, 0 lap (<=12m), 8 bars."""
    req = ColumnBarRequest(
        member_id="C-01",
        bar_diameter_mm=16,
        num_bars=8,
        storey_height_mm=3000,
        footing_embedment_mm=0,
        top_extension_mm=0,
        bend_allowance_mm=0,  # defaults to 300mm
        concrete_grade="M25",
        steel_grade="Fe500",
        source_references=["drawing:TEST-COL-001"],
        use_is_code_rules=True,
        deduct_bends=True,
    )
    result = calculate_longitudinal_bar(req)

    assert result.member_id == "C-01"
    # Storey (3000) + Bend allowance (300) - Bend deduction 2d (32) = 3268 mm
    assert result.cutting_length_mm == 3268.0
    assert result.cutting_length_m == 3.268
    # Breakdown does NOT include footing embedment or lap length
    labels = [b.label for b in result.breakdown]
    assert "Footing embedment" not in labels
    assert "Lap length" not in labels
    assert "Bend allowance" in labels
    assert "Bend deduction (90 deg)" in labels

    bbs = result.to_bbs_result()
    assert bbs.items[0].num_bars == 8
    assert bbs.items[0].cutting_length_m == 3.268
    assert bbs.items[0].total_length_m == round(3.268 * 8, 3)  # 26.144 m
    # Unit weight = 16^2 / 162 = 1.580 kg/m; Total weight = 26.144 * 1.580 = 41.31 kg
    assert bbs.items[0].total_weight_kg == 41.31

    # Verify Item 2: Lateral ties (8mm dia)
    assert len(bbs.items) == 2
    tie_item = bbs.items[1]
    assert tie_item.bar_mark == "Lateral Ties / Stirrups"
    assert tie_item.bar_diameter_mm == 8.0
    assert tie_item.num_bars > 0
    assert tie_item.cutting_length_m > 0.0
    assert tie_item.total_weight_kg > 0.0


def test_column_custom_bend_allowance_20d() -> None:
    """Test Column with custom bend allowance of 20 times the diameter (20 * 16 = 320mm)."""
    req = ColumnBarRequest(
        member_id="C-02",
        bar_diameter_mm=16,
        num_bars=8,
        storey_height_mm=3000,
        footing_embedment_mm=0,
        top_extension_mm=0,
        bend_allowance_mm=20.0 * 16.0,  # 320 mm
        concrete_grade="M25",
        steel_grade="Fe500",
        source_references=["drawing:TEST-COL-001"],
        use_is_code_rules=True,
        deduct_bends=True,
    )
    result = calculate_longitudinal_bar(req)

    # Storey (3000) + Bend allowance (320) - Bend deduction 2d (32) = 3288 mm
    assert result.cutting_length_mm == 3288.0
    assert result.cutting_length_m == 3.288

