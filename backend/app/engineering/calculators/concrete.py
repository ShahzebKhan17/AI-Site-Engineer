"""Concrete volume and material estimation calculator per IS 456:2000 standards.

Computes exact concrete volume (m³) for all 9 structural members:
- Column, Beam, Footing/Raft, Slab, Pile, Pile Cap, Pier, Retaining Wall, Staircase
And estimates material quantities:
- Dry volume (1.54x factor), 50kg cement bags, sand (m³/kg), coarse aggregate (m³/kg), and water (liters per IS 456 Table 5).
"""

import math
from typing import Any
from pydantic import BaseModel, Field

ENGINE_VERSION = "0.3.0"

# Standard nominal and design mix ratios (Cement : Fine Aggregate : Coarse Aggregate)
CONCRETE_MIX_RATIOS: dict[str, tuple[float, float, float]] = {
    "M15": (1.0, 2.0, 4.0),
    "M20": (1.0, 1.5, 3.0),
    "M25": (1.0, 1.0, 2.0),
    "M30": (1.0, 0.75, 1.5),
    "M35": (1.0, 0.65, 1.3),
    "M40": (1.0, 0.55, 1.1),
}

# Maximum free water-cement ratio per IS 456:2000 Table 5 (Reinforced Concrete)
WATER_CEMENT_RATIOS: dict[str, float] = {
    "M15": 0.55,
    "M20": 0.50,
    "M25": 0.45,
    "M30": 0.45,
    "M35": 0.40,
    "M40": 0.40,
}

DENSITY_CEMENT_KG_M3 = 1440.0
DENSITY_SAND_KG_M3 = 1600.0
DENSITY_AGGREGATE_KG_M3 = 1500.0
DRY_VOLUME_FACTOR = 1.54  # 54% increase for dry voids & shrinkage


class ConcreteMaterialBreakdown(BaseModel):
    cement_bags: float
    cement_kg: float
    sand_m3: float
    sand_kg: float
    aggregate_m3: float
    aggregate_kg: float
    water_liters: float
    mix_ratio: str
    water_cement_ratio: float
    dry_volume_factor: float = DRY_VOLUME_FACTOR


class ConcreteCalculationResult(BaseModel):
    member_id: str
    member_type: str
    concrete_grade: str
    volume_m3: float
    dry_volume_m3: float
    materials: ConcreteMaterialBreakdown
    dimensions_summary: str
    assumptions: list[str] = Field(default_factory=list)
    code_provisions: dict[str, str | float] = Field(default_factory=dict)
    engine_version: str = ENGINE_VERSION

    @property
    def concrete_volume_m3(self) -> float:
        return self.volume_m3


def calculate_concrete_materials(volume_m3: float, concrete_grade: str = "M25") -> ConcreteMaterialBreakdown:
    """Calculate cement bags, sand, aggregate, and water for a given wet concrete volume."""
    grade_key = concrete_grade.strip().upper()
    if grade_key not in CONCRETE_MIX_RATIOS:
        grade_key = "M25"

    c_part, s_part, a_part = CONCRETE_MIX_RATIOS[grade_key]
    total_parts = c_part + s_part + a_part
    dry_vol = volume_m3 * DRY_VOLUME_FACTOR

    cement_m3 = (c_part / total_parts) * dry_vol
    cement_kg = round(cement_m3 * DENSITY_CEMENT_KG_M3, 1)
    cement_bags = round(cement_kg / 50.0, 2)

    sand_m3 = round((s_part / total_parts) * dry_vol, 3)
    sand_kg = round(sand_m3 * DENSITY_SAND_KG_M3, 1)

    agg_m3 = round((a_part / total_parts) * dry_vol, 3)
    agg_kg = round(agg_m3 * DENSITY_AGGREGATE_KG_M3, 1)

    w_c = WATER_CEMENT_RATIOS.get(grade_key, 0.45)
    water_liters = round(cement_kg * w_c, 1)

    mix_str = f"{c_part:g} : {s_part:g} : {a_part:g}"

    return ConcreteMaterialBreakdown(
        cement_bags=cement_bags,
        cement_kg=cement_kg,
        sand_m3=sand_m3,
        sand_kg=sand_kg,
        aggregate_m3=agg_m3,
        aggregate_kg=agg_kg,
        water_liters=water_liters,
        mix_ratio=mix_str,
        water_cement_ratio=w_c,
        dry_volume_factor=DRY_VOLUME_FACTOR,
    )


