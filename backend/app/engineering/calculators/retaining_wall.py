"""Cantilever Retaining Wall Bar Bending Schedule (BBS) calculator per IS 456:2000 & SP 34 Section 11."""

import math
from pydantic import BaseModel, Field, field_validator

from app.engineering.models import BBSCalculationResult, BBSItem, CalculationBreakdown
from app.engineering.rules.is456 import StressType, calculate_development_length
from app.engineering.rules.sp34 import calculate_bend_deduction

ENGINE_VERSION = "0.3.0"


class RetainingWallScheduleRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)  # e.g. "RW1", "RET-01"
    wall_length_m: float = Field(gt=0, default=10.0, description="Running length of retaining wall panel in meters")
    stem_height_mm: float = Field(gt=0, default=3500.0, description="Clear stem height H above base slab in mm")
    base_slab_width_mm: float = Field(gt=0, default=2400.0, description="Total base slab width B in mm")
    base_slab_thickness_mm: float = Field(gt=0, default=400.0, description="Base slab thickness D_b in mm")
    stem_base_thickness_mm: float = Field(gt=0, default=400.0, description="Stem thickness at base in mm")
    toe_projection_mm: float = Field(gt=0, default=600.0, description="Toe slab projection in mm")
    main_bar_dia_mm: float = Field(gt=0, default=16.0, description="Main stem vertical bar diameter in mm")
    main_bar_spacing_mm: float = Field(gt=0, default=150.0, description="Spacing of main vertical bars in mm")
    dist_bar_dia_mm: float = Field(gt=0, default=10.0, description="Horizontal distribution bar diameter in mm")
    dist_bar_spacing_mm: float = Field(gt=0, default=200.0, description="Spacing of horizontal distribution bars in mm")
    curtail_alternate_bars: bool = Field(default=True, description="Whether 50% of vertical bars are curtailed at H/2")
    clear_cover_mm: float = Field(ge=40.0, default=50.0, description="Nominal cover on earth-retaining face in mm")
    concrete_grade: str = Field(default="M25")
    steel_grade: str = Field(default="FE500")
    source_references: list[str] = Field(min_length=1)
    deduct_bends: bool = Field(default=True)

    @field_validator("member_id")
    @classmethod
    def normalize_member_id(cls, value: str) -> str:
        return value.strip().upper()


