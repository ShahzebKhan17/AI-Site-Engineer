"""Beam reinforcement cutting length & schedule calculator per IS 456:2000 & SP 34:1987."""

import math
from pydantic import BaseModel, Field, field_validator

from app.engineering.models import BBSCalculationResult, BBSItem, CalculationBreakdown
from app.engineering.rules.is456 import StressType, calculate_development_length
from app.engineering.rules.sp34 import calculate_bend_deduction

ENGINE_VERSION = "0.2.0"


class BeamBarRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)
    bar_diameter_mm: float = Field(gt=0)
    clear_span_mm: float = Field(gt=0)
    left_support_width_mm: float = Field(ge=0, default=300.0)
    right_support_width_mm: float = Field(ge=0, default=300.0)
    beam_width_mm: float | None = Field(default=None, description="Beam web width in mm")
    beam_depth_mm: float | None = Field(default=None, description="Beam total depth in mm")
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


class BeamScheduleRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)
    clear_span_mm: float = Field(gt=0, description="Clear span between support faces in mm")
    beam_width_mm: float = Field(default=230.0, gt=0, description="Beam cross-section width in mm")
    beam_depth_mm: float = Field(default=450.0, gt=0, description="Beam overall depth in mm")
    left_support_width_mm: float = Field(default=300.0, ge=0, description="Width of left supporting column in mm")
    right_support_width_mm: float = Field(default=300.0, ge=0, description="Width of right supporting column in mm")
    clear_cover_mm: float = Field(default=25.0, ge=0, description="Nominal clear cover in mm per IS 456 Cl. 26.4.2.1")

    # Bottom longitudinal reinforcement (tension bars)
    bottom_bars_count: int = Field(default=3, ge=1, description="Number of bottom continuous longitudinal tension bars")
    bottom_bar_dia_mm: float = Field(default=16.0, gt=0, description="Diameter of bottom longitudinal tension bars in mm")

    # Top longitudinal reinforcement (hanger / anchor bars)
    top_bars_count: int = Field(default=2, ge=0, description="Number of top continuous hanger/compression bars")
    top_bar_dia_mm: float = Field(default=12.0, gt=0, description="Diameter of top longitudinal bars in mm")

    # Transverse shear reinforcement (stirrups / links)
    stirrup_dia_mm: float = Field(default=8.0, gt=0, description="Diameter of shear stirrups in mm")
    stirrup_spacing_mm: float = Field(default=150.0, gt=0, description="Center-to-center spacing of stirrups in mm")
    stirrup_legs: int = Field(default=2, ge=1, description="Number of vertical stirrup legs")

    concrete_grade: str = Field(default="M25")
    steel_grade: str = Field(default="FE500")
    source_references: list[str] = Field(default_factory=lambda: ["Drawing Specifications"])
    deduct_bends: bool = Field(default=True)
    use_is_code_rules: bool = Field(default=True)

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
    concrete_volume_m3: float = 0.0
    concrete_grade: str = "M25"

    def to_bbs_result(
        self,
        bar_diameter_mm: float = 16.0,
        num_bars: int = 3,
        beam_width_mm: float | None = None,
        beam_depth_mm: float | None = None,
        clear_span_mm: float | None = None,
        stirrup_dia_mm: float = 8.0,
        stirrup_spacing_mm: float = 150.0,
        clear_cover_mm: float = 25.0,
    ) -> BBSCalculationResult:
        from app.engineering.calculators.concrete import calculate_concrete_materials, DRY_VOLUME_FACTOR

        unit_wt = round((bar_diameter_mm ** 2) / 162.0, 3)
        total_len = round(self.cutting_length_m * num_bars, 3)
        total_wt = round(unit_wt * total_len, 2)

        main_item = BBSItem(
            bar_mark=f"Beam {self.bar_position.replace('_', ' ').title()}",
            bar_type="main",
            bar_diameter_mm=bar_diameter_mm,
            num_bars=num_bars,
            cutting_length_mm=self.cutting_length_mm,
            cutting_length_m=self.cutting_length_m,
            total_length_m=total_len,
            unit_weight_kg_m=unit_wt,
            total_weight_kg=total_wt,
            shape_description=f"Beam {self.bar_position.replace('_', ' ')} bars anchored into column core with 90° hooks",
            breakdown=self.breakdown,
        )
        items = [main_item]

        # If beam cross-section and span are available, also synthesize stirrups
        w = beam_width_mm or 230.0
        d = beam_depth_mm or 450.0
        span = clear_span_mm or (self.cutting_length_mm - 840.0 if self.cutting_length_mm > 1000 else 4000.0)

        if w > 0 and d > 0 and span > 0:
            core_w = max(50.0, w - (2.0 * clear_cover_mm))
            core_d = max(50.0, d - (2.0 * clear_cover_mm))
            perim = 2.0 * (core_w + core_d)
            hook_ext = 2.0 * (10.0 * stirrup_dia_mm)  # 2 x 135 deg seismic hooks per IS 456 Cl 26.2.2.4
            bend_ded_90 = calculate_bend_deduction(stirrup_dia_mm, 90.0).deduction_mm
            bend_ded_135 = calculate_bend_deduction(stirrup_dia_mm, 135.0).deduction_mm
            total_ded = (3.0 * bend_ded_90) + (2.0 * bend_ded_135)
            stirrup_cut_mm = round(perim + hook_ext - total_ded, 1)
            stirrup_cut_m = round(stirrup_cut_mm / 1000.0, 3)

            n_stirrups = int(math.floor(span / stirrup_spacing_mm)) + 1 if stirrup_spacing_mm > 0 else 0
            s_unit_wt = round((stirrup_dia_mm ** 2) / 162.0, 3)
            s_total_len = round(stirrup_cut_m * n_stirrups, 3)
            s_total_wt = round(s_unit_wt * s_total_len, 2)

            stirrup_breakdown = [
                CalculationBreakdown(label=f"Core width (2 x {core_w:.0f} mm)", length_mm=2.0 * core_w, clause="IS 456 Cl. 26.4.2.1"),
                CalculationBreakdown(label=f"Core depth (2 x {core_d:.0f} mm)", length_mm=2.0 * core_d, clause="IS 456 Cl. 26.4.2.1"),
                CalculationBreakdown(label=f"Two 135° seismic hooks (2 x 10d = {hook_ext:.0f} mm)", length_mm=hook_ext, clause="IS 456 Cl. 26.2.2.4"),
                CalculationBreakdown(label="Bend deductions (3x 90° + 2x 135° bends)", length_mm=-total_ded, clause="SP 34 Cl. 3.2"),
            ]

            stirrup_item = BBSItem(
                bar_mark="Shear Stirrups / Links",
                bar_type="tie",
                bar_diameter_mm=stirrup_dia_mm,
                num_bars=n_stirrups,
                spacing_mm=stirrup_spacing_mm,
                cutting_length_mm=stirrup_cut_mm,
                cutting_length_m=stirrup_cut_m,
                total_length_m=s_total_len,
                unit_weight_kg_m=s_unit_wt,
                total_weight_kg=s_total_wt,
                shape_description=f"2-legged closed rectangular stirrup ({core_w:.0f}x{core_d:.0f} mm) with 135° seismic hooks @ {stirrup_spacing_mm:.0f} mm c/c",
                breakdown=stirrup_breakdown,
            )
            items.append(stirrup_item)
            total_wt = round(total_wt + s_total_wt, 2)

        c_grade = getattr(self, "concrete_grade", "M25")
        vol_m3 = getattr(self, "concrete_volume_m3", 0.0)
        if vol_m3 <= 0 and w > 0 and d > 0 and span > 0:
            vol_m3 = round((w * d * span) / 1e9, 4)

        if vol_m3 > 0:
            mat = calculate_concrete_materials(vol_m3, c_grade)
            c_bags, s_m3, a_m3, w_l = mat.cement_bags, mat.sand_m3, mat.aggregate_m3, mat.water_liters
            dry_v = round(vol_m3 * DRY_VOLUME_FACTOR, 4)
        else:
            c_bags, s_m3, a_m3, w_l, dry_v = None, None, None, None, None

        return BBSCalculationResult(
            member_id=self.member_id,
            member_type="BEAM",
            total_cutting_length_m=self.cutting_length_m,
            total_cutting_length_mm=self.cutting_length_mm,
            total_weight_kg=total_wt,
            items=items,
            concrete_volume_m3=vol_m3 if vol_m3 > 0 else None,
            dry_volume_m3=dry_v,
            cement_bags=c_bags,
            sand_m3=s_m3,
            aggregate_m3=a_m3,
            water_liters=w_l,
            concrete_grade=c_grade if vol_m3 > 0 else None,
            assumptions=self.assumptions,
            source_references=self.source_references,
            is_code_provisions=self.is_code_provisions,
            engine_version=self.engine_version,
        )


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

    # Column support cover = 40 mm, 90-degree bend vertical leg = 12 * d
    cover_col = 40.0
    hook_leg = 12.0 * request.bar_diameter_mm

    if request.bar_position == "top_extra":
        # Extra curtailment bar at support face
        curtailed_extent = round(0.25 * request.clear_span_mm, 1)
        straight_embed_left = max(0.0, request.left_support_width_mm - cover_col)
        anchorage_into_support = round(min(ld_mm, straight_embed_left + hook_leg), 1)

        breakdown.append(CalculationBreakdown(label="Curtailed span projection (0.25 * L)", length_mm=curtailed_extent, clause="SP 34 Cl. 4.1"))
        breakdown.append(
            CalculationBreakdown(
                label=f"Support anchorage (90° hook: [{request.left_support_width_mm:.0f} - {cover_col:.0f} col cover] + 12d leg [{hook_leg:.0f} mm])",
                length_mm=anchorage_into_support,
                clause="IS 456 Cl. 26.2.3.3",
            )
        )

        if request.deduct_bends:
            ded = calculate_bend_deduction(request.bar_diameter_mm, 90.0).deduction_mm
            breakdown.append(CalculationBreakdown(label="Bend deduction (90 deg: -2d)", length_mm=-ded, clause="SP 34 Cl. 3.2"))

        assumptions.append("Top extra rebar curtailed at 0.25 * clear span from support face per SP 34 Cl. 4.1.")
    else:
        # Full length continuous bars (bottom or top)
        straight_embed_left = max(0.0, request.left_support_width_mm - cover_col)
        straight_embed_right = max(0.0, request.right_support_width_mm - cover_col)
        anchorage_left = round(min(ld_mm, straight_embed_left + hook_leg), 1)
        anchorage_right = round(min(ld_mm, straight_embed_right + hook_leg), 1)

        breakdown.append(CalculationBreakdown(label="Clear span length", length_mm=request.clear_span_mm, clause="Drawing Detail"))
        breakdown.append(
            CalculationBreakdown(
                label=f"Left support anchorage (90° hook: [{request.left_support_width_mm:.0f} - {cover_col:.0f} col cover] + 12d leg [{hook_leg:.0f} mm])",
                length_mm=anchorage_left,
                clause="IS 456 Cl. 26.2.3.3",
            )
        )
        breakdown.append(
            CalculationBreakdown(
                label=f"Right support anchorage (90° hook: [{request.right_support_width_mm:.0f} - {cover_col:.0f} col cover] + 12d leg [{hook_leg:.0f} mm])",
                length_mm=anchorage_right,
                clause="IS 456 Cl. 26.2.3.3",
            )
        )

        if request.deduct_bends:
            ded = calculate_bend_deduction(request.bar_diameter_mm, 90.0).deduction_mm * 2.0
            breakdown.append(CalculationBreakdown(label="Bend deductions (2 x 90 deg: -4d)", length_mm=-ded, clause="SP 34 Cl. 3.2"))

        assumptions.append(
            f"Support anchorage = (Supporting column width {request.left_support_width_mm:.0f} mm - 40 mm end cover) + (12 * bar_dia {request.bar_diameter_mm:.0f} mm vertical bend leg) = {straight_embed_left:.0f} + {hook_leg:.0f} = {anchorage_left:.1f} mm per IS 456 Cl. 26.2.3.3."
        )

    assumptions.append(f"Development length Ld = {ld_mm} mm ({ld_res.development_length_factor}d) per IS 456:2000 Cl. 26.2.1.")

    total_mm = round(sum(b.length_mm for b in breakdown), 1)
    tot_span = request.clear_span_mm
    vol_m3 = round((request.beam_width_mm * request.beam_depth_mm * tot_span) / 1e9, 4) if (request.beam_width_mm and request.beam_depth_mm) else 0.0

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
        concrete_volume_m3=vol_m3,
        concrete_grade=request.concrete_grade,
    )


