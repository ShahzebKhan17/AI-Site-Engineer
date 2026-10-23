"""Bridge Pier and Foundation Pedestal Bar Bending Schedule (BBS) calculator per IS 456 & IRC:112."""

import math
from pydantic import BaseModel, Field, field_validator

from app.engineering.models import BBSCalculationResult, BBSItem, CalculationBreakdown
from app.engineering.rules.is456 import StressType, calculate_development_length
from app.engineering.rules.sp34 import calculate_bend_deduction

ENGINE_VERSION = "0.3.0"


class PierScheduleRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)  # e.g. "PR1", "PD1"
    shape: str = Field(default="rectangular")             # "rectangular" or "circular"
    dimension_1_mm: float = Field(gt=0, default=800.0, description="Width or Diameter in mm")
    dimension_2_mm: float = Field(gt=0, default=800.0, description="Depth in mm (ignored for circular)")
    height_mm: float = Field(gt=0, default=3000.0, description="Clear pier/pedestal height in mm")
    starter_embedment_mm: float = Field(ge=0, default=800.0, description="Embedment into footing / pile cap in mm")
    cap_anchorage_mm: float = Field(ge=0, default=800.0, description="Anchorage / lap into pier cap beam in mm")
    main_bar_dia_mm: float = Field(gt=0, default=25.0, description="Main vertical longitudinal bar diameter in mm")
    num_main_bars: int = Field(ge=4, default=12, description="Number of main vertical bars")
    tie_bar_dia_mm: float = Field(gt=0, default=10.0, description="Lateral tie hoop diameter in mm")
    tie_spacing_mm: float = Field(gt=0, default=150.0, description="Spacing of lateral ties in mm")
    clear_cover_mm: float = Field(ge=40.0, default=40.0, description="Nominal cover in mm")
    concrete_grade: str = Field(default="M35")
    steel_grade: str = Field(default="FE500")
    source_references: list[str] = Field(min_length=1)
    deduct_bends: bool = Field(default=True)

    @field_validator("member_id")
    @classmethod
    def normalize_member_id(cls, value: str) -> str:
        return value.strip().upper()


