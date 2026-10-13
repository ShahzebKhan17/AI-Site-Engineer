from app.engineering.calculators.footing import FootingMeshRequest, calculate_footing_mesh


def test_calculate_isolated_footing_mesh() -> None:
    req = FootingMeshRequest(
        member_id="F12",
        length_mm=2400,
        width_mm=1800,
        depth_mm=600,
        bar_diameter_mm=12,
        spacing_mm=150,
        clear_cover_mm=50,
        concrete_grade="M25",
        steel_grade="FE500",
        source_references=["drawing:footing_details.pdf#page=4"],
        deduct_bends=True,
    )

    res = calculate_footing_mesh(req)

    assert res.member_id == "F12"
    # Straight long: 2400 - 2*50 = 2300 mm
    # Vert legs: 600 - 2*50 = 500 mm (2 of them = 1000 mm)
    # Bend deduction (2 x 90 deg = -4d = -4*12 = -48 mm)
    # Long cutting length: 2300 + 1000 - 48 = 3252.0 mm
    assert res.cutting_length_long_mm == 3252.0

    # Straight short: 1800 - 100 = 1700 mm
    # Short cutting length: 1700 + 1000 - 48 = 2652.0 mm
    assert res.cutting_length_short_mm == 2652.0

    # Num bars long: int(1700 / 150) + 1 = 11 + 1 = 12
    assert res.num_bars_long == 12

    # Num bars short: int(2300 / 150) + 1 = 15 + 1 = 16
    assert res.num_bars_short == 16

    # Unit weight: 12^2 / 162 = 0.8889 kg/m
    # Total length: (3.252 * 12) + (2.652 * 16) = 39.024 + 42.432 = 81.456 m
    # Total weight: 81.456 * 0.8889 = 72.41 kg
    assert res.total_mesh_weight_kg > 70.0
    assert len(res.breakdown_long) == 4
    assert res.engine_version == "0.2.0"
