"""Staircase Bar Bending Schedule (BBS) calculator per IS 456:2000 Cl. 33 & SP 34:1987 Section 10."""

import math
from pydantic import BaseModel, Field, field_validator

from app.engineering.models import BBSCalculationResult, BBSItem, CalculationBreakdown
from app.engineering.rules.is456 import StressType, calculate_development_length
from app.engineering.rules.sp34 import calculate_bend_deduction

ENGINE_VERSION = "0.3.0"


class StaircaseScheduleRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)  # e.g. "ST1", "SC1"
    flight_width_mm: float = Field(gt=0, default=1200.0, description="Stair width / flight width in mm")
    waist_slab_thickness_mm: float = Field(gt=0, default=150.0, description="Thickness of inclined waist slab in mm")
    riser_mm: float = Field(gt=0, default=150.0, description="Step riser height in mm")
    tread_mm: float = Field(gt=0, default=250.0, description="Step tread going in mm")
    num_risers: int = Field(ge=2, default=10, description="Total number of risers in flight")
    num_treads: int = Field(ge=1, default=9, description="Total number of treads in flight")
    bottom_landing_length_mm: float = Field(ge=0, default=1200.0, description="Bottom landing length in mm")
    top_landing_length_mm: float = Field(ge=0, default=1200.0, description="Top landing length in mm")
    main_bar_dia_mm: float = Field(gt=0, default=12.0, description="Main tensile waist rebar diameter in mm")
    main_bar_spacing_mm: float = Field(gt=0, default=150.0, description="Spacing of main tensile waist bars in mm")
    dist_bar_dia_mm: float = Field(gt=0, default=8.0, description="Distribution bar diameter in mm")
    dist_bar_spacing_mm: float = Field(gt=0, default=175.0, description="Spacing of distribution bars in mm")
    clear_cover_mm: float = Field(ge=15.0, default=20.0, description="Nominal cover in mm")
    concrete_grade: str = Field(default="M25")
    steel_grade: str = Field(default="FE500")
    source_references: list[str] = Field(min_length=1)
    deduct_bends: bool = Field(default=True)

    @field_validator("member_id")
    @classmethod
    def normalize_member_id(cls, value: str) -> str:
        return value.strip().upper()


