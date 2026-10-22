import pytest
from app.engineering.optimization import (
    optimize_cutting_stock,
    unit_weight,
    STANDARD_STOCK_LENGTH_MM,
)


def test_unit_weight_formula():
    """Verify standard rebar unit weight d^2 / 162."""
    assert unit_weight(16) == round((16 * 16) / 162, 3)
    assert unit_weight(8) == round(64 / 162, 3)
    assert unit_weight(25) == round(625 / 162, 3)


def test_cutting_stock_packing():
    """Verify that cutting pieces are packed into standard 12m stock bars with zero negative scrap."""
    test_items = [
        {
            "member_id": "C12",
            "bar_mark": "Main Bar",
            "bar_diameter_mm": 16,
            "cutting_length_mm": 4389.4,
            "num_bars": 4,
        },
        {
            "member_id": "B4",
            "bar_mark": "Bottom Bar",
            "bar_diameter_mm": 16,
            "cutting_length_mm": 5600.0,
            "num_bars": 2,
        },
    ]

    result = optimize_cutting_stock(test_items, project_id="Test-Project")

    assert result.project_id == "Test-Project"
    assert result.total_stock_bars_12m > 0
    assert result.total_gross_weight_tonnes >= result.total_net_weight_tonnes
    assert result.overall_wastage_percentage >= 0.0

    # Verify per-diameter summary
    dia16_summary = next(s for s in result.diameter_summaries if s.bar_diameter_mm == 16)
    assert dia16_summary.total_pieces_required == 6  # 4 + 2

    # Check each pattern doesn't exceed 12m length
    for pat in dia16_summary.patterns:
        assert pat.total_cut_length_mm <= STANDARD_STOCK_LENGTH_MM + 0.1
        assert pat.waste_scrap_mm >= 0.0
        assert pat.waste_scrap_mm == round(STANDARD_STOCK_LENGTH_MM - pat.total_cut_length_mm, 1)


def test_large_bar_segmentation():
    """Verify that bars longer than 12m are divided into 12m full bars and remainder."""
    test_items = [
        {
            "member_id": "P1",
            "bar_mark": "Deep Pile Bar",
            "bar_diameter_mm": 25,
            "cutting_length_mm": 15000.0,  # 15 meters
            "num_bars": 1,
        }
    ]

    result = optimize_cutting_stock(test_items)
    dia25_summary = next(s for s in result.diameter_summaries if s.bar_diameter_mm == 25)
    assert dia25_summary.stock_bars_12m_required == 2
