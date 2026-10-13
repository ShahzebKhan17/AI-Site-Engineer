import pytest

from app.engineering.calculators.column import calculate_longitudinal_bar
from app.engineering.models import ColumnBarRequest
from app.engineering.rules.is456 import (
    ConcreteGrade,
    SteelGrade,
    StressType,
    calculate_development_length,
    get_design_bond_stress,
)
from app.engineering.rules.sp34 import (
    HookType,
    calculate_bend_deduction,
    calculate_column_lap_length,
    calculate_column_lap_zone,
    calculate_hook_anchorage,
)


def test_design_bond_stress_table() -> None:
    # M20 plain bar in tension: base = 1.2
    base, design = get_design_bond_stress("M20", "Fe250", "tension")
    assert base == 1.2
    assert design == 1.2

    # M20 deformed Fe415 in tension: 1.2 * 1.6 = 1.92
    base, design = get_design_bond_stress("M20", "Fe415", "tension")
    assert base == 1.2
    assert design == 1.92

    # M25 deformed Fe500 in tension: 1.4 * 1.6 = 2.24
    base, design = get_design_bond_stress("M25", "Fe500", "tension")
    assert base == 1.4
    assert design == 2.24

    # M25 deformed Fe500 in compression: 2.24 * 1.25 = 2.80
    base, design = get_design_bond_stress("M25", "Fe500", "compression")
    assert base == 1.4
    assert design == 2.8


def test_development_length_tension() -> None:
    # 16mm, M20, Fe415: Ld = (16 * 0.87 * 415) / (4 * 1.92) = 752.19 mm (factor ~ 47.01)
    res_m20_fe415 = calculate_development_length(16, "M20", "Fe415", "tension")
    assert res_m20_fe415.development_length_factor == pytest.approx(47.01, abs=0.1)
    assert res_m20_fe415.development_length_mm == pytest.approx(752.2, abs=0.2)

    # 16mm, M25, Fe500: Ld = (16 * 0.87 * 500) / (4 * 2.24) = 776.79 mm (factor ~ 48.55)
    res_m25_fe500 = calculate_development_length(16, "M25", "Fe500", "tension")
    assert res_m25_fe500.development_length_factor == pytest.approx(48.55, abs=0.1)
    assert res_m25_fe500.development_length_mm == pytest.approx(776.8, abs=0.2)


def test_development_length_compression() -> None:
    # 16mm, M25, Fe500 compression: Ld = (16 * 435) / (4 * 2.80) = 621.43 mm (factor ~ 38.84)
    res = calculate_development_length(16, "M25", "Fe500", "compression")
    assert res.development_length_factor == pytest.approx(38.84, abs=0.1)
    assert res.development_length_mm == pytest.approx(621.4, abs=0.2)
    assert res.stress_type == "compression"


def test_bend_deductions_sp34() -> None:
    # 16mm bar bend deductions: 1d for 45 deg, 2d for 90 deg, 3d for 135 deg, 4d for 180 deg
    ded_45 = calculate_bend_deduction(16, 45)
    assert ded_45.deduction_mm == 16.0
    assert ded_45.deduction_factor == 1.0

    ded_90 = calculate_bend_deduction(16, 90)
    assert ded_90.deduction_mm == 32.0
    assert ded_90.deduction_factor == 2.0

    ded_135 = calculate_bend_deduction(16, 135)
    assert ded_135.deduction_mm == 48.0
    assert ded_135.deduction_factor == 3.0

    ded_180 = calculate_bend_deduction(16, 180)
    assert ded_180.deduction_mm == 64.0
    assert ded_180.deduction_factor == 4.0


def test_hook_anchorage_is456() -> None:
    # 90 deg standard bend: 8d anchorage
    hook_90 = calculate_hook_anchorage(16, HookType.DEG_90)
    assert hook_90.anchorage_value_mm == 128.0
    assert hook_90.min_tail_length_mm == 65.0  # max(4 * 16 = 64, 65)

    # 180 deg U-hook: 16d anchorage
    hook_180 = calculate_hook_anchorage(16, HookType.DEG_180)
    assert hook_180.anchorage_value_mm == 256.0


def test_column_lap_length_governing_minimums() -> None:
    # Compression: max(Ld_comp, 24d)
    lap_comp = calculate_column_lap_length(16, "M25", "Fe500", StressType.COMPRESSION)
    assert lap_comp.lap_length_mm == pytest.approx(621.4, abs=0.2)
    assert lap_comp.lap_length_mm >= 24 * 16

    # Tension: max(Ld_tens, 30d)
    lap_tens = calculate_column_lap_length(16, "M25", "Fe500", StressType.TENSION)
    assert lap_tens.lap_length_mm == pytest.approx(776.8, abs=0.2)
    assert lap_tens.lap_length_mm >= 30 * 16


def test_column_lap_zone_and_stagger() -> None:
    zone = calculate_column_lap_zone(
        storey_height_mm=3200,
        beam_depth_top_mm=450,
        beam_depth_bottom_mm=0,
        lap_length_mm=621.4,
    )
    assert zone.clear_height_mm == 2750.0
    assert zone.lower_confinement_limit_mm == pytest.approx(687.5, abs=0.1)
    assert zone.lap_zone_start_mm == pytest.approx(687.5, abs=0.1)
    assert zone.lap_zone_end_mm == pytest.approx(2062.5, abs=0.1)
    assert zone.max_stagger_spacing_mm == pytest.approx(807.8, abs=0.2)
    assert len(zone.rule_notes) == 4


def test_column_calculator_is_code_integration() -> None:
    req = ColumnBarRequest(
        member_id="C12",
        bar_diameter_mm=16,
        storey_height_mm=3000,
        footing_embedment_mm=500,
        top_extension_mm=0,
        concrete_grade="M25",
        steel_grade="Fe500",
        source_references=["drawing:structural_schedule.pdf#page=1"],
        use_is_code_rules=True,
        deduct_bends=True,
    )
    res = calculate_longitudinal_bar(req)

    assert res.member_id == "C12"
    # Storey (3000) + Footing (500) + Top (0) + Bend allowance (300) + Lap (621.4) - Bend deduction (32) = 4389.4 mm
    assert res.cutting_length_mm == 4389.4
    assert res.cutting_length_m == 4.389
    assert res.engine_version == "0.2.0"
    assert res.is_code_provisions is not None
    assert "IS 456:2000" in res.is_code_provisions["lap_code_clause"]


def test_validation_errors() -> None:
    with pytest.raises(ValueError, match="Unsupported concrete grade"):
        calculate_development_length(16, "M99", "Fe500")

    with pytest.raises(ValueError, match="Unsupported steel grade"):
        calculate_development_length(16, "M25", "Fe999")

    with pytest.raises(ValueError, match="Bar diameter must be greater than 0"):
        calculate_development_length(0, "M25", "Fe500")
