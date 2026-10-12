from app.engineering.models import CalculationBreakdown, ColumnBarRequest, ColumnBarResult

ENGINE_VERSION = "0.1.0"


def calculate_longitudinal_bar(request: ColumnBarRequest) -> ColumnBarResult:
    """Calculate from explicit, reviewed lengths only.

    Code-specific development and lap values must be resolved upstream by a
    reviewed rules module before they can be supplied to this calculator.
    """
    breakdown = [
        CalculationBreakdown(label="Storey height", length_mm=request.storey_height_mm),
        CalculationBreakdown(label="Footing embedment", length_mm=request.footing_embedment_mm),
        CalculationBreakdown(label="Top extension", length_mm=request.top_extension_mm),
        CalculationBreakdown(label="Bend allowance", length_mm=request.bend_allowance_mm),
        CalculationBreakdown(label="Lap length", length_mm=request.lap_length_mm),
    ]
    total = sum(item.length_mm for item in breakdown)
    return ColumnBarResult(
        member_id=request.member_id,
        cutting_length_mm=round(total, 1),
        cutting_length_m=round(total / 1000, 3),
        breakdown=breakdown,
        assumptions=[
            "All input dimensions were explicitly supplied and require engineer review.",
            "Lap and development values are supplied inputs; this engine version does not infer code provisions.",
        ],
        source_references=request.source_references,
        engine_version=ENGINE_VERSION,
    )
