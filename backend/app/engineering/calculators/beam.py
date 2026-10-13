"""Beam longitudinal reinforcement cutting length calculator per IS 456:2000 & SP 34:1987."""

from pydantic import BaseModel, Field, field_validator

from app.engineering.models import CalculationBreakdown
from app.engineering.rules.is456 import StressType, calculate_development_length
from app.engineering.rules.sp34 import calculate_bend_deduction

ENGINE_VERSION = "0.2.0"


class BeamBarRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)
    bar_diameter_mm: float = Field(gt=0)
    clear_span_mm: float = Field(gt=0)
    left_support_width_mm: float = Field(ge=0, default=300.0)
    right_support_width_mm: float = Field(ge=0, default=300.0)
    bar_position: str = Field(default="bottom_continuous")  # bottom_continuous, top_continuous, top_extra
    concrete_grade: str = Field(default="M25")
    steel_grade: str = Field(default="FE500")
    source_references: list[str] = Field(min_length=1)
    use_is_code_rules: bool = Field(default=True)
    deduct_bends: bool = Field(default=True)

    @field_validator("member_id")
    @classmethod
    def normalize_member_id(cls, value: str) -> str:
        return value.strip().upper()


class BeamBarResult(BaseModel):
    member_id: str
    bar_position: str
    cutting_length_mm: float
    cutting_length_m: float
    breakdown: list[CalculationBreakdown]
    assumptions: list[str]
    source_references: list[str]
    engine_version: str
    is_code_provisions: dict[str, str | float] | None = None


def calculate_beam_bar_length(request: BeamBarRequest) -> BeamBarResult:
    """Calculate beam rebar cutting length with support anchorages and bend deductions.

    Code Provisions:
      - Main bottom tension bars anchor into end support with Ld or standard 90-deg hook (IS 456 Cl. 26.2.3.3).
      - Top continuous bars anchor with development length Ld into columns.
      - Top extra bars are curtailed at 0.25 * clear_span + Ld into support (SP 34 Cl. 4.1).
      - Elongation bend deductions: -2d per 90-degree bend (SP 34 Cl. 3.2 & IS 2502).
    """
    assumptions: list[str] = []
    is_code_provisions: dict[str, str | float] = {}

    # Calculate development length in tension for anchorage
    ld_res = calculate_development_length(
        bar_diameter_mm=request.bar_diameter_mm,
        concrete_grade=request.concrete_grade,
        steel_grade=request.steel_grade,
        stress_type=StressType.TENSION,
    )
    ld_mm = ld_res.development_length_mm
    is_code_provisions["Ld_tension_mm"] = ld_mm
    is_code_provisions["Ld_factor"] = ld_res.development_length_factor

    breakdown: list[CalculationBreakdown] = []

    if request.bar_position == "top_extra":
        # Extra curtailment bar at support face
        curtailed_extent = round(0.25 * request.clear_span_mm, 1)
        anchorage_into_support = round(min(ld_mm, request.left_support_width_mm - 40.0 + 12.0 * request.bar_diameter_mm), 1)

        breakdown.append(CalculationBreakdown(label="Curtailed span projection (0.25 * L)", length_mm=curtailed_extent))
        breakdown.append(CalculationBreakdown(label="Support anchorage (Ld / hook)", length_mm=anchorage_into_support))

        if request.deduct_bends:
            ded = calculate_bend_deduction(request.bar_diameter_mm, 90.0).deduction_mm
            breakdown.append(CalculationBreakdown(label="Bend deduction (90 deg)", length_mm=-ded))

        assumptions.append("Top extra rebar curtailed at 0.25 * clear span from support face per SP 34 Cl. 4.1.")
    else:
        # Full length continuous bars (bottom or top)
        # Anchorage into left and right supports: Ld into support or support_width - cover + 90-deg leg
        anchorage_left = round(min(ld_mm, request.left_support_width_mm - 40.0 + 12.0 * request.bar_diameter_mm), 1)
        anchorage_right = round(min(ld_mm, request.right_support_width_mm - 40.0 + 12.0 * request.bar_diameter_mm), 1)

        breakdown.append(CalculationBreakdown(label="Clear span length", length_mm=request.clear_span_mm))
        breakdown.append(CalculationBreakdown(label="Left support anchorage (90 deg leg)", length_mm=anchorage_left))
        breakdown.append(CalculationBreakdown(label="Right support anchorage (90 deg leg)", length_mm=anchorage_right))

        if request.deduct_bends:
            # 2 standard 90-deg bends (one on each end support)
            ded = calculate_bend_deduction(request.bar_diameter_mm, 90.0).deduction_mm * 2.0
            breakdown.append(CalculationBreakdown(label="Bend deductions (2 x 90 deg: -4d)", length_mm=-ded))

        assumptions.append(
            f"Anchorages anchored into supporting columns with standard 90-degree hooks per IS 456 Cl. 26.2.3.3."
        )

    assumptions.append(f"Development length Ld = {ld_mm} mm ({ld_res.development_length_factor}d) per IS 456:2000 Cl. 26.2.1.")

    total_mm = round(sum(b.length_mm for b in breakdown), 1)

    return BeamBarResult(
        member_id=request.member_id,
        bar_position=request.bar_position,
        cutting_length_mm=total_mm,
        cutting_length_m=round(total_mm / 1000.0, 3),
        breakdown=breakdown,
        assumptions=assumptions,
        source_references=request.source_references,
        engine_version=ENGINE_VERSION,
        is_code_provisions=is_code_provisions,
    )
