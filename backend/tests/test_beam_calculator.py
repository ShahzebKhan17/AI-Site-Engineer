from app.engineering.calculators.beam import BeamBarRequest, calculate_beam_bar_length


def test_calculate_beam_bottom_continuous_bar() -> None:
    req = BeamBarRequest(
        member_id="B104",
        bar_diameter_mm=16,
        clear_span_mm=5000,
        left_support_width_mm=300,
        right_support_width_mm=300,
        bar_position="bottom_continuous",
        concrete_grade="M25",
        steel_grade="FE500",
        source_references=["drawing:beam_layout.pdf#page=3"],
        use_is_code_rules=True,
        deduct_bends=True,
    )

    res = calculate_beam_bar_length(req)

    assert res.member_id == "B104"
    assert res.bar_position == "bottom_continuous"
    # Clear span: 5000
    # Left support anchorage: 300 - 40 + 12*16 = 452
    # Right support anchorage: 452
    # Bend deduction (2 x 90 deg = -4d = -64)
    # Total = 5000 + 452 + 452 - 64 = 5840.0 mm
    assert res.cutting_length_mm == 5840.0
    assert res.cutting_length_m == 5.840
    assert len(res.breakdown) == 4
    assert res.is_code_provisions is not None
    assert "Ld_tension_mm" in res.is_code_provisions


def test_calculate_beam_top_curtailed_extra_bar() -> None:
    req = BeamBarRequest(
        member_id="B104",
        bar_diameter_mm=16,
        clear_span_mm=5000,
        left_support_width_mm=300,
        right_support_width_mm=300,
        bar_position="top_extra",
        concrete_grade="M25",
        steel_grade="FE500",
        source_references=["drawing:beam_layout.pdf#page=3"],
        use_is_code_rules=True,
        deduct_bends=True,
    )

    res = calculate_beam_bar_length(req)

    # 0.25 * 5000 = 1250 mm
    # Anchorage into support = 452 mm
    # 1 x 90 deg bend deduction = -32 mm
    # Total = 1250 + 452 - 32 = 1670.0 mm
    assert res.cutting_length_mm == 1670.0
    assert res.cutting_length_m == 1.670
    assert any("0.25 * L" in b.label for b in res.breakdown)
