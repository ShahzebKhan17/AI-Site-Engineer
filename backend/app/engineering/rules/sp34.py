"""SP 34:1987 Handbook on Concrete Reinforcement and Detailing and IS 456 detailing rules."""

from enum import Enum
from pydantic import BaseModel, Field

from app.engineering.rules.is456 import (
    StressType,
    calculate_development_length,
    normalize_concrete_grade,
    normalize_steel_grade,
    normalize_stress_type,
)


class HookType(str, Enum):
    DEG_90 = "90_degree"
    DEG_135 = "135_degree"
    DEG_180 = "180_degree"


class BendDeductionResult(BaseModel):
    angle_degrees: float
    bar_diameter_mm: float
    deduction_mm: float
    deduction_factor: float
    clause_reference: str = "SP 34:1987 Cl. 3.2 & IS 2502"


class HookAnchorageResult(BaseModel):
    hook_type: str
    bar_diameter_mm: float
    anchorage_value_mm: float
    anchorage_factor: float
    min_tail_length_mm: float
    clause_reference: str = "IS 456:2000 Cl. 26.2.2.1 & SP 34 Cl. 3.3"


class LapLengthResult(BaseModel):
    bar_diameter_mm: float
    concrete_grade: str
    steel_grade: str
    lap_length_mm: float
    lap_length_factor: float
    governing_criteria: str
    clause_reference: str = "IS 456:2000 Cl. 26.2.5.1"


class LapZoneResult(BaseModel):
    storey_height_mm: float
    clear_height_mm: float
    lower_confinement_limit_mm: float
    upper_confinement_limit_mm: float
    lap_zone_start_mm: float
    lap_zone_end_mm: float
    max_stagger_spacing_mm: float
    rule_notes: list[str]
    clause_reference: str = "IS 456:2000 Cl. 26.2.5.1 & SP 34 Cl. 7.2"


def calculate_bend_deduction(bar_diameter_mm: float, angle_degrees: float) -> BendDeductionResult:
    """Calculate bar elongation deduction for standard bends per SP 34 / IS 2502.

    Standard allowances:
      - 45 deg: 1 * phi
      - 90 deg: 2 * phi
      - 135 deg: 3 * phi
      - 180 deg: 4 * phi
    """
    if bar_diameter_mm <= 0:
        raise ValueError("Bar diameter must be greater than 0 mm.")

    factor = (angle_degrees / 45.0) * 1.0
    deduction = round(factor * bar_diameter_mm, 1)

    return BendDeductionResult(
        angle_degrees=angle_degrees,
        bar_diameter_mm=bar_diameter_mm,
        deduction_mm=deduction,
        deduction_factor=round(factor, 2),
    )


def calculate_hook_anchorage(
    bar_diameter_mm: float,
    hook_type: str | HookType = HookType.DEG_90,
) -> HookAnchorageResult:
    """Calculate equivalent anchorage value of hooks and bends per IS 456:2000 Cl. 26.2.2.1.

    Anchorage values:
      - 90 deg bend: 8 * phi (with min tail extension 4 * phi)
      - 135 deg hook: 12 * phi (with min tail extension 6 * phi)
      - 180 deg U-hook: 16 * phi (with min tail extension 4 * phi)
    """
    if bar_diameter_mm <= 0:
        raise ValueError("Bar diameter must be greater than 0 mm.")

    h_type = hook_type if isinstance(hook_type, HookType) else HookType(hook_type)

    if h_type == HookType.DEG_90:
        factor = 8.0
        tail = max(4.0 * bar_diameter_mm, 65.0)
    elif h_type == HookType.DEG_135:
        factor = 12.0
        tail = max(6.0 * bar_diameter_mm, 65.0)
    else:
        factor = 16.0
        tail = max(4.0 * bar_diameter_mm, 65.0)

    anchorage_val = factor * bar_diameter_mm

    return HookAnchorageResult(
        hook_type=h_type.value,
        bar_diameter_mm=bar_diameter_mm,
        anchorage_value_mm=round(anchorage_val, 1),
        anchorage_factor=factor,
        min_tail_length_mm=round(tail, 1),
    )


