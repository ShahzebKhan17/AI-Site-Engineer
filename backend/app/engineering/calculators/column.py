from app.engineering.models import CalculationBreakdown, ColumnBarRequest, ColumnBarResult
from app.engineering.rules.sp34 import (
    calculate_bend_deduction,
    calculate_column_lap_length,
)

ENGINE_VERSION = "0.2.0"


def calculate_longitudinal_bar(request: ColumnBarRequest) -> ColumnBarResult:
    """Calculate column longitudinal bar cutting length.

    Supports:
      1. Explicit mode (default): Uses reviewed, exact values from drawings.
      2. IS Code mode (use_is_code_rules=True): Dynamically resolves development length,
         lap length, and bend allowances per IS 456:2000 & SP 34:1987.
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
    )
