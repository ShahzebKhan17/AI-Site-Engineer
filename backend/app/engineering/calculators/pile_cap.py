"""Pile Cap Bar Bending Schedule (BBS) calculator per IS 2911 (Part 1) & IS 456:2000."""

import math
from pydantic import BaseModel, Field, field_validator

from app.engineering.models import BBSCalculationResult, BBSItem, CalculationBreakdown
from app.engineering.rules.is456 import StressType, calculate_development_length
from app.engineering.rules.sp34 import calculate_bend_deduction

ENGINE_VERSION = "0.3.0"


class PileCapScheduleRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)  # e.g. "PC1", "PC-02"
    length_mm: float = Field(gt=0, default=2400.0, description="Pile cap length L in mm")
    width_mm: float = Field(gt=0, default=2400.0, description="Pile cap width B in mm")
    depth_mm: float = Field(gt=0, default=1000.0, description="Pile cap overall depth D in mm")
    num_piles: int = Field(ge=1, default=4, description="Number of supporting piles under cap")
    bottom_mesh_dia_mm: float = Field(gt=0, default=20.0, description="Main bottom tension rebar diameter in mm")
    bottom_mesh_spacing_mm: float = Field(gt=0, default=150.0, description="Spacing of bottom mesh bars in mm")
    has_top_mesh: bool = Field(default=True, description="Whether top nominal reinforcement mesh is provided")
    top_mesh_dia_mm: float = Field(gt=0, default=12.0, description="Top mesh rebar diameter in mm")
    top_mesh_spacing_mm: float = Field(gt=0, default=200.0, description="Top mesh spacing in mm")
    num_starter_bars: int = Field(ge=0, default=8, description="Number of column/pier starter dowel bars")
    starter_bar_dia_mm: float = Field(gt=0, default=20.0, description="Starter dowel bar diameter in mm")
    clear_cover_mm: float = Field(ge=40.0, default=50.0, description="Nominal cover per IS 456 / IS 2911")
    concrete_grade: str = Field(default="M25")
    steel_grade: str = Field(default="FE500")
    source_references: list[str] = Field(min_length=1)
    deduct_bends: bool = Field(default=True)

    @field_validator("member_id")
    @classmethod
    def normalize_member_id(cls, value: str) -> str:
        return value.strip().upper()


