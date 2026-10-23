"""Slab reinforcement cutting length and Bar Bending Schedule (BBS) calculator per IS 456:2000 & SP 34:1987."""

import math
from pydantic import BaseModel, Field, field_validator

from app.engineering.models import BBSCalculationResult, BBSItem, CalculationBreakdown
from app.engineering.rules.is456 import StressType, calculate_development_length
from app.engineering.rules.sp34 import calculate_bend_deduction

ENGINE_VERSION = "0.3.0"


class SlabScheduleRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)  # e.g. "S1", "S12"
    length_ly_mm: float = Field(gt=0, description="Longer clear span Ly in mm")
    width_lx_mm: float = Field(gt=0, description="Shorter clear span Lx in mm")
    thickness_mm: float = Field(gt=0, default=150.0, description="Overall slab thickness D in mm")
    support_width_mm: float = Field(ge=0, default=230.0, description="Bearing width on beam or wall in mm")
    main_bar_dia_mm: float = Field(gt=0, default=10.0, description="Main reinforcement diameter in mm")
    main_bar_spacing_mm: float = Field(gt=0, default=150.0, description="Spacing of main bars in mm")
    dist_bar_dia_mm: float = Field(gt=0, default=8.0, description="Distribution bar diameter in mm")
    dist_bar_spacing_mm: float = Field(gt=0, default=175.0, description="Spacing of distribution bars in mm")
    clear_cover_mm: float = Field(ge=15.0, default=20.0, description="Nominal concrete cover per IS 456 Table 16")
    is_cranked: bool = Field(default=True, description="Whether alternate main bars are bent-up / cranked at 45 deg")
    concrete_grade: str = Field(default="M25")
    steel_grade: str = Field(default="FE500")
    source_references: list[str] = Field(min_length=1)
    deduct_bends: bool = Field(default=True)

    @field_validator("member_id")
    @classmethod
    def normalize_member_id(cls, value: str) -> str:
        return value.strip().upper()


