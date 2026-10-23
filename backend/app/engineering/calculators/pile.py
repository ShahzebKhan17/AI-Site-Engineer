"""Bored / Driven Reinforced Concrete Pile Bar Bending Schedule calculator per IS 2911 & IS 456:2000."""

import math
from pydantic import BaseModel, Field, field_validator

from app.engineering.models import BBSCalculationResult, BBSItem, CalculationBreakdown
from app.engineering.rules.is456 import StressType, calculate_development_length

ENGINE_VERSION = "0.3.0"


class PileScheduleRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)  # e.g. "P1", "P-04"
    pile_diameter_mm: float = Field(gt=0, default=600.0, description="Pile shaft diameter in mm")
    pile_length_m: float = Field(gt=0, default=12.0, description="Pile shaft depth below cut-off level in meters")
    embedment_into_cap_mm: float = Field(ge=0, default=800.0, description="Dowel projection into pile cap in mm (min 50d or Ld)")
    main_bar_dia_mm: float = Field(gt=0, default=20.0, description="Longitudinal cage bar diameter in mm")
    num_main_bars: int = Field(ge=4, default=8, description="Number of vertical longitudinal bars in cage")
    spiral_bar_dia_mm: float = Field(gt=0, default=8.0, description="Helical spiral tie diameter in mm")
    spiral_pitch_mm: float = Field(gt=0, default=150.0, description="Pitch of helical spiral ties in mm")
    stiffener_bar_dia_mm: float = Field(gt=0, default=16.0, description="Circular master stiffener ring diameter in mm")
    stiffener_spacing_m: float = Field(gt=0, default=2.0, description="Spacing between master stiffener rings in meters")
    clear_cover_mm: float = Field(ge=40.0, default=50.0, description="Nominal cover to pile cage in mm (min 50mm per IS 2911)")
    concrete_grade: str = Field(default="M25")
    steel_grade: str = Field(default="FE500")
    source_references: list[str] = Field(min_length=1)

    @field_validator("member_id")
    @classmethod
    def normalize_member_id(cls, value: str) -> str:
        return value.strip().upper()