def calculate_beam_bbs(request: BeamScheduleRequest) -> BBSCalculationResult:
    """Calculate complete deterministic Bar Bending Schedule (BBS) for an RCC Beam per IS 456:2000 & SP 34:1987.

    Produces:
      - Item 1: Bottom longitudinal tension bars (with 90° hooks into column support core)
      - Item 2: Top longitudinal hanger bars (with 90° hooks into column support core)
      - Item 3: Transverse shear stirrups / links (with 135° seismic hooks & bend deductions)
      - Concrete Volume & materials (cement bags, sand, aggregate, water)
    """
    from app.engineering.calculators.concrete import calculate_concrete_materials, DRY_VOLUME_FACTOR

    assumptions: list[str] = []
    is_code_provisions: dict[str, str | float] = {}
    items: list[BBSItem] = []
    total_cutting_len_m = 0.0
    total_steel_wt = 0.0

    cover_col = 40.0  # End cover inside supporting column core

    # -------------------------------------------------------------
    # 1. BOTTOM LONGITUDINAL BARS (Tension Reinforcement)
    # -------------------------------------------------------------
    b_dia = request.bottom_bar_dia_mm
    ld_bottom = calculate_development_length(
        bar_diameter_mm=b_dia,
        concrete_grade=request.concrete_grade,
        steel_grade=request.steel_grade,
        stress_type=StressType.TENSION,
    )
    b_hook_leg = 12.0 * b_dia
    b_straight_left = max(0.0, request.left_support_width_mm - cover_col)
    b_straight_right = max(0.0, request.right_support_width_mm - cover_col)
    b_anchor_left = round(min(ld_bottom.development_length_mm, b_straight_left + b_hook_leg), 1)
    b_anchor_right = round(min(ld_bottom.development_length_mm, b_straight_right + b_hook_leg), 1)

    b_ded = calculate_bend_deduction(b_dia, 90.0).deduction_mm * 2.0 if request.deduct_bends else 0.0

    b_breakdown = [
        CalculationBreakdown(label="Clear span length", length_mm=request.clear_span_mm, clause="Drawing Detail"),
        CalculationBreakdown(
            label=f"Left support anchorage (90° hook: [{request.left_support_width_mm:.0f} - {cover_col:.0f} col cover] + 12d leg [{b_hook_leg:.0f} mm])",
            length_mm=b_anchor_left,
            clause="IS 456 Cl. 26.2.3.3",
        ),
        CalculationBreakdown(
            label=f"Right support anchorage (90° hook: [{request.right_support_width_mm:.0f} - {cover_col:.0f} col cover] + 12d leg [{b_hook_leg:.0f} mm])",
            length_mm=b_anchor_right,
            clause="IS 456 Cl. 26.2.3.3",
        ),
        CalculationBreakdown(label="Bend deductions (2 x 90 deg: -4d)", length_mm=-b_ded, clause="SP 34 Cl. 3.2"),
    ]
    b_cut_mm = round(sum(row.length_mm for row in b_breakdown), 1)
    b_cut_m = round(b_cut_mm / 1000.0, 3)
    b_unit_wt = round((b_dia ** 2) / 162.0, 3)
    b_tot_len = round(b_cut_m * request.bottom_bars_count, 3)
    b_tot_wt = round(b_unit_wt * b_tot_len, 2)

    items.append(
        BBSItem(
            bar_mark="Bottom Longitudinal Bars",
            bar_type="main",
            bar_diameter_mm=b_dia,
            num_bars=request.bottom_bars_count,
            cutting_length_mm=b_cut_mm,
            cutting_length_m=b_cut_m,
            total_length_m=b_tot_len,
            unit_weight_kg_m=b_unit_wt,
            total_weight_kg=b_tot_wt,
            shape_description=f"Bottom tension bars ({request.bottom_bars_count}-T{b_dia:.0f}) anchored into column support with 90° hooks",
            breakdown=b_breakdown,
        )
    )
    total_cutting_len_m += b_cut_m
    total_steel_wt += b_tot_wt

    # -------------------------------------------------------------
    # 2. TOP LONGITUDINAL BARS (Hangers / Compression Reinforcement)
    # -------------------------------------------------------------
    if request.top_bars_count > 0:
        t_dia = request.top_bar_dia_mm
        ld_top = calculate_development_length(
            bar_diameter_mm=t_dia,
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            stress_type=StressType.TENSION,
        )
        t_hook_leg = 12.0 * t_dia
        t_straight_left = max(0.0, request.left_support_width_mm - cover_col)
        t_straight_right = max(0.0, request.right_support_width_mm - cover_col)
        t_anchor_left = round(min(ld_top.development_length_mm, t_straight_left + t_hook_leg), 1)
        t_anchor_right = round(min(ld_top.development_length_mm, t_straight_right + t_hook_leg), 1)

        t_ded = calculate_bend_deduction(t_dia, 90.0).deduction_mm * 2.0 if request.deduct_bends else 0.0

        t_breakdown = [
            CalculationBreakdown(label="Clear span length", length_mm=request.clear_span_mm, clause="Drawing Detail"),
            CalculationBreakdown(
                label=f"Left support anchorage (90° hook: [{request.left_support_width_mm:.0f} - {cover_col:.0f} col cover] + 12d leg [{t_hook_leg:.0f} mm])",
                length_mm=t_anchor_left,
                clause="IS 456 Cl. 26.2.3.3",
            ),
            CalculationBreakdown(
                label=f"Right support anchorage (90° hook: [{request.right_support_width_mm:.0f} - {cover_col:.0f} col cover] + 12d leg [{t_hook_leg:.0f} mm])",
                length_mm=t_anchor_right,
                clause="IS 456 Cl. 26.2.3.3",
            ),
            CalculationBreakdown(label="Bend deductions (2 x 90 deg: -4d)", length_mm=-t_ded, clause="SP 34 Cl. 3.2"),
        ]
        t_cut_mm = round(sum(row.length_mm for row in t_breakdown), 1)
        t_cut_m = round(t_cut_mm / 1000.0, 3)
        t_unit_wt = round((t_dia ** 2) / 162.0, 3)
        t_tot_len = round(t_cut_m * request.top_bars_count, 3)
        t_tot_wt = round(t_unit_wt * t_tot_len, 2)

        items.append(
            BBSItem(
                bar_mark="Top Longitudinal Hanger Bars",
                bar_type="secondary",
                bar_diameter_mm=t_dia,
                num_bars=request.top_bars_count,
                cutting_length_mm=t_cut_mm,
                cutting_length_m=t_cut_m,
                total_length_m=t_tot_len,
                unit_weight_kg_m=t_unit_wt,
                total_weight_kg=t_tot_wt,
                shape_description=f"Top anchor/hanger bars ({request.top_bars_count}-T{t_dia:.0f}) anchored into column support with 90° hooks",
                breakdown=t_breakdown,
            )
        )
        total_steel_wt += t_tot_wt

    # -------------------------------------------------------------
    # 3. TRANSVERSE SHEAR STIRRUPS / LINKS
    # -------------------------------------------------------------
    s_dia = request.stirrup_dia_mm
    s_pitch = request.stirrup_spacing_mm
    cov = request.clear_cover_mm

    core_w = max(50.0, request.beam_width_mm - (2.0 * cov))
    core_d = max(50.0, request.beam_depth_mm - (2.0 * cov))
    hook_ext = 2.0 * (10.0 * s_dia)  # 2 x 135 deg seismic hooks per IS 456 Cl. 26.2.2.4

    bend_ded_90 = calculate_bend_deduction(s_dia, 90.0).deduction_mm if request.deduct_bends else 0.0
    bend_ded_135 = calculate_bend_deduction(s_dia, 135.0).deduction_mm if request.deduct_bends else 0.0
    s_total_ded = (3.0 * bend_ded_90) + (2.0 * bend_ded_135)

    s_breakdown = [
        CalculationBreakdown(label=f"Core horizontal width (2 x {core_w:.0f} mm)", length_mm=2.0 * core_w, clause="IS 456 Cl. 26.4.2.1"),
        CalculationBreakdown(label=f"Core vertical depth (2 x {core_d:.0f} mm)", length_mm=2.0 * core_d, clause="IS 456 Cl. 26.4.2.1"),
        CalculationBreakdown(label=f"Two 135° seismic hooks (2 x 10d = {hook_ext:.0f} mm)", length_mm=hook_ext, clause="IS 456 Cl. 26.2.2.4"),
        CalculationBreakdown(label="Bend deductions (3x 90° + 2x 135° bends)", length_mm=-s_total_ded, clause="SP 34 Cl. 3.2"),
    ]
    s_cut_mm = round(sum(row.length_mm for row in s_breakdown), 1)
    s_cut_m = round(s_cut_mm / 1000.0, 3)

    num_stirrups = int(math.floor(request.clear_span_mm / s_pitch)) + 1 if s_pitch > 0 else 0
    s_unit_wt = round((s_dia ** 2) / 162.0, 3)
    s_tot_len = round(s_cut_m * num_stirrups, 3)
    s_tot_wt = round(s_unit_wt * s_tot_len, 2)

    items.append(
        BBSItem(
            bar_mark="Shear Stirrups / Links",
            bar_type="tie",
            bar_diameter_mm=s_dia,
            num_bars=num_stirrups,
            spacing_mm=s_pitch,
            cutting_length_mm=s_cut_mm,
            cutting_length_m=s_cut_m,
            total_length_m=s_tot_len,
            unit_weight_kg_m=s_unit_wt,
            total_weight_kg=s_tot_wt,
            shape_description=f"2-legged closed rectangular stirrup ({core_w:.0f}x{core_d:.0f} mm) with 135° seismic hooks @ {s_pitch:.0f} mm c/c",
            breakdown=s_breakdown,
        )
    )
    total_steel_wt += s_tot_wt

    # -------------------------------------------------------------
    # 4. CONCRETE VOLUME & MATERIALS
    # -------------------------------------------------------------
    # Gross rectangular clear span beam volume
    vol_m3 = round((request.beam_width_mm * request.beam_depth_mm * request.clear_span_mm) / 1e9, 4)
    mat = calculate_concrete_materials(vol_m3, request.concrete_grade)
    dry_v = round(vol_m3 * DRY_VOLUME_FACTOR, 4)

    # Engineering Documentation & Code Provisions
    assumptions.append(
        f"Support anchorage = (Supporting column width {request.left_support_width_mm:.0f} mm - 40 mm end cover) + (12 * bar_dia {b_dia:.0f} mm vertical bend leg) = {b_straight_left:.0f} + {b_hook_leg:.0f} = {b_anchor_left:.1f} mm per IS 456:2000 Cl. 26.2.3.3 & SP 34."
    )
    assumptions.append(
        f"Stirrup count = floor(Clear span {request.clear_span_mm:.0f} mm / Spacing {s_pitch:.0f} mm) + 1 = {num_stirrups} stirrups per IS 456 Cl. 26.5.1.5."
    )
    assumptions.append(
        f"Development length Ld = {ld_bottom.development_length_mm:.1f} mm ({ld_bottom.development_length_factor}d) for Fe500 in {request.concrete_grade} per IS 456:2000 Cl. 26.2.1."
    )
    assumptions.append(
        f"Gross concrete volume = {request.beam_width_mm:.0f} mm x {request.beam_depth_mm:.0f} mm x {request.clear_span_mm:.0f} mm = {vol_m3:.3f} m3 per IS 456:2000."
    )

    is_code_provisions["Ld_tension_mm"] = ld_bottom.development_length_mm
    is_code_provisions["Ld_factor"] = ld_bottom.development_length_factor
    is_code_provisions["support_anchorage_left_mm"] = b_anchor_left
    is_code_provisions["support_anchorage_right_mm"] = b_anchor_right
    is_code_provisions["stirrups_count"] = num_stirrups
    is_code_provisions["stirrup_cutting_length_m"] = s_cut_m

    return BBSCalculationResult(
        member_id=request.member_id,
        member_type="BEAM",
        total_cutting_length_m=b_cut_m,
        total_cutting_length_mm=b_cut_mm,
        total_weight_kg=round(total_steel_wt, 2),
        items=items,
        concrete_volume_m3=vol_m3,
        dry_volume_m3=dry_v,
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