def calculate_retaining_wall_bbs(request: RetainingWallScheduleRequest) -> BBSCalculationResult:
    """Calculate Bar Bending Schedule for Cantilever RC Retaining Wall per IS 456 & SP 34 Section 11.

    Key Detailing Rules (SP 34 Section 11):
      - Main vertical tensile bars on earth face anchor into base slab with L-bend into heel slab (min Ld).
      - Curtailment: Alternate vertical bars curtailed at H/2 + Ld (since bending moment is cubic parabolic).
      - Minimum horizontal distribution steel = 0.12% gross area (IS 456 Cl. 26.5.2.1) placed on both faces.
      - Base slab heel top bars extend full heel length plus anchorage into stem.
      - Bend deductions per IS 2502: -2d per 90° bend.
    """
    assumptions: list[str] = []
    is_code_provisions: dict[str, str | float] = {}

    h_stem = request.stem_height_mm
    b_base = request.base_slab_width_mm
    d_base = request.base_slab_thickness_mm
    cover = request.clear_cover_mm
    main_dia = request.main_bar_dia_mm
    main_spacing = request.main_bar_spacing_mm
    dist_dia = request.dist_bar_dia_mm
    dist_spacing = request.dist_bar_spacing_mm
    wall_len_mm = request.wall_length_m * 1000.0

    # Development length in tension for earth face
    ld_res = calculate_development_length(
        bar_diameter_mm=main_dia,
        concrete_grade=request.concrete_grade,
        steel_grade=request.steel_grade,
        stress_type=StressType.TENSION,
    )
    Ld = ld_res.development_length_mm
    is_code_provisions["Development Length (Ld)"] = f"{Ld:.1f} mm ({ld_res.development_length_factor:.1f}d)"
    is_code_provisions["Stem Height"] = f"{h_stem:.0f} mm"

    assumptions.append(f"Cantilever wall: Stem height {h_stem:.0f} mm, Base slab {b_base:.0f} x {d_base:.0f} mm.")
    assumptions.append(f"Earth face rebar: T{main_dia:.0f} @ {main_spacing:.0f} mm c/c with L-anchor into heel slab.")

    items: list[BBSItem] = []

    # Total number of vertical bar locations along wall panel
    total_vert_bars = int(math.floor(wall_len_mm / main_spacing)) + 1
    heel_length_mm = b_base - request.toe_projection_mm - request.stem_base_thickness_mm
    heel_anchor_leg = min(heel_length_mm - cover, Ld)
    bend_ded_90 = calculate_bend_deduction(main_dia, 90.0).deduction_mm if request.deduct_bends else 0.0

    unit_wt_main = round((main_dia ** 2) / 162.0, 3)

    if request.curtail_alternate_bars:
        num_full = math.ceil(total_vert_bars / 2.0)
        num_curt = total_vert_bars - num_full

        # 1. Full Height Vertical Earth Face Bars
        full_cut_mm = h_stem + d_base - (2.0 * cover) + heel_anchor_leg - bend_ded_90
        full_m = round(full_cut_mm / 1000.0, 3)
        total_full_m = round(full_m * num_full, 3)

        items.append(BBSItem(
            bar_mark="Main Vertical Stem Bars (Full Height)",
            bar_type="main",
            bar_diameter_mm=main_dia,
            num_bars=num_full,
            spacing_mm=main_spacing * 2,
            cutting_length_mm=full_cut_mm,
            cutting_length_m=full_m,
            total_length_m=total_full_m,
            unit_weight_kg_m=unit_wt_main,
            total_weight_kg=round(unit_wt_main * total_full_m, 2),
            shape_description="L-shaped vertical stem bar extending full height and into heel slab",
            breakdown=[
                CalculationBreakdown(label="Stem clear height", length_mm=h_stem, clause="Drawing elevation"),
                CalculationBreakdown(label="Base slab depth embedment", length_mm=d_base - (2.0 * cover), clause="SP 34 Sec. 11"),
                CalculationBreakdown(label="Heel slab horizontal anchor leg (Ld)", length_mm=heel_anchor_leg, clause="IS 456 Cl. 26.2.1"),
                CalculationBreakdown(label="Bend deduction (1 x 90°: -2d)", length_mm=-bend_ded_90, clause="IS 2502"),
            ],
        ))

        # 2. Curtailed Vertical Earth Face Bars (curtailed at 0.5 * H + Ld)
        curt_height = min((0.5 * h_stem) + Ld, h_stem)
        curt_cut_mm = curt_height + d_base - (2.0 * cover) + heel_anchor_leg - bend_ded_90
        curt_m = round(curt_cut_mm / 1000.0, 3)
        total_curt_m = round(curt_m * num_curt, 3)

        items.append(BBSItem(
            bar_mark="Main Vertical Stem Bars (Curtailed at H/2)",
            bar_type="main",
            bar_diameter_mm=main_dia,
            num_bars=num_curt,
            spacing_mm=main_spacing * 2,
            cutting_length_mm=curt_cut_mm,
            cutting_length_m=curt_m,
            total_length_m=total_curt_m,
            unit_weight_kg_m=unit_wt_main,
            total_weight_kg=round(unit_wt_main * total_curt_m, 2),
            shape_description="Curtailed vertical rebar stopping at H/2 + Ld above base",
            breakdown=[
                CalculationBreakdown(label="Curtailed stem height (0.5H + Ld)", length_mm=curt_height, clause="SP 34 Cl. 11.2"),
                CalculationBreakdown(label="Base slab embedment", length_mm=d_base - (2.0 * cover), clause="SP 34 Sec. 11"),
                CalculationBreakdown(label="Heel slab anchor leg", length_mm=heel_anchor_leg, clause="IS 456 Cl. 26.2.1"),
                CalculationBreakdown(label="Bend deduction (1 x 90°)", length_mm=-bend_ded_90, clause="IS 2502"),
            ],
        ))
    else:
        full_cut_mm = h_stem + d_base - (2.0 * cover) + heel_anchor_leg - bend_ded_90
        full_m = round(full_cut_mm / 1000.0, 3)
        total_full_m = round(full_m * total_vert_bars, 3)
        items.append(BBSItem(
            bar_mark="Main Vertical Stem Bars (Full Height)",
            bar_type="main",
            bar_diameter_mm=main_dia,
            num_bars=total_vert_bars,
            spacing_mm=main_spacing,
            cutting_length_mm=full_cut_mm,
            cutting_length_m=full_m,
            total_length_m=total_full_m,
            unit_weight_kg_m=unit_wt_main,
            total_weight_kg=round(unit_wt_main * total_full_m, 2),
            shape_description="L-shaped vertical stem bar extending full height and into heel slab",
            breakdown=[
                CalculationBreakdown(label="Stem clear height", length_mm=h_stem, clause="Drawing elevation"),
                CalculationBreakdown(label="Heel anchor leg", length_mm=heel_anchor_leg, clause="IS 456 Cl. 26.2.1"),
                CalculationBreakdown(label="Bend deduction (1 x 90°)", length_mm=-bend_ded_90, clause="IS 2502"),
            ],
        ))

    # 3. Horizontal Distribution Bars (Both Faces of Stem)
    # 2 faces of the wall
    num_horiz_per_face = int(math.floor(h_stem / dist_spacing)) + 1
    total_horiz_bars = num_horiz_per_face * 2
    horiz_cut_mm = wall_len_mm - (2.0 * cover)
    horiz_m = round(horiz_cut_mm / 1000.0, 3)
    total_horiz_m = round(horiz_m * total_horiz_bars, 3)
    unit_wt_dist = round((dist_dia ** 2) / 162.0, 3)

    items.append(BBSItem(
        bar_mark="Horizontal Distribution Bars (Both Faces)",
        bar_type="distribution",
        bar_diameter_mm=dist_dia,
        num_bars=total_horiz_bars,
        spacing_mm=dist_spacing,
        cutting_length_mm=horiz_cut_mm,
        cutting_length_m=horiz_m,
        total_length_m=total_horiz_m,
        unit_weight_kg_m=unit_wt_dist,
        total_weight_kg=round(unit_wt_dist * total_horiz_m, 2),
        shape_description="Straight horizontal distribution rebar tied on inside and earth faces",
        breakdown=[
            CalculationBreakdown(label="Wall panel length minus end covers", length_mm=horiz_cut_mm, clause="IS 456 Cl. 26.5.2.1"),
        ],
    ))

    # 4. Base Slab Heel Top Bars
    heel_cut_mm = heel_length_mm + request.stem_base_thickness_mm + 200.0 - (2.0 * cover)
    heel_m = round(heel_cut_mm / 1000.0, 3)
    num_heel_bars = int(math.floor(wall_len_mm / main_spacing)) + 1
    total_heel_m = round(heel_m * num_heel_bars, 3)

    items.append(BBSItem(
        bar_mark="Base Slab Heel Top Reinforcement",
        bar_type="secondary",
        bar_diameter_mm=main_dia,
        num_bars=num_heel_bars,
        spacing_mm=main_spacing,
        cutting_length_mm=heel_cut_mm,
        cutting_length_m=heel_m,
        total_length_m=total_heel_m,
        unit_weight_kg_m=unit_wt_main,
        total_weight_kg=round(unit_wt_main * total_heel_m, 2),
        shape_description="Straight tensile rebar at top face of heel slab resisting cantilever moment",
        breakdown=[
            CalculationBreakdown(label="Heel cantilever projection plus stem embedment", length_mm=heel_cut_mm, clause="SP 34 Cl. 11.3"),
        ],
    ))

    total_weight = round(sum(i.total_weight_kg for i in items), 2)
    primary_cutting_m = items[0].cutting_length_m

    from app.engineering.calculators.concrete import calculate_concrete_materials, DRY_VOLUME_FACTOR
    v_base = (request.base_slab_width_mm * request.base_slab_thickness_mm * wall_len_mm) / 1e9
    v_stem = (request.stem_base_thickness_mm * request.stem_height_mm * wall_len_mm) / 1e9
    vol_m3 = round(v_base + v_stem, 4)
    mat = calculate_concrete_materials(vol_m3, request.concrete_grade)

    return BBSCalculationResult(
        member_id=request.member_id,
        member_type="RETAINING_WALL",
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