def calculate_pile_bbs(request: PileScheduleRequest) -> BBSCalculationResult:
    """Calculate Bar Bending Schedule for RC Pile Foundation per IS 2911:2010 (Part 1) and IS 456:2000.

    Key Provisions:
      - IS 2911 Part 1 Cl. 6.11: Minimum clear cover = 50 mm (cast in-situ with casing).
      - Embedment into pile cap >= Ld in tension (IS 456 Cl. 26.2.1) or minimum 50d.
      - Helical spiral link length per turn = sqrt((pi * D_cage)^2 + pitch^2).
      - IS 2911: Minimum 6 vertical bars of min 12 mm dia; spiral ties minimum 6 mm (or 8 mm for heavy piles).
      - Stiffener master rings (usually 16mm dia) placed every 1.5 to 2.0 m along cage length.
    """
    assumptions: list[str] = []
    is_code_provisions: dict[str, str | float] = {}

    d_pile = request.pile_diameter_mm
    l_pile_mm = request.pile_length_m * 1000.0
    cover = request.clear_cover_mm
    main_dia = request.main_bar_dia_mm
    num_main = request.num_main_bars

    # Calculate Ld in tension for embedment check
    ld_res = calculate_development_length(
        bar_diameter_mm=main_dia,
        concrete_grade=request.concrete_grade,
        steel_grade=request.steel_grade,
        stress_type=StressType.TENSION,
    )
    min_embedment = max(ld_res.development_length_mm, 50.0 * main_dia)
    embedment = max(request.embedment_into_cap_mm, min_embedment)

    is_code_provisions["Required Embedment (Ld)"] = f"{min_embedment:.1f} mm (Provided: {embedment:.1f} mm)"
    is_code_provisions["Minimum Cover (IS 2911)"] = f"{cover:.1f} mm"

    assumptions.append(f"Pile diameter: {d_pile:.0f} mm, Depth: {request.pile_length_m:.1f} m below cut-off level.")
    assumptions.append(f"Vertical cage: {num_main}-T{main_dia:.0f} bars. Embedment into pile cap: {embedment:.1f} mm.")

    items: list[BBSItem] = []

    # 1. Longitudinal Vertical Cage Bars
    vert_cutting_mm = l_pile_mm + embedment - cover  # Bottom cover deducted
    vert_m = round(vert_cutting_mm / 1000.0, 3)
    total_vert_m = round(vert_m * num_main, 3)
    unit_wt_main = round((main_dia ** 2) / 162.0, 3)
    total_vert_wt = round(unit_wt_main * total_vert_m, 2)

    items.append(BBSItem(
        bar_mark="Main Vertical Cage Rebar",
        bar_type="main",
        bar_diameter_mm=main_dia,
        num_bars=num_main,
        cutting_length_mm=vert_cutting_mm,
        cutting_length_m=vert_m,
        total_length_m=total_vert_m,
        unit_weight_kg_m=unit_wt_main,
        total_weight_kg=total_vert_wt,
        shape_description="Straight vertical longitudinal bar projecting into pile cap",
        breakdown=[
            CalculationBreakdown(label="Pile shaft depth", length_mm=l_pile_mm, clause="Drawing elevation"),
            CalculationBreakdown(label="Pile cap embedment (Ld)", length_mm=embedment, clause="IS 2911 Cl. 6.11 / IS 456"),
            CalculationBreakdown(label="Bottom end clear cover", length_mm=-cover, clause="IS 2911 Part 1"),
        ],
    ))

    # 2. Helical Spiral Links
    # Cage mean diameter for spiral
    d_cage = d_pile - (2.0 * cover) - request.spiral_bar_dia_mm
    pitch = request.spiral_pitch_mm
    turns = math.ceil(l_pile_mm / pitch)
    length_per_turn = math.sqrt((math.pi * d_cage) ** 2 + (pitch ** 2))
    # 2 extra full anchorage turns at top and bottom per standard detailing practice
    total_spiral_length_mm = (turns * length_per_turn) + (4.0 * math.pi * d_cage)
    spiral_m = round(total_spiral_length_mm / 1000.0, 3)
    unit_wt_spiral = round((request.spiral_bar_dia_mm ** 2) / 162.0, 3)
    total_spiral_wt = round(unit_wt_spiral * spiral_m, 2)

    items.append(BBSItem(
        bar_mark="Helical Spiral Lateral Ties",
        bar_type="spiral",
        bar_diameter_mm=request.spiral_bar_dia_mm,
        num_bars=1,
        spacing_mm=pitch,
        cutting_length_mm=total_spiral_length_mm,
        cutting_length_m=spiral_m,
        total_length_m=spiral_m,
        unit_weight_kg_m=unit_wt_spiral,
        total_weight_kg=total_spiral_wt,
        shape_description=f"Continuous helical spiral (pitch {pitch:.0f} mm) around cage core",
        breakdown=[
            CalculationBreakdown(label=f"Continuous helical pitch length ({turns} turns)", length_mm=turns * length_per_turn, clause="SP 34 Cl. 7.3"),
            CalculationBreakdown(label="End anchorage full turns (4 x pi * D_cage)", length_mm=4.0 * math.pi * d_cage, clause="IS 2911 Cl. 6.11"),
        ],
    ))

    # 3. Master Stiffener Rings
    stiff_dia = request.stiffener_bar_dia_mm
    num_stiffeners = max(int(math.floor(request.pile_length_m / request.stiffener_spacing_m)) + 1, 2)
    # Circular hoop with 24d lap
    stiff_lap = 24.0 * stiff_dia
    stiff_cutting_mm = (math.pi * d_cage) + stiff_lap
    stiff_m = round(stiff_cutting_mm / 1000.0, 3)
    total_stiff_m = round(stiff_m * num_stiffeners, 3)
    unit_wt_stiff = round((stiff_dia ** 2) / 162.0, 3)
    total_stiff_wt = round(unit_wt_stiff * total_stiff_m, 2)

    items.append(BBSItem(
        bar_mark="Master Stiffener Rings",
        bar_type="stiffener",
        bar_diameter_mm=stiff_dia,
        num_bars=num_stiffeners,
        spacing_mm=request.stiffener_spacing_m * 1000.0,
        cutting_length_mm=stiff_cutting_mm,
        cutting_length_m=stiff_m,
        total_length_m=total_stiff_m,
        unit_weight_kg_m=unit_wt_stiff,
        total_weight_kg=total_stiff_wt,
        shape_description="Circular welded internal stiffener ring maintaining cage rigidity",
        breakdown=[
            CalculationBreakdown(label="Circumferential loop (pi * D_cage)", length_mm=math.pi * d_cage, clause="IS 2911 Part 1"),
            CalculationBreakdown(label="Welded/tied lap splice (24d)", length_mm=stiff_lap, clause="SP 34 Cl. 3.4"),
        ],
    ))

    total_weight = round(sum(i.total_weight_kg for i in items), 2)
    primary_cutting_m = items[0].cutting_length_m

    from app.engineering.calculators.concrete import calculate_concrete_materials, DRY_VOLUME_FACTOR
    radius_m = (d_pile / 1000.0) / 2.0
    vol_m3 = round(math.pi * (radius_m ** 2) * request.pile_length_m, 4)
    mat = calculate_concrete_materials(vol_m3, request.concrete_grade)

    return BBSCalculationResult(
        member_id=request.member_id,
        member_type="PILE",
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