def calculate_member_concrete_volume(
    member_type: str,
    member_id: str,
    concrete_grade: str = "M25",
    params: dict[str, Any] | None = None,
) -> ConcreteCalculationResult:
    """Deterministic concrete volume and material calculator for any structural member."""
    mtype = member_type.strip().lower()
    p = params or {}
    grade = concrete_grade.strip().upper()

    vol_m3 = 0.0
    dim_summary = ""
    assumptions: list[str] = [
        f"Concrete grade: {grade} per IS 456:2000 Table 2.",
        f"Dry volume conversion factor: {DRY_VOLUME_FACTOR}x (IS 456 allowance for voids and shrinkage).",
        "Cement standard weight: 50 kg per bag (density 1440 kg/m³).",
    ]

    if mtype == "column":
        w = float(p.get("width_mm") or p.get("column_width_mm") or 0.0)
        d = float(p.get("depth_mm") or p.get("column_depth_mm") or 0.0)
        h = float(p.get("storey_height_mm") or p.get("height_mm") or 0.0)
        if not (w and d and h):
            missing_keys = [k for k, v in [("width_mm", w), ("depth_mm", d), ("storey_height_mm", h)] if not v]
            raise ValueError(f"Dynamic dimensions missing for COLUMN {member_id}: {', '.join(missing_keys)}. Exact drawing geometry required.")
        vol_m3 = round((w * d * h) / 1e9, 4)
        dim_summary = f"{w:g} mm x {d:g} mm x {h:g} mm height"

    elif mtype == "beam":
        w = float(p.get("beam_width_mm") or p.get("width_mm") or 0.0)
        d = float(p.get("beam_depth_mm") or p.get("depth_mm") or 0.0)
        clear_span = float(p.get("clear_span_mm") or p.get("span_mm") or 0.0)
        left_supp = float(p.get("left_support_width_mm") or 0.0)
        right_supp = float(p.get("right_support_width_mm") or 0.0)
        if not (w and d and clear_span):
            missing_keys = [k for k, v in [("beam_width_mm", w), ("beam_depth_mm", d), ("clear_span_mm", clear_span)] if not v]
            raise ValueError(f"Dynamic dimensions missing for BEAM {member_id}: {', '.join(missing_keys)}. Exact drawing geometry required.")
        total_len = clear_span + left_supp + right_supp
        vol_m3 = round((w * d * total_len) / 1e9, 4)
        dim_summary = f"{w:g} mm x {d:g} mm x {total_len:g} mm total span"

    elif mtype in ("footing", "raft"):
        l = float(p.get("length_mm") or 0.0)
        w = float(p.get("width_mm") or 0.0)
        d = float(p.get("depth_mm") or 0.0)
        if not (l and w and d):
            missing_keys = [k for k, v in [("length_mm", l), ("width_mm", w), ("depth_mm", d)] if not v]
            raise ValueError(f"Dynamic dimensions missing for {mtype.upper()} {member_id}: {', '.join(missing_keys)}. Exact drawing geometry required.")
        vol_m3 = round((l * w * d) / 1e9, 4)
        dim_summary = f"{l:g} mm x {w:g} mm x {d:g} mm depth"

    elif mtype == "slab":
        lx = float(p.get("width_lx_mm") or p.get("width_mm") or 0.0)
        ly = float(p.get("length_ly_mm") or p.get("length_mm") or 0.0)
        th = float(p.get("thickness_mm") or p.get("depth_mm") or 0.0)
        if not (lx and ly and th):
            missing_keys = [k for k, v in [("width_lx_mm", lx), ("length_ly_mm", ly), ("thickness_mm", th)] if not v]
            raise ValueError(f"Dynamic dimensions missing for SLAB {member_id}: {', '.join(missing_keys)}. Exact drawing geometry required.")
        vol_m3 = round((lx * ly * th) / 1e9, 4)
        dim_summary = f"{lx:g} mm (Lx) x {ly:g} mm (Ly) x {th:g} mm thick"

    elif mtype == "pile":
        dia = float(p.get("pile_diameter_mm") or p.get("diameter_mm") or 0.0)
        l_m = float(p.get("pile_length_m") or p.get("length_m") or 0.0)
        if not (dia and l_m):
            missing_keys = [k for k, v in [("pile_diameter_mm", dia), ("pile_length_m", l_m)] if not v]
            raise ValueError(f"Dynamic dimensions missing for PILE {member_id}: {', '.join(missing_keys)}. Exact drawing geometry required.")
        radius_m = (dia / 1000.0) / 2.0
        vol_m3 = round(math.pi * (radius_m ** 2) * l_m, 4)
        dim_summary = f"{dia:g} mm dia x {l_m:.2f} m depth"

    elif mtype == "pile_cap":
        l = float(p.get("length_mm") or 0.0)
        w = float(p.get("width_mm") or 0.0)
        d = float(p.get("depth_mm") or 0.0)
        if not (l and w and d):
            missing_keys = [k for k, v in [("length_mm", l), ("width_mm", w), ("depth_mm", d)] if not v]
            raise ValueError(f"Dynamic dimensions missing for PILE_CAP {member_id}: {', '.join(missing_keys)}. Exact drawing geometry required.")
        vol_m3 = round((l * w * d) / 1e9, 4)
        dim_summary = f"{l:g} mm x {w:g} mm x {d:g} mm depth"

    elif mtype == "pier":
        d1 = float(p.get("dimension_1_mm") or p.get("width_mm") or 0.0)
        d2 = float(p.get("dimension_2_mm") or p.get("depth_mm") or 0.0)
        h = float(p.get("height_mm") or 0.0)
        if not (d1 and d2 and h):
            missing_keys = [k for k, v in [("dimension_1_mm", d1), ("dimension_2_mm", d2), ("height_mm", h)] if not v]
            raise ValueError(f"Dynamic dimensions missing for PIER {member_id}: {', '.join(missing_keys)}. Exact drawing geometry required.")
        vol_m3 = round((d1 * d2 * h) / 1e9, 4)
        dim_summary = f"{d1:g} mm x {d2:g} mm x {h:g} mm height"

    elif mtype == "retaining_wall":
        l_m = float(p.get("wall_length_m") or p.get("length_m") or 0.0)
        h_stem = float(p.get("stem_height_mm") or 0.0)
        b_base = float(p.get("base_slab_width_mm") or 0.0)
        d_base = float(p.get("base_slab_thickness_mm") or 0.0)
        t_stem = float(p.get("stem_base_thickness_mm") or 0.0)
        if not (l_m and h_stem and b_base and d_base and t_stem):
            missing_keys = [k for k, v in [("wall_length_m", l_m), ("stem_height_mm", h_stem), ("base_slab_width_mm", b_base), ("base_slab_thickness_mm", d_base), ("stem_base_thickness_mm", t_stem)] if not v]
            raise ValueError(f"Dynamic dimensions missing for RETAINING_WALL {member_id}: {', '.join(missing_keys)}. Exact drawing geometry required.")
        l_mm = l_m * 1000.0
        v_base = (b_base * d_base * l_mm) / 1e9
        v_stem = (t_stem * h_stem * l_mm) / 1e9
        vol_m3 = round(v_base + v_stem, 4)
        dim_summary = f"Base: {b_base:g}x{d_base:g} mm, Stem: {h_stem:g}x{t_stem:g} mm, Length: {l_m:.2f} m"

    elif mtype == "staircase":
        w = float(p.get("flight_width_mm") or 0.0)
        th = float(p.get("waist_slab_thickness_mm") or 0.0)
        r = float(p.get("riser_mm") or 0.0)
        t = float(p.get("tread_mm") or 0.0)
        n_r = int(p.get("num_risers") or 0)
        n_t = int(p.get("num_treads") or 0)
        l_bot = float(p.get("bottom_landing_length_mm") or 0.0)
        l_top = float(p.get("top_landing_length_mm") or 0.0)
        if not (w and th and r and t and n_r and n_t):
            missing_keys = [k for k, v in [("flight_width_mm", w), ("waist_slab_thickness_mm", th), ("riser_mm", r), ("tread_mm", t), ("num_risers", n_r), ("num_treads", n_t)] if not v]
            raise ValueError(f"Dynamic dimensions missing for STAIRCASE {member_id}: {', '.join(missing_keys)}. Exact drawing geometry required.")

        # Inclined waist slab
        going_mm = n_t * t
        height_mm = n_r * r
        slope_len_mm = math.sqrt(going_mm ** 2 + height_mm ** 2)
        v_waist = (slope_len_mm * w * th) / 1e9

        # Steps triangular volume
        v_steps = n_t * ((0.5 * r * t * w) / 1e9)

        # Landings volume
        v_landings = ((l_bot + l_top) * w * th) / 1e9
        vol_m3 = round(v_waist + v_steps + v_landings, 4)
        dim_summary = f"Flight width: {w:g} mm, Waist: {th:g} mm, {n_r} risers, {n_t} treads, 2 landings"

    else:
        raise ValueError(f"Unsupported structural member type: '{member_type}'. Must be one of column, beam, footing/raft, slab, pile, pile_cap, pier, retaining_wall, staircase.")

    materials = calculate_concrete_materials(vol_m3, grade)
    dry_vol_m3 = round(vol_m3 * DRY_VOLUME_FACTOR, 4)

    code_provisions = {
        "is_code": "IS 456:2000 Table 2 & Table 5",
        "concrete_grade": grade,
        "nominal_mix": materials.mix_ratio,
        "water_cement_ratio": materials.water_cement_ratio,
        "dry_volume_factor": DRY_VOLUME_FACTOR,
    }

    return ConcreteCalculationResult(
        member_id=member_id.upper(),
        member_type=mtype.upper(),
        concrete_grade=grade,
        volume_m3=vol_m3,
        dry_volume_m3=dry_vol_m3,
        materials=materials,
        dimensions_summary=dim_summary,
        assumptions=assumptions,
        code_provisions=code_provisions,
        engine_version=ENGINE_VERSION,
    )