def calculate_column_lap_length(
    bar_diameter_mm: float,
    concrete_grade: str,
    steel_grade: str,
    stress_type: str | StressType = StressType.COMPRESSION,
) -> LapLengthResult:
    """Calculate column reinforcement lap length per IS 456:2000 Cl. 26.2.5.1.

    Rules:
      - Compression lap length shall not be less than Ld (compression) or 24 * phi.
      - Tension lap length shall not be less than Ld (tension) or 30 * phi.
    """
    c_grade = normalize_concrete_grade(concrete_grade)
    s_grade = normalize_steel_grade(steel_grade)
    s_type = normalize_stress_type(stress_type)

    ld_result = calculate_development_length(bar_diameter_mm, c_grade, s_grade, s_type)

    if s_type == StressType.COMPRESSION:
        min_rule_mm = 24.0 * bar_diameter_mm
        rule_desc = "max(Ld_compression, 24 * ϕ)"
    else:
        min_rule_mm = 30.0 * bar_diameter_mm
        rule_desc = "max(Ld_tension, 30 * ϕ)"

    lap_len = max(ld_result.development_length_mm, min_rule_mm)
    factor = round(lap_len / bar_diameter_mm, 2)

    return LapLengthResult(
        bar_diameter_mm=bar_diameter_mm,
        concrete_grade=c_grade.value,
        steel_grade=s_grade.value,
        lap_length_mm=round(lap_len, 1),
        lap_length_factor=factor,
        governing_criteria=rule_desc,
    )


def calculate_column_lap_zone(
    storey_height_mm: float,
    beam_depth_top_mm: float = 450.0,
    beam_depth_bottom_mm: float = 0.0,
    lap_length_mm: float = 0.0,
) -> LapZoneResult:
    """Calculate permissible lapping zones for columns per SP 34 Cl. 7.2 and IS 456 Cl. 26.2.5.1.

    Lapping provisions:
      - Clear storey height H_clear = storey_height - beam_depth_top - beam_depth_bottom.
      - No laps permitted in bottom confinement zone (max(H_clear / 4, 450mm, max_dim)).
      - Permissible lapping zone is the central half (H_clear / 2) of the clear storey height.
      - Maximum 50% of column bars shall be lapped at any single cross section.
      - Stagger distance between adjacent lap sections must be at least 1.3 * lap_length.
    """
    if storey_height_mm <= 0:
        raise ValueError("Storey height must be greater than 0 mm.")

    clear_height = max(storey_height_mm - beam_depth_top_mm - beam_depth_bottom_mm, 0.0)
    confinement_extent = max(clear_height / 4.0, 450.0)

    lap_zone_start = confinement_extent + beam_depth_bottom_mm
    lap_zone_end = max(lap_zone_start, storey_height_mm - beam_depth_top_mm - confinement_extent)

    stagger_spacing = round(1.3 * lap_length_mm, 1) if lap_length_mm > 0 else 0.0

    notes = [
        "Lapping is restricted to the central zone of the column height.",
        "No lapping permitted within beam-column junction or plastic hinge zone.",
        "Maximum 50% longitudinal bars can be spliced at any single section.",
        f"Stagger distance between spliced bars must be at least 1.3 * lap length ({stagger_spacing} mm).",
    ]

    return LapZoneResult(
        storey_height_mm=storey_height_mm,
        clear_height_mm=round(clear_height, 1),
        lower_confinement_limit_mm=round(confinement_extent, 1),
        upper_confinement_limit_mm=round(confinement_extent, 1),
        lap_zone_start_mm=round(lap_zone_start, 1),
        lap_zone_end_mm=round(lap_zone_end, 1),
        max_stagger_spacing_mm=stagger_spacing,
        rule_notes=notes,
    )