def calculate_slab_bbs(request: SlabScheduleRequest) -> BBSCalculationResult:
    """Calculate Bar Bending Schedule for RC Slabs (One-Way / Two-Way) per IS 456:2000 & SP 34:1987.

    Key Provisions:
      - IS 456 Cl. 26.5.2.1: Minimum reinforcement = 0.12% gross area for Fe500 HYSD bars.
      - SP 34 Cl. 4.1: Alternate bars cranked up at 0.15 * clear_span from support face.
      - Crank depth d_eff = thickness - 2 * cover - bar_dia. Extra length = 0.42 * d_eff for 45° crank.
      - Bend deductions for 45° bends = -1d per bend (SP 34 Cl. 3.2 & IS 2502).
      - Straight bottom bars extend min Ld/3 or 100 mm into support.
    """
    assumptions: list[str] = []
    is_code_provisions: dict[str, str | float] = {}

    lx = request.width_lx_mm
    ly = request.length_ly_mm
    D = request.thickness_mm
    bearing = request.support_width_mm
    cover = request.clear_cover_mm
    main_dia = request.main_bar_dia_mm
    main_spacing = request.main_bar_spacing_mm
    dist_dia = request.dist_bar_dia_mm
    dist_spacing = request.dist_bar_spacing_mm

    aspect_ratio = round(ly / lx, 2)
    is_one_way = aspect_ratio > 2.0
    slab_type = "One-Way Slab" if is_one_way else "Two-Way Slab"

    assumptions.append(f"Slab aspect ratio Ly/Lx = {ly:.0f}/{lx:.0f} = {aspect_ratio:.2f} ({slab_type}).")
    assumptions.append(f"Concrete grade: {request.concrete_grade}, Steel grade: {request.steel_grade}, Clear cover: {cover} mm.")

    # Anchorage & Development length
    ld_res = calculate_development_length(
        bar_diameter_mm=main_dia,
        concrete_grade=request.concrete_grade,
        steel_grade=request.steel_grade,
        stress_type=StressType.TENSION,
    )
    is_code_provisions["Aspect Ratio (Ly/Lx)"] = f"{aspect_ratio:.2f} ({slab_type})"
    is_code_provisions["Development Length (Ld)"] = f"{ld_res.development_length_mm:.1f} mm ({ld_res.development_length_factor:.1f}d)"

    # Effective depth for crank
    d_eff = max(D - (2.0 * cover) - main_dia, 0.0)
    crank_additional = round(0.42 * d_eff, 1)

    # 1. Main Straight Bottom Bars along Lx
    straight_bearing = min(bearing - cover, ld_res.development_length_mm / 3.0)
    straight_cutting_lx = lx + (2.0 * straight_bearing)
    # Number of bars across Ly
    num_main_total = int(math.floor((ly - 2.0 * cover) / main_spacing)) + 1

    items: list[BBSItem] = []

    if request.is_cranked:
        num_straight = math.ceil(num_main_total / 2.0)
        num_cranked = num_main_total - num_straight

        # Straight Bottom Bars
        straight_breakdown = [
            CalculationBreakdown(label="Clear span (Lx)", length_mm=lx, clause="Drawing dimensions"),
            CalculationBreakdown(label="Left support bearing", length_mm=straight_bearing, clause="SP 34 Cl. 4.1"),
            CalculationBreakdown(label="Right support bearing", length_mm=straight_bearing, clause="SP 34 Cl. 4.1"),
        ]
        unit_wt_main = round((main_dia ** 2) / 162.0, 3)
        straight_m = round(straight_cutting_lx / 1000.0, 3)
        total_straight_m = round(straight_m * num_straight, 3)
        items.append(BBSItem(
            bar_mark="Main Straight Bottom (Lx)",
            bar_type="main",
            bar_diameter_mm=main_dia,
            num_bars=num_straight,
            spacing_mm=main_spacing * 2,
            cutting_length_mm=straight_cutting_lx,
            cutting_length_m=straight_m,
            total_length_m=total_straight_m,
            unit_weight_kg_m=unit_wt_main,
            total_weight_kg=round(unit_wt_main * total_straight_m, 2),
            shape_description="Straight bar spanning across short span with end bearings",
            breakdown=straight_breakdown,
        ))

        # Cranked Bars (Bent up at 0.15 Lx with 4 x 45° bends)
        crank_breakdown = [
            CalculationBreakdown(label="Clear span (Lx)", length_mm=lx, clause="Drawing dimensions"),
            CalculationBreakdown(label="Left support bearing", length_mm=straight_bearing, clause="SP 34 Cl. 4.1"),
            CalculationBreakdown(label="Right support bearing", length_mm=straight_bearing, clause="SP 34 Cl. 4.1"),
            CalculationBreakdown(label="Crank additions (2 x 0.42*d)", length_mm=2.0 * crank_additional, clause="SP 34 Cl. 4.1.3"),
        ]
        bend_ded_45 = calculate_bend_deduction(main_dia, 45.0).deduction_mm if request.deduct_bends else 0.0
        total_crank_ded = 4.0 * bend_ded_45
        if request.deduct_bends:
            crank_breakdown.append(CalculationBreakdown(label="Bend deductions (4 x 45°: -1d each)", length_mm=-total_crank_ded, clause="IS 2502 / SP 34"))

        crank_cutting_lx = straight_cutting_lx + (2.0 * crank_additional) - total_crank_ded
        crank_m = round(crank_cutting_lx / 1000.0, 3)
        total_crank_m = round(crank_m * num_cranked, 3)
        items.append(BBSItem(
            bar_mark="Main Cranked / Bent-up (Lx)",
            bar_type="main",
            bar_diameter_mm=main_dia,
            num_bars=num_cranked,
            spacing_mm=main_spacing * 2,
            cutting_length_mm=crank_cutting_lx,
            cutting_length_m=crank_m,
            total_length_m=total_crank_m,
            unit_weight_kg_m=unit_wt_main,
            total_weight_kg=round(unit_wt_main * total_crank_m, 2),
            shape_description="Bent-up bar at 0.15Lx with 45° cranks into top zone",
            breakdown=crank_breakdown,
        ))
    else:
        straight_m = round(straight_cutting_lx / 1000.0, 3)
        total_straight_m = round(straight_m * num_main_total, 3)
        unit_wt_main = round((main_dia ** 2) / 162.0, 3)
        items.append(BBSItem(
            bar_mark="Main Bottom Bars (Lx)",
            bar_type="main",
            bar_diameter_mm=main_dia,
            num_bars=num_main_total,
            spacing_mm=main_spacing,
            cutting_length_mm=straight_cutting_lx,
            cutting_length_m=straight_m,
            total_length_m=total_straight_m,
            unit_weight_kg_m=unit_wt_main,
            total_weight_kg=round(unit_wt_main * total_straight_m, 2),
            shape_description="Full straight bottom reinforcement across short span",
            breakdown=[
                CalculationBreakdown(label="Clear span (Lx)", length_mm=lx, clause="Drawing dimensions"),
                CalculationBreakdown(label="Support bearings", length_mm=2.0 * straight_bearing, clause="SP 34 Cl. 4.1"),
            ],
        ))

    # 2. Distribution / Secondary Bars along Ly
    dist_bearing = min(bearing - cover, ld_res.development_length_mm / 3.0)
    dist_cutting_ly = ly + (2.0 * dist_bearing)
    num_dist_bars = int(math.floor((lx - 2.0 * cover) / dist_spacing)) + 1
    unit_wt_dist = round((dist_dia ** 2) / 162.0, 3)
    dist_m = round(dist_cutting_ly / 1000.0, 3)
    total_dist_m = round(dist_m * num_dist_bars, 3)

    items.append(BBSItem(
        bar_mark="Distribution Reinforcement (Ly)",
        bar_type="distribution",
        bar_diameter_mm=dist_dia,
        num_bars=num_dist_bars,
        spacing_mm=dist_spacing,
        cutting_length_mm=dist_cutting_ly,
        cutting_length_m=dist_m,
        total_length_m=total_dist_m,
        unit_weight_kg_m=unit_wt_dist,
        total_weight_kg=round(unit_wt_dist * total_dist_m, 2),
        shape_description="Transverse distribution bars tied over main reinforcement",
        breakdown=[
            CalculationBreakdown(label="Clear span (Ly)", length_mm=ly, clause="Drawing dimensions"),
            CalculationBreakdown(label="Support bearings", length_mm=2.0 * dist_bearing, clause="IS 456 Cl. 26.5.2.1"),
        ],
    ))

    # 3. Chair Spacers for Top Steel Stability
    num_chairs = max(int(math.ceil((lx * ly) / 1_000_000.0)), 2)
    chair_dia = 10.0
    chair_height = max(D - (2.0 * cover) - (2.0 * main_dia), 50.0)
    chair_cutting = (2.0 * 150.0) + (2.0 * chair_height) + 200.0  # 2 legs + 2 heights + crown
    chair_m = round(chair_cutting / 1000.0, 3)
    unit_wt_chair = round((chair_dia ** 2) / 162.0, 3)
    total_chair_m = round(chair_m * num_chairs, 3)
    items.append(BBSItem(
        bar_mark="Top Rebar Chairs / Spacers",
        bar_type="secondary",
        bar_diameter_mm=chair_dia,
        num_bars=num_chairs,
        spacing_mm=1000.0,
        cutting_length_mm=chair_cutting,
        cutting_length_m=chair_m,
        total_length_m=total_chair_m,
        unit_weight_kg_m=unit_wt_chair,
        total_weight_kg=round(unit_wt_chair * total_chair_m, 2),
        shape_description="Four-legged spacer chair maintaining top crank elevation",
        breakdown=[
            CalculationBreakdown(label="Chair top crown", length_mm=200.0, clause="Site practice"),
            CalculationBreakdown(label="Chair vertical legs (2x)", length_mm=2.0 * chair_height, clause="D - 2*cover - 2*phi"),
            CalculationBreakdown(label="Base resting feet (2x150mm)", length_mm=300.0, clause="SP 34 Cl. 4.2"),
        ],
    ))

    total_weight = round(sum(i.total_weight_kg for i in items), 2)
    primary_cutting_m = items[0].cutting_length_m

    from app.engineering.calculators.concrete import calculate_concrete_materials, DRY_VOLUME_FACTOR
    vol_m3 = round((lx * ly * D) / 1e9, 4)
    mat = calculate_concrete_materials(vol_m3, request.concrete_grade)

    return BBSCalculationResult(
        member_id=request.member_id,
        member_type="SLAB",
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
