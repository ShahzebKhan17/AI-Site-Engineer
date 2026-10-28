import math

from app.engineering.models import CalculationBreakdown, ColumnBarRequest, ColumnBarResult
from app.engineering.rules.sp34 import (
    calculate_bend_deduction,
    calculate_column_lap_length,
)

ENGINE_VERSION = "0.2.0"


def calculate_longitudinal_bar(request: ColumnBarRequest) -> ColumnBarResult:
    """Calculate column longitudinal bar and lateral tie cutting lengths.

    Supports:
      1. Explicit mode (default): Uses reviewed, exact values from drawings.
      2. IS Code mode (use_is_code_rules=True): Dynamically resolves development length,
         lap length, lateral tie pitch, and bend allowances per IS 456:2000 & SP 34:1987.
    """
    assumptions: list[str] = []
    is_code_provisions: dict[str, str | float] = {}

    lap_length_mm = request.lap_length_mm
    bend_allowance_mm = request.bend_allowance_mm
    bend_deduction_mm = 0.0

    if request.use_is_code_rules:
        # Resolve lap length: commercial stock bar length is 12.0m (12000 mm).
        # Lap length is added if bar exceeds 12.0m, if column has footing starter embedment, or if explicitly requested.
        total_lift_mm = request.storey_height_mm + request.footing_embedment_mm + request.top_extension_mm
        if lap_length_mm <= 0:
            if request.has_lap_splice or request.footing_embedment_mm > 0 or total_lift_mm > 12000.0:
                lap_result = calculate_column_lap_length(
                    bar_diameter_mm=request.bar_diameter_mm,
                    concrete_grade=request.concrete_grade,
                    steel_grade=request.steel_grade,
                )
                lap_length_mm = lap_result.lap_length_mm
                assumptions.append(
                    f"Lap length calculated as {lap_length_mm} mm ({lap_result.lap_length_factor}d) per {lap_result.clause_reference}."
                )
                is_code_provisions["lap_length_mm"] = lap_length_mm
                is_code_provisions["lap_code_clause"] = lap_result.clause_reference
            else:
                lap_length_mm = 0.0
                assumptions.append("No lap splice required: total length <= 12.0m commercial stock bar length and no starter lap specified.")
        else:
            assumptions.append(f"Explicit lap length of {lap_length_mm} mm provided from drawing schedule.")

        # Resolve bend allowance: if nothing is specified in drawing, default is +300 mm
        if bend_allowance_mm <= 0:
            bend_allowance_mm = max(300.0, round(16.0 * request.bar_diameter_mm, 1))
            assumptions.append(
                f"Bend allowance calculated as {bend_allowance_mm} mm (min 300 mm standard detailing) as none was specified."
            )
            is_code_provisions["footing_bend_allowance_mm"] = bend_allowance_mm
        else:
            assumptions.append(f"Bend allowance of {bend_allowance_mm} mm applied from drawing specification.")
            is_code_provisions["footing_bend_allowance_mm"] = bend_allowance_mm

        # Calculate bend deduction (1D for 45°, 2D for 90°, 3D for 135°, 4D for 180°)
        if request.deduct_bends and bend_allowance_mm > 0:
            deduction_result = calculate_bend_deduction(request.bar_diameter_mm, angle_degrees=90.0)
            bend_deduction_mm = deduction_result.deduction_mm
            assumptions.append(
                f"Bend deduction of {bend_deduction_mm} mm (2d) applied for 90-degree bend per {deduction_result.clause_reference}."
            )
            is_code_provisions["bend_deduction_mm"] = bend_deduction_mm
    else:
        assumptions = [
            "All input dimensions were explicitly supplied and require engineer review.",
            "Lap and development values are supplied inputs; IS code provisions were not auto-inferred.",
        ]

    breakdown = [
        CalculationBreakdown(label="Storey height", length_mm=request.storey_height_mm),
    ]
    if request.footing_embedment_mm > 0:
        breakdown.append(CalculationBreakdown(label="Footing embedment", length_mm=request.footing_embedment_mm))
    breakdown.append(CalculationBreakdown(label="Top extension", length_mm=request.top_extension_mm))
    if bend_allowance_mm > 0:
        breakdown.append(CalculationBreakdown(label="Bend allowance", length_mm=bend_allowance_mm))
    if lap_length_mm > 0:
        breakdown.append(CalculationBreakdown(label="Lap length", length_mm=lap_length_mm))
    if bend_deduction_mm > 0:
        breakdown.append(CalculationBreakdown(label="Bend deduction (90 deg)", length_mm=-bend_deduction_mm))

    total = sum(item.length_mm for item in breakdown)
    c_vol = round((request.column_width_mm * request.column_depth_mm * request.storey_height_mm) / 1e9, 4) if (request.column_width_mm and request.column_depth_mm) else 0.0

    # Lateral Ties / Stirrups calculation per IS 456 Cl. 26.5.3.2 & SP 34 Cl. 7.2
    col_w = request.column_width_mm or 300.0
    col_d = request.column_depth_mm or 300.0
    cover = request.clear_cover_mm if request.clear_cover_mm is not None else 40.0
    tie_dia = request.tie_bar_dia_mm or 8.0

    has_dual_zone = bool(
        request.tie_spacing_end_mm and request.tie_spacing_end_mm > 0
        and request.end_zone_length_mm and request.end_zone_length_mm > 0
    )

    if has_dual_zone:
        end_len = request.end_zone_length_mm or 300.0
        end_pitch = request.tie_spacing_end_mm or 100.0
        mid_pitch = request.tie_spacing_mid_mm or request.tie_spacing_mm or 150.0

        if (2.0 * end_len) < request.storey_height_mm:
            mid_len = request.storey_height_mm - (2.0 * end_len)
            ties_each_end = int(round(end_len / end_pitch))
            ties_mid = int(round(mid_len / mid_pitch))
            num_ties = (2 * ties_each_end) + ties_mid
            actual_pitch = mid_pitch
        else:
            mid_len = 0.0
            ties_each_end = int(math.floor(request.storey_height_mm / end_pitch)) + 1
            ties_mid = 0
            num_ties = ties_each_end
            actual_pitch = end_pitch
    else:
        max_code_pitch = min(col_w, col_d, 16.0 * request.bar_diameter_mm, 300.0)
        actual_pitch = request.tie_spacing_mm if (request.tie_spacing_mm and request.tie_spacing_mm > 0) else max_code_pitch
        actual_pitch = min(actual_pitch, max_code_pitch)
        num_ties = int(math.floor(request.storey_height_mm / actual_pitch)) + 1 if actual_pitch > 0 else 0

    w_core = max(50.0, col_w - (2.0 * cover))
    d_core = max(50.0, col_d - (2.0 * cover))
    hook_ext = 2.0 * (10.0 * tie_dia)
    bend_ded_135 = calculate_bend_deduction(tie_dia, 135.0).deduction_mm if request.deduct_bends else 0.0
    bend_ded_90_tie = calculate_bend_deduction(tie_dia, 90.0).deduction_mm if request.deduct_bends else 0.0
    total_ded = (3.0 * bend_ded_90_tie) + (2.0 * bend_ded_135)
    tie_cut_mm = (2.0 * (w_core + d_core)) + hook_ext - total_ded
    tie_m = round(tie_cut_mm / 1000.0, 3)

    tie_breakdown = [
        CalculationBreakdown(label="Core perimeter (2*(w+d))", length_mm=round(2.0 * (w_core + d_core), 1), clause="IS 456 Cl. 26.5.3"),
        CalculationBreakdown(label="Seismic 135° hook extensions (2 x 10d)", length_mm=round(hook_ext, 1), clause="SP 34 Cl. 7.2"),
    ]
    if total_ded > 0:
        tie_breakdown.append(CalculationBreakdown(label="Bend deductions (3x90° + 2x135°)", length_mm=-round(total_ded, 1), clause="IS 2502"))

    if request.use_is_code_rules:
        if has_dual_zone:
            is_code_provisions["lateral_tie_pitch_mm"] = (
                f"End zones: {request.tie_spacing_end_mm:.0f} mm c/c (2x{request.end_zone_length_mm:.0f} mm), "
                f"Mid zone: {request.tie_spacing_mid_mm or request.tie_spacing_mm:.0f} mm c/c"
            )
            is_code_provisions["lateral_tie_count_derivation"] = (
                f"2 x ({request.end_zone_length_mm:.0f}/{request.tie_spacing_end_mm:.0f}) + "
                f"({mid_len:.0f}/{mid_pitch:.0f}) = {2 * ties_each_end} + {ties_mid} = {num_ties} ties"
            )
        else:
            is_code_provisions["lateral_tie_pitch_mm"] = f"{actual_pitch:.0f} mm (IS 456 Cl. 26.5.3.2)"
        is_code_provisions["lateral_tie_shape"] = "Closed rectangular tie with 135° seismic hooks"

    return ColumnBarResult(
        member_id=request.member_id,
        cutting_length_mm=round(total, 1),
        cutting_length_m=round(total / 1000.0, 3),
        breakdown=breakdown,
        assumptions=assumptions,
        source_references=request.source_references,
        engine_version=ENGINE_VERSION,
        is_code_provisions=is_code_provisions if request.use_is_code_rules else None,
        concrete_volume_m3=c_vol,
        concrete_grade=request.concrete_grade,
        num_bars=request.num_bars,
        bar_diameter_mm=request.bar_diameter_mm,
        tie_bar_dia_mm=tie_dia,
        tie_spacing_mm=actual_pitch,
        tie_spacing_end_mm=request.tie_spacing_end_mm,
        end_zone_length_mm=request.end_zone_length_mm,
        tie_spacing_mid_mm=request.tie_spacing_mid_mm,
        num_ties=num_ties,
        tie_cutting_length_m=tie_m,
        tie_cutting_length_mm=round(tie_cut_mm, 1),
        tie_breakdown=tie_breakdown,
        include_ties=request.include_ties,
    )
