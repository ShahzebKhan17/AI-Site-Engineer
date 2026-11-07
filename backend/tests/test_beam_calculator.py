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


def test_calculate_beam_complete_bbs_schedule() -> None:
    from app.engineering.calculators.beam import BeamScheduleRequest, calculate_beam_bbs

    req = BeamScheduleRequest(
        member_id="BM-01",
        clear_span_mm=4000.0,
        beam_width_mm=230.0,
        beam_depth_mm=450.0,
        left_support_width_mm=300.0,
        right_support_width_mm=300.0,
        clear_cover_mm=25.0,
        bottom_bars_count=3,
        bottom_bar_dia_mm=16.0,
        top_bars_count=2,
        top_bar_dia_mm=12.0,
        stirrup_dia_mm=8.0,
        stirrup_spacing_mm=150.0,
        concrete_grade="M25",
        steel_grade="FE500",
    )

    res = calculate_beam_bbs(req)

    assert res.member_id == "BM-01"
    assert res.member_type == "BEAM"
    assert len(res.items) == 3

    # Item 1: Bottom bars (3-T16)
    bot = res.items[0]
    assert bot.bar_mark == "Bottom Longitudinal Bars"
    assert bot.bar_diameter_mm == 16.0
    assert bot.num_bars == 3
    # 4000 + 452 + 452 - 64 = 4840.0 mm
    assert bot.cutting_length_mm == 4840.0
    assert bot.total_weight_kg == 22.94

    # Item 2: Top bars (2-T12)
    top = res.items[1]
    assert top.bar_mark == "Top Longitudinal Hanger Bars"
    assert top.bar_diameter_mm == 12.0
    assert top.num_bars == 2
    # 4000 + 404 + 404 - 48 = 4760.0 mm
    assert top.cutting_length_mm == 4760.0
    assert top.total_weight_kg == 8.46

    # Item 3: Stirrups (T8 @ 150 c/c)
    st = res.items[2]
    assert st.bar_mark == "Shear Stirrups / Links"
    assert st.bar_diameter_mm == 8.0
    # floor(4000 / 150) + 1 = 26 + 1 = 27
    assert st.num_bars == 27
    # (180*2 + 400*2) + 160 - 96 = 1160 + 64 = 1224.0 mm
    assert st.cutting_length_mm == 1224.0
    assert st.total_weight_kg == 13.05

    # Total steel weight
    assert res.total_weight_kg == round(22.94 + 8.46 + 13.05, 2)

    # Concrete volume
    # 0.23 * 0.45 * 4.0 = 0.414 m3
    assert res.concrete_volume_m3 == 0.414
    assert res.cement_bags is not None and res.cement_bags > 0