def calculate_pier_bbs(request: PierScheduleRequest) -> BBSCalculationResult:
    """Calculate Bar Bending Schedule for RC Bridge Piers and Building Pedestals per IS 456 & IRC:112.

    Key Provisions:
      - IS 456 Cl. 26.5.3.1: Minimum longitudinal reinforcement = 0.8% of gross cross-sectional area.
      - IS 456 Cl. 26.5.3.2: Pitch of lateral ties shall not exceed min(least lateral dimension, 16 * main_dia, 300 mm).
      - Seismic 135° hook anchorage with 10d extension per SP 34 Cl. 7.2.
      - Vertical rebar anchors into footing/pile cap with Ld and into pier cap beam with Ld.
    """
    assumptions: list[str] = []
    is_code_provisions: dict[str, str | float] = {}

    is_circular = request.shape.lower().strip() == "circular"
    b = request.dimension_1_mm
    d = request.dimension_1_mm if is_circular else request.dimension_2_mm
    h = request.height_mm
    cover = request.clear_cover_mm
    main_dia = request.main_bar_dia_mm
    num_main = request.num_main_bars

    # Development length in compression/tension
    ld_res = calculate_development_length(
        bar_diameter_mm=main_dia,
        concrete_grade=request.concrete_grade,
        steel_grade=request.steel_grade,
        stress_type=StressType.COMPRESSION,
    )
    Ld = ld_res.development_length_mm
    embedment = max(request.starter_embedment_mm, Ld)
    cap_anchor = max(request.cap_anchorage_mm, Ld)

    is_code_provisions["Development Length (Ld)"] = f"{Ld:.1f} mm ({ld_res.development_length_factor:.1f}d)"
    is_code_provisions["Footing Embedment"] = f"{embedment:.1f} mm"

    # Governing tie spacing check per IS 456 Cl. 26.5.3.2
    least_lateral = b if is_circular else min(b, d)
    max_code_pitch = min(least_lateral, 16.0 * main_dia, 300.0)
    actual_pitch = min(request.tie_spacing_mm, max_code_pitch)
    is_code_provisions["Maximum Permissible Tie Pitch"] = f"{max_code_pitch:.0f} mm (Provided: {actual_pitch:.0f} mm)"

    shape_name = f"Circular ({b:.0f} mm dia)" if is_circular else f"Rectangular ({b:.0f} x {d:.0f} mm)"
    assumptions.append(f"Pier geometry: {shape_name}, Height: {h:.0f} mm.")
    assumptions.append(f"Longitudinal steel: {num_main}-T{main_dia:.0f} bars. Foundation embedment: {embedment:.0f} mm.")

    items: list[BBSItem] = []

    # 1. Main Vertical Bars
    # Standard 90 deg footing hook leg (16d or min 300mm)
    hook_leg = max(300.0, 16.0 * main_dia)
    bend_ded_90 = calculate_bend_deduction(main_dia, 90.0).deduction_mm if request.deduct_bends else 0.0
    vert_cut_mm = h + embedment + cap_anchor + hook_leg - bend_ded_90
    vert_m = round(vert_cut_mm / 1000.0, 3)
    total_vert_m = round(vert_m * num_main, 3)
    unit_wt_main = round((main_dia ** 2) / 162.0, 3)
    total_vert_wt = round(unit_wt_main * total_vert_m, 2)

    items.append(BBSItem(
        bar_mark="Main Vertical Longitudinal Bars",
        bar_type="main",
        bar_diameter_mm=main_dia,
        num_bars=num_main,
        cutting_length_mm=vert_cut_mm,
        cutting_length_m=vert_m,
        total_length_m=total_vert_m,
        unit_weight_kg_m=unit_wt_main,
        total_weight_kg=total_vert_wt,
        shape_description="Full-height vertical rebar with 90° footing anchor hook and cap dowel lap",
        breakdown=[
            CalculationBreakdown(label="Pier clear height", length_mm=h, clause="Drawing elevation"),
            CalculationBreakdown(label="Foundation starter embedment (Ld)", length_mm=embedment, clause="IS 456 Cl. 26.2.1"),
            CalculationBreakdown(label="Cap beam anchorage / lap (Ld)", length_mm=cap_anchor, clause="IS 456 Cl. 26.2.1"),
            CalculationBreakdown(label="Bottom 90° hook leg (16d)", length_mm=hook_leg, clause="SP 34 Cl. 3.3"),
            CalculationBreakdown(label="Bend deduction (1 x 90°: -2d)", length_mm=-bend_ded_90, clause="IS 2502"),
        ],
    ))

    # 2. Lateral Ties / Hoops
    tie_dia = request.tie_bar_dia_mm
    num_ties = int(math.floor(h / actual_pitch)) + 1
    unit_wt_tie = round((tie_dia ** 2) / 162.0, 3)

    if is_circular:
        d_core = b - (2.0 * cover)
        tie_lap = max(24.0 * tie_dia, 300.0)
        tie_cut_mm = (math.pi * d_core) + tie_lap
        tie_shape = "Circular hoop tie with 24d lap splice"
        tie_breakdown = [
            CalculationBreakdown(label="Core circumference (pi * D_core)", length_mm=math.pi * d_core, clause="b - 2*cover"),
            CalculationBreakdown(label="Lap splice length (24d)", length_mm=tie_lap, clause="SP 34 Cl. 7.2"),
        ]
    else:
        w_core = b - (2.0 * cover)
        d_core = d - (2.0 * cover)
        # Seismic 135 deg hooks: 2 x 10d extensions minus bend deductions
        hook_ext = 2.0 * (10.0 * tie_dia)
        bend_ded_135 = calculate_bend_deduction(tie_dia, 135.0).deduction_mm if request.deduct_bends else 0.0
        bend_ded_90_tie = calculate_bend_deduction(tie_dia, 90.0).deduction_mm if request.deduct_bends else 0.0
        total_ded = (3.0 * bend_ded_90_tie) + (2.0 * bend_ded_135)
        tie_cut_mm = (2.0 * (w_core + d_core)) + hook_ext - total_ded
        tie_shape = "Rectangular closed tie with 135° seismic hooks (10d tails)"
        tie_breakdown = [
            CalculationBreakdown(label="Perimeter of core (2*(w+d))", length_mm=2.0 * (w_core + d_core), clause="Perimeter"),
            CalculationBreakdown(label="Seismic 135° hook extensions (2 x 10d)", length_mm=hook_ext, clause="SP 34 Cl. 7.2"),
            CalculationBreakdown(label="Bend deductions (3x90° + 2x135°)", length_mm=-total_ded, clause="IS 2502"),
        ]

    tie_m = round(tie_cut_mm / 1000.0, 3)
    total_tie_m = round(tie_m * num_ties, 3)

    items.append(BBSItem(
        bar_mark="Lateral Confining Ties / Hoops",
        bar_type="tie",
        bar_diameter_mm=tie_dia,
        num_bars=num_ties,
        spacing_mm=actual_pitch,
        cutting_length_mm=tie_cut_mm,
        cutting_length_m=tie_m,
        total_length_m=total_tie_m,
        unit_weight_kg_m=unit_wt_tie,
        total_weight_kg=round(unit_wt_tie * total_tie_m, 2),
        shape_description=tie_shape,
        breakdown=tie_breakdown,
    ))

    total_weight = round(sum(i.total_weight_kg for i in items), 2)
    primary_cutting_m = items[0].cutting_length_m

    from app.engineering.calculators.concrete import calculate_concrete_materials, DRY_VOLUME_FACTOR
    if is_circular:
        vol_m3 = round(math.pi * ((b / 2000.0) ** 2) * (h / 1000.0), 4)
    else:
        vol_m3 = round((b * d * h) / 1e9, 4)
    mat = calculate_concrete_materials(vol_m3, request.concrete_grade)

    return BBSCalculationResult(
        member_id=request.member_id,
        member_type="PIER",
        total_cutting_length_m=primary_cutting_m,
        total_weight_kg=total_weight,
        items=items,
        concrete_volume_m3=vol_m3,
        dry_volume_m3=round(vol_m3 * DRY_VOLUME_FACTOR, 4),
        cement_bags=mat.cement_bags,
        sand_m3=mat.sand_m3,
        aggregate_m3=mat.aggregate_m3,
        water_liters=mat.water_liters,
        concrete_grade=request.concrete_grade,
        assumptions=assumptions,
        source_references=request.source_references,
        is_code_provisions=is_code_provisions,
        engine_version=ENGINE_VERSION,
    )