def calculate_staircase_bbs(request: StaircaseScheduleRequest) -> BBSCalculationResult:
    """Calculate Bar Bending Schedule for RC Staircase Flights per IS 456 Cl. 33 and SP 34 Section 10.

    Key Detailing Rules (SP 34 Section 10):
      - Waist flight inclined length L_flight = sqrt((num_treads * tread)^2 + (num_risers * riser)^2).
      - Re-entrant Corner Rule: Main bottom steel at waist-landing junction must NEVER turn around an inside corner.
        It must continue straight to the opposite face and anchor with development length Ld.
      - Top negative steel at waist-landing junction anchors Ld into landing and 0.3 * L_flight into waist slab.
      - Transverse distribution bars provided throughout flight waist and landings (IS 456 Cl. 26.5.2.1).
    """
    assumptions: list[str] = []
    is_code_provisions: dict[str, str | float] = {}

    R = request.riser_mm
    T = request.tread_mm
    num_r = request.num_risers
    num_t = request.num_treads
    total_going_mm = num_t * T
    total_rise_mm = num_r * R
    inclined_flight_mm = math.sqrt(total_going_mm ** 2 + total_rise_mm ** 2)

    cover = request.clear_cover_mm
    main_dia = request.main_bar_dia_mm
    main_spacing = request.main_bar_spacing_mm
    dist_dia = request.dist_bar_dia_mm
    dist_spacing = request.dist_bar_spacing_mm
    width = request.flight_width_mm

    # Development length for landing anchorage
    ld_res = calculate_development_length(
        bar_diameter_mm=main_dia,
        concrete_grade=request.concrete_grade,
        steel_grade=request.steel_grade,
        stress_type=StressType.TENSION,
    )
    Ld = ld_res.development_length_mm
    is_code_provisions["Inclined Flight Length"] = f"{inclined_flight_mm:.1f} mm"
    is_code_provisions["Development Length (Ld)"] = f"{Ld:.1f} mm ({ld_res.development_length_factor:.1f}d)"

    assumptions.append(f"Flight geometry: {num_r} risers @ {R:.0f} mm, {num_t} treads @ {T:.0f} mm. Inclined length: {inclined_flight_mm:.1f} mm.")
    assumptions.append(f"SP 34 Section 10 re-entrant junction rule enforced (bars cross and anchor Ld into compression face).")

    items: list[BBSItem] = []

    # Number of main bars across flight width
    num_main_bars = int(math.floor((width - 2.0 * cover) / main_spacing)) + 1
    unit_wt_main = round((main_dia ** 2) / 162.0, 3)

    # 1. Main Bottom Waist Bar (anchored Ld into both bottom and top landings)
    bottom_anchorage = min(request.bottom_landing_length_mm - cover, Ld)
    top_anchorage = min(request.top_landing_length_mm - cover, Ld)
    bend_ded = calculate_bend_deduction(main_dia, 45.0).deduction_mm if request.deduct_bends else 0.0

    main_bottom_cutting_mm = inclined_flight_mm + bottom_anchorage + top_anchorage - (2.0 * bend_ded)
    main_bot_m = round(main_bottom_cutting_mm / 1000.0, 3)
    total_main_bot_m = round(main_bot_m * num_main_bars, 3)

    items.append(BBSItem(
        bar_mark="Main Waist Tensile Rebar",
        bar_type="main",
        bar_diameter_mm=main_dia,
        num_bars=num_main_bars,
        spacing_mm=main_spacing,
        cutting_length_mm=main_bottom_cutting_mm,
        cutting_length_m=main_bot_m,
        total_length_m=total_main_bot_m,
        unit_weight_kg_m=unit_wt_main,
        total_weight_kg=round(unit_wt_main * total_main_bot_m, 2),
        shape_description="Inclined waist bottom bar continuing with Ld development into both landing slabs",
        breakdown=[
            CalculationBreakdown(label="Inclined flight waist length", length_mm=inclined_flight_mm, clause="sqrt(G^2 + H^2)"),
            CalculationBreakdown(label="Bottom landing anchorage (Ld)", length_mm=bottom_anchorage, clause="SP 34 Sec. 10"),
            CalculationBreakdown(label="Top landing anchorage (Ld)", length_mm=top_anchorage, clause="SP 34 Sec. 10"),
            CalculationBreakdown(label="Junction bend deductions (2 x 45°: -1d)", length_mm=-2.0 * bend_ded, clause="IS 2502"),
        ],
    ))

    # 2. Top Extra / Negative Junction Bars at Waist-Landing Interface
    junction_top_waist_mm = 0.3 * inclined_flight_mm
    junction_top_landing_mm = Ld
    junction_cut_mm = junction_top_waist_mm + junction_top_landing_mm - bend_ded
    junc_m = round(junction_cut_mm / 1000.0, 3)
    # 2 junctions (top landing and bottom landing)
    num_junction_bars = num_main_bars * 2
    total_junc_m = round(junc_m * num_junction_bars, 3)

    items.append(BBSItem(
        bar_mark="Top Negative Junction Extra Bars",
        bar_type="top_extra",
        bar_diameter_mm=main_dia,
        num_bars=num_junction_bars,
        spacing_mm=main_spacing,
        cutting_length_mm=junction_cut_mm,
        cutting_length_m=junc_m,
        total_length_m=total_junc_m,
        unit_weight_kg_m=unit_wt_main,
        total_weight_kg=round(unit_wt_main * total_junc_m, 2),
        shape_description="Negative moment hogging bar at waist-landing junction (0.3L_flight + Ld)",
        breakdown=[
            CalculationBreakdown(label="Waist slab extension (0.3 * L_flight)", length_mm=junction_top_waist_mm, clause="SP 34 Cl. 10.3"),
            CalculationBreakdown(label="Landing anchorage embedment (Ld)", length_mm=junction_top_landing_mm, clause="IS 456 Cl. 26.2.1"),
            CalculationBreakdown(label="Bend deduction (1 x 45°)", length_mm=-bend_ded, clause="IS 2502"),
        ],
    ))

    # 3. Transverse Distribution Bars (across waist flight and landings)
    dist_cut_mm = width - (2.0 * cover)
    dist_m = round(dist_cut_mm / 1000.0, 3)
    num_dist_flight = int(math.floor(inclined_flight_mm / dist_spacing)) + 1
    num_dist_bot_land = int(math.floor(request.bottom_landing_length_mm / dist_spacing)) + 1
    num_dist_top_land = int(math.floor(request.top_landing_length_mm / dist_spacing)) + 1
    total_dist_bars = num_dist_flight + num_dist_bot_land + num_dist_top_land
    total_dist_m = round(dist_m * total_dist_bars, 3)
    unit_wt_dist = round((dist_dia ** 2) / 162.0, 3)

    items.append(BBSItem(
        bar_mark="Transverse Distribution Reinforcement",
        bar_type="distribution",
        bar_diameter_mm=dist_dia,
        num_bars=total_dist_bars,
        spacing_mm=dist_spacing,
        cutting_length_mm=dist_cut_mm,
        cutting_length_m=dist_m,
        total_length_m=total_dist_m,
        unit_weight_kg_m=unit_wt_dist,
        total_weight_kg=round(unit_wt_dist * total_dist_m, 2),
        shape_description="Straight transverse distribution bars across stair width",
        breakdown=[
            CalculationBreakdown(label="Flight width minus side covers", length_mm=dist_cut_mm, clause="IS 456 Cl. 26.5.2.1"),
        ],
    ))

    total_weight = round(sum(i.total_weight_kg for i in items), 2)
    primary_cutting_m = items[0].cutting_length_m

    from app.engineering.calculators.concrete import calculate_concrete_materials, DRY_VOLUME_FACTOR
    v_waist = (inclined_flight_mm * width * request.waist_slab_thickness_mm) / 1e9
    v_steps = (num_t * 0.5 * R * T * width) / 1e9
    v_landings = ((request.bottom_landing_length_mm + request.top_landing_length_mm) * width * request.waist_slab_thickness_mm) / 1e9
    vol_m3 = round(v_waist + v_steps + v_landings, 4)
    mat = calculate_concrete_materials(vol_m3, request.concrete_grade)

    return BBSCalculationResult(
        member_id=request.member_id,
        member_type="STAIRCASE",
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
