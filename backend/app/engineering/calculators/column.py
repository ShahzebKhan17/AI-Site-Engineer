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
        # Resolve lap length if not explicitly provided
        if lap_length_mm <= 0:
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
            assumptions.append(f"Explicit lap length of {lap_length_mm} mm provided from drawing schedule.")

        # Resolve footing bend allowance if footing embedment is present but bend allowance is missing
        if bend_allowance_mm <= 0 and request.footing_embedment_mm > 0:
            # Standard 90-degree footing horizontal leg (min 300 mm or 16d)
            bend_allowance_mm = max(300.0, round(16.0 * request.bar_diameter_mm, 1))
            assumptions.append(
                f"Footing 90-deg bend leg calculated as {bend_allowance_mm} mm per SP 34 standard detailing."
            )
            is_code_provisions["footing_bend_allowance_mm"] = bend_allowance_mm

        # Calculate bend deduction if requested
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
        CalculationBreakdown(label="Footing embedment", length_mm=request.footing_embedment_mm),
        CalculationBreakdown(label="Top extension", length_mm=request.top_extension_mm),
        CalculationBreakdown(label="Bend allowance", length_mm=bend_allowance_mm),
        CalculationBreakdown(label="Lap length", length_mm=lap_length_mm),
    ]

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
    )