def calculate_pile_cap_bbs(request: PileCapScheduleRequest) -> BBSCalculationResult:
    """Calculate Bar Bending Schedule for RC Pile Cap per IS 2911:2010 and IS 456:2000.

    Key Provisions:
      - IS 456 Cl. 34.3 & IS 2911: Tensile reinforcement hooked upwards at ends by min D - 2*cover (max 450 mm).
      - IS 456 Cl. 26.5.1.3: Side face / skin reinforcement required when overall depth exceeds 750 mm (0.1% web area).
      - Starter dowels anchor into pile cap with horizontal L-leg (min 300 mm or 16d) and project upwards by Ld.
      - Bend deductions per IS 2502 / SP 34: -2d per 90-degree bend.
    """
    assumptions: list[str] = []
    is_code_provisions: dict[str, str | float] = {}

    L = request.length_mm
    B = request.width_mm
    D = request.depth_mm
    cover = request.clear_cover_mm
    bar_dia = request.bottom_mesh_dia_mm
    spacing = request.bottom_mesh_spacing_mm

    # Development length calculation
    ld_res = calculate_development_length(
        bar_diameter_mm=bar_dia,
        concrete_grade=request.concrete_grade,
        steel_grade=request.steel_grade,
        stress_type=StressType.TENSION,
    )
    is_code_provisions["Development Length (Ld)"] = f"{ld_res.development_length_mm:.1f} mm ({ld_res.development_length_factor:.1f}d)"
    is_code_provisions["Clear Cover"] = f"{cover:.1f} mm"

    assumptions.append(f"Pile cap dimensions: {L:.0f} x {B:.0f} x {D:.0f} mm ({request.num_piles} piles).")
    assumptions.append(f"Bottom tension mesh: T{bar_dia:.0f} @ {spacing:.0f} mm c/c both ways.")

    items: list[BBSItem] = []

    # Upward vertical leg at ends
    vert_leg = min(D - (2.0 * cover), 450.0)
    bend_ded_90 = calculate_bend_deduction(bar_dia, 90.0).deduction_mm if request.deduct_bends else 0.0

    # 1. Bottom Main Tension Bars along Length (L)
    straight_L = L - (2.0 * cover)
    bottom_cut_L = straight_L + (2.0 * vert_leg) - (2.0 * bend_ded_90)
    num_bars_L = int(math.floor((B - 2.0 * cover) / spacing)) + 1
    unit_wt_bot = round((bar_dia ** 2) / 162.0, 3)
    cut_L_m = round(bottom_cut_L / 1000.0, 3)
    total_L_m = round(cut_L_m * num_bars_L, 3)

    items.append(BBSItem(
        bar_mark="Bottom Mesh (X-Direction)",
        bar_type="main",
        bar_diameter_mm=bar_dia,
        num_bars=num_bars_L,
        spacing_mm=spacing,
        cutting_length_mm=bottom_cut_L,
        cutting_length_m=cut_L_m,
        total_length_m=total_L_m,
        unit_weight_kg_m=unit_wt_bot,
        total_weight_kg=round(unit_wt_bot * total_L_m, 2),
        shape_description="U-shaped bottom bar with vertical end legs turned upward",
        breakdown=[
            CalculationBreakdown(label="Straight bottom length", length_mm=straight_L, clause="L - 2*cover"),
            CalculationBreakdown(label="Vertical upward legs (2x)", length_mm=2.0 * vert_leg, clause="IS 456 Cl. 34.3"),
            CalculationBreakdown(label="Bend deductions (2 x 90°: -2d)", length_mm=-2.0 * bend_ded_90, clause="IS 2502 / SP 34"),
        ],
    ))

    # 2. Bottom Main Tension Bars along Width (B)
    straight_B = B - (2.0 * cover)
    bottom_cut_B = straight_B + (2.0 * vert_leg) - (2.0 * bend_ded_90)
    num_bars_B = int(math.floor((L - 2.0 * cover) / spacing)) + 1
    cut_B_m = round(bottom_cut_B / 1000.0, 3)
    total_B_m = round(cut_B_m * num_bars_B, 3)

    items.append(BBSItem(
        bar_mark="Bottom Mesh (Y-Direction)",
        bar_type="main",
        bar_diameter_mm=bar_dia,
        num_bars=num_bars_B,
        spacing_mm=spacing,
        cutting_length_mm=bottom_cut_B,
        cutting_length_m=cut_B_m,
        total_length_m=total_B_m,
        unit_weight_kg_m=unit_wt_bot,
        total_weight_kg=round(unit_wt_bot * total_B_m, 2),
        shape_description="U-shaped bottom bar with vertical end legs turned upward",
        breakdown=[
            CalculationBreakdown(label="Straight bottom length", length_mm=straight_B, clause="B - 2*cover"),
            CalculationBreakdown(label="Vertical upward legs (2x)", length_mm=2.0 * vert_leg, clause="IS 456 Cl. 34.3"),
            CalculationBreakdown(label="Bend deductions (2 x 90°: -2d)", length_mm=-2.0 * bend_ded_90, clause="IS 2502 / SP 34"),
        ],
    ))

    # 3. Top Nominal Mesh (if specified or deep cap)
    if request.has_top_mesh:
        top_dia = request.top_mesh_dia_mm
        top_spacing = request.top_mesh_spacing_mm
        top_cut_L = straight_L
        top_cut_B = straight_B
        num_top_L = int(math.floor((B - 2.0 * cover) / top_spacing)) + 1
        num_top_B = int(math.floor((L - 2.0 * cover) / top_spacing)) + 1
        unit_wt_top = round((top_dia ** 2) / 162.0, 3)

        top_L_m = round(top_cut_L / 1000.0, 3)
        top_B_m = round(top_cut_B / 1000.0, 3)
        total_top_m = round((top_L_m * num_top_L) + (top_B_m * num_top_B), 3)

        items.append(BBSItem(
            bar_mark="Top Nominal Mesh (X & Y)",
            bar_type="secondary",
            bar_diameter_mm=top_dia,
            num_bars=num_top_L + num_top_B,
            spacing_mm=top_spacing,
            cutting_length_mm=top_cut_L,
            cutting_length_m=top_L_m,
            total_length_m=total_top_m,
            unit_weight_kg_m=unit_wt_top,
            total_weight_kg=round(unit_wt_top * total_top_m, 2),
            shape_description="Straight grid bars tied at top face to resist thermal / shrinkage stresses",
            breakdown=[
                CalculationBreakdown(label="Straight length across cap", length_mm=straight_L, clause="IS 456 Cl. 34.4"),
            ],
        ))

    # 4. Column / Pier Starter Dowel Bars
    if request.num_starter_bars > 0:
        s_dia = request.starter_bar_dia_mm
        s_ld_res = calculate_development_length(
            bar_diameter_mm=s_dia,
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            stress_type=StressType.COMPRESSION,
        )
        s_vert = max(D - cover - 50.0, s_ld_res.development_length_mm)
        s_horiz = max(300.0, 16.0 * s_dia)  # 90 deg horizontal anchor leg
        s_bend_ded = calculate_bend_deduction(s_dia, 90.0).deduction_mm if request.deduct_bends else 0.0
        s_cut_mm = s_vert + s_horiz - s_bend_ded
        s_cut_m = round(s_cut_mm / 1000.0, 3)
        total_s_m = round(s_cut_m * request.num_starter_bars, 3)
        unit_wt_s = round((s_dia ** 2) / 162.0, 3)

        items.append(BBSItem(
            bar_mark="Column Starter Dowels",
            bar_type="main",
            bar_diameter_mm=s_dia,
            num_bars=request.num_starter_bars,
            cutting_length_mm=s_cut_mm,
            cutting_length_m=s_cut_m,
            total_length_m=total_s_m,
            unit_weight_kg_m=unit_wt_s,
            total_weight_kg=round(unit_wt_s * total_s_m, 2),
            shape_description="L-shaped starter dowel anchored into cap bottom with lap projection",
            breakdown=[
                CalculationBreakdown(label="Vertical dowel embedment & lap", length_mm=s_vert, clause="IS 456 Cl. 26.2.1"),
                CalculationBreakdown(label="Horizontal footing hook leg (16d)", length_mm=s_horiz, clause="SP 34 Cl. 3.3"),
                CalculationBreakdown(label="Bend deduction (1 x 90°: -2d)", length_mm=-s_bend_ded, clause="IS 2502"),
            ],
        ))

    total_weight = round(sum(i.total_weight_kg for i in items), 2)
    primary_cutting_m = items[0].cutting_length_m

    return BBSCalculationResult(
        member_id=request.member_id,
        member_type="PILE_CAP",
        total_cutting_length_m=primary_cutting_m,
        total_weight_kg=total_weight,
        items=items,
        assumptions=assumptions,
        source_references=request.source_references,
        is_code_provisions=is_code_provisions,
        engine_version=ENGINE_VERSION,
    )
