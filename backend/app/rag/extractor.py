"""Structured extraction service mapping drawing evidence snippets into engineering calculation models."""

import os
import re
from typing import Sequence
from pydantic import BaseModel, Field

from app.engineering.calculators.beam import BeamBarRequest
from app.engineering.calculators.footing import FootingMeshRequest
from app.engineering.calculators.pier import PierScheduleRequest
from app.engineering.calculators.pile import PileScheduleRequest
from app.engineering.calculators.pile_cap import PileCapScheduleRequest
from app.engineering.calculators.retaining_wall import RetainingWallScheduleRequest
from app.engineering.calculators.slab import SlabScheduleRequest
from app.engineering.calculators.staircase import StaircaseScheduleRequest
from app.engineering.models import ColumnBarRequest
from app.rag.retrieval import RetrievedChunk


class ScheduleTableRow(BaseModel):
    bar_id: str = ""
    reinforcement: str = ""
    location: str = ""
    layer: str = ""
    bar_diameter_mm: float | None = None
    spacing_mm: float | None = None


class ExtractionOutput(BaseModel):
    member_id: str
    member_type: str = "column"
    column_request: ColumnBarRequest | None = None
    beam_request: BeamBarRequest | None = None
    footing_request: FootingMeshRequest | None = None
    slab_request: SlabScheduleRequest | None = None
    pile_request: PileScheduleRequest | None = None
    pile_cap_request: PileCapScheduleRequest | None = None
    staircase_request: StaircaseScheduleRequest | None = None
    pier_request: PierScheduleRequest | None = None
    retaining_wall_request: RetainingWallScheduleRequest | None = None
    schedule_rows: list[ScheduleTableRow] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    extracted_from_pages: list[int] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def parse_reinforcement_schedule_table(text: str) -> list[ScheduleTableRow]:
    """Parse structural drawing reinforcement schedule tables (e.g. REINFORCEMENT TYPICAL SCHEDULE).

    Detects schedules and maps BAR ID, REINFORCEMENT (e.g. Y16 AT 150 C/C),
    LOCATION (e.g. RAFT), and LAYER (e.g. BOTTOM, TOP, SHEAR LINKS),
    extracting rebar diameters and spacing.
    """
    rows: list[ScheduleTableRow] = []

    # Regex matching schedule rows in multi-line, pipe-delimited, key-value, or continuous whitespace format
    row_pattern = re.compile(
        r"(?:(?:BAR\s*(?:ID|MARK|NO\.?)\s*[:=]?\s*)|(?:\b))"
        r"([A-Z0-9_\-]+)\s*[:|,]?\s+"
        r"(?:(?:REINFORCEMENT\s*[:=]?\s*)|(?:\b))"
        r"((?:Y|T|TOR|#|dia|Ø)?\s*\d+\s*(?:AT|@)\s*\d+\s*(?:C/C|c/c|mm\s*c/c)?)\s*[:|,]?\s+"
        r"(?:(?:LOCATION\s*[:=]?\s*)|(?:\b))([A-Za-z0-9_\-]+)\s*[:|,]?\s+"
        r"(?:(?:LAYER\s*[:=]?\s*)|(?:\b))(BOTTOM(?:\s*MESH)?|TOP(?:\s*MESH)?|SHEAR\s*LINKS?|LINKS?|CHAIRS?)",
        re.IGNORECASE,
    )

    for match in row_pattern.finditer(text):
        bid = match.group(1).strip()
        if bid.upper() in ("BAR", "ID", "MARK", "SCHEDULE", "ITEM", "REV"):
            continue
        reinf = match.group(2).strip()
        loc = match.group(3).strip().upper()
        layer = match.group(4).strip().upper()

        dia_m = re.search(r"(?:Y|T|TOR|#|dia|Ø)?\s*(8|10|12|16|20|25|28|32)\b", reinf, re.IGNORECASE)
        sp_m = re.search(r"(?:AT|@)\s*(\d+)", reinf, re.IGNORECASE)
        bar_dia = float(dia_m.group(1)) if dia_m else None
        spacing = float(sp_m.group(1)) if sp_m else None

        rows.append(
            ScheduleTableRow(
                bar_id=bid,
                reinforcement=reinf,
                location=loc,
                layer=layer,
                bar_diameter_mm=bar_dia,
                spacing_mm=spacing,
            )
        )

    if not rows:
        # Flexible pattern for lines like "Bottom: Y16 @ 150 c/c" or "01 Y16 AT 150 C/C RAFT BOTTOM"
        flexible_pattern = re.compile(
            r"(?:([A-Z0-9_\-]+)\s+)?(?:(?:LOCATION\s*[:=]?\s*)?([A-Za-z0-9_\-]+)\s+)?(BOTTOM|TOP|SHEAR\s*LINKS?|LINKS?)\s*(?:MESH|REINFORCEMENT|LAYER)?\s*[:=]?\s*"
            r"((?:Y|T|TOR|#|dia|Ø)?\s*\d+\s*(?:AT|@)\s*\d+\s*(?:C/C|c/c|mm\s*c/c)?)",
            re.IGNORECASE,
        )
        for match in flexible_pattern.finditer(text):
            bid = (match.group(1) or "").strip()
            loc = (match.group(2) or ("RAFT" if "raft" in text.lower() else "FOUNDATION")).strip().upper()
            layer = match.group(3).strip().upper()
            reinf = match.group(4).strip()
            dia_m = re.search(r"(?:Y|T|TOR|#|dia|Ø)?\s*(8|10|12|16|20|25|28|32)\b", reinf, re.IGNORECASE)
            sp_m = re.search(r"(?:AT|@)\s*(\d+)", reinf, re.IGNORECASE)
            bar_dia = float(dia_m.group(1)) if dia_m else None
            spacing = float(sp_m.group(1)) if sp_m else None
            rows.append(
                ScheduleTableRow(
                    bar_id=bid or ("01" if "BOTTOM" in layer else ("02" if "TOP" in layer else "03")),
                    reinforcement=reinf,
                    location=loc,
                    layer=layer,
                    bar_diameter_mm=bar_dia,
                    spacing_mm=spacing,
                )
            )

    return rows


def infer_member_type(member_id: str, text: str = "") -> str:
    """Infer structural member category from member ID tag or context."""
    mid = member_id.upper().strip()
    if mid.startswith("PC"):
        return "pile_cap"
    if mid.startswith("PR") or mid.startswith("PD"):
        return "pier"
    if mid.startswith("ST") or mid.startswith("SC"):
        return "staircase"
    if mid.startswith("RW") or mid.startswith("RET"):
        return "retaining_wall"
    if mid.startswith("C"):
        return "column"
    if mid.startswith("B"):
        return "beam"
    if mid.startswith("F") or mid.startswith("RF") or "RAFT" in mid:
        return "footing"
    if mid.startswith("P"):
        return "pile"
    if mid.startswith("S"):
        return "slab"

    # Context fallback
    lower = text.lower()
    if "pile cap" in lower:
        return "pile_cap"
    if "pier" in lower or "pedestal" in lower:
        return "pier"
    if "stair" in lower:
        return "staircase"
    if "retaining" in lower:
        return "retaining_wall"
    if "slab" in lower:
        return "slab"
    if "pile" in lower:
        return "pile"
    if "beam" in lower:
        return "beam"
    if "footing" in lower or "raft" in lower or "foundation" in lower:
        return "footing"
    return "column"


def regex_extract_drawing_dimensions(
    text: str,
    target_member_id: str,
    citations: list[str],
    pages: list[int],
    specified_member_type: str | None = None,
) -> ExtractionOutput:
    """Deterministic extractor parsing engineering parameters from drawing schedule text."""
    missing: list[str] = []
    notes: list[str] = []
    member_type = specified_member_type or infer_member_type(target_member_id, text)

    # 1. Concrete & Steel Grade extraction
    concrete_match = re.search(r"\b(M20|M25|M30|M35|M40)\b", text, re.IGNORECASE)
    concrete_grade = concrete_match.group(1).upper() if concrete_match else ("M35" if member_type == "pier" else "M25")

    steel_match = re.search(r"\b(Fe\s*250|Fe\s*415|Fe\s*500|Fe\s*550)\b", text, re.IGNORECASE)
    steel_grade = steel_match.group(1).replace(" ", "").upper() if steel_match else "FE500"

    citations_list = citations if citations else ["drawing:evidence#unspecified"]

    col_req: ColumnBarRequest | None = None
    beam_req: BeamBarRequest | None = None
    foot_req: FootingMeshRequest | None = None
    slab_req: SlabScheduleRequest | None = None
    pile_req: PileScheduleRequest | None = None
    pc_req: PileCapScheduleRequest | None = None
    stair_req: StaircaseScheduleRequest | None = None
    pier_req: PierScheduleRequest | None = None
    rw_req: RetainingWallScheduleRequest | None = None

    confidence = 1.0

    sched_rows = parse_reinforcement_schedule_table(text)

    if member_type == "slab":
        lx_match = re.search(r"(?:Lx|short(?:er)?\s*span|width)\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        ly_match = re.search(r"(?:Ly|long(?:er)?\s*span|length)\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        thick_match = re.search(r"(?:thickness|depth|D)\s*(?:is|=|:)?\s*(\d{2,4})\s*mm", text, re.IGNORECASE)
        main_dia_match = re.search(r"(?:main(?:\s*bottom)?(?: reinforcement| rebar)?)\s*[:=]?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(8|10|12|16|20|25|28|32)\b", text, re.IGNORECASE)
        dist_dia_match = re.search(r"(?:distribution(?: reinforcement| rebar)?)\s*[:=]?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(8|10|12|16|20|25|28|32)\b", text, re.IGNORECASE)

        if not lx_match or not ly_match:
            dims_pair = re.search(r"(\d{3,5})\s*mm?\s*x\s*(\d{3,5})\s*mm?", text, re.IGNORECASE)
            if dims_pair:
                v1, v2 = float(dims_pair.group(1)), float(dims_pair.group(2))
                lx = min(v1, v2)
                ly = max(v1, v2)
            else:
                lx = float(lx_match.group(1)) if lx_match else None
                ly = float(ly_match.group(1)) if ly_match else None
        else:
            lx = float(lx_match.group(1))
            ly = float(ly_match.group(1))

        thick = float(thick_match.group(1)) if thick_match else None
        main_dia = float(main_dia_match.group(1)) if main_dia_match else None
        dist_dia = float(dist_dia_match.group(1)) if dist_dia_match else None

        if not lx:
            missing.append("width_lx_mm")
        if not ly:
            missing.append("length_ly_mm")
        if not thick:
            missing.append("thickness_mm")
        if not main_dia:
            missing.append("main_bar_dia_mm")

        main_sp_match = re.search(r"main.*?(?:@|at)\s*(\d+)\s*(?:mm)?", text, re.IGNORECASE)
        dist_sp_match = re.search(r"dist.*?(?:@|at)\s*(\d+)\s*(?:mm)?", text, re.IGNORECASE)
        bearing_match = re.search(r"(?:bearing|support\s*width)\s*(?:is|=|:)?\s*(\d{2,4})\s*mm", text, re.IGNORECASE)

        main_sp = float(main_sp_match.group(1)) if main_sp_match else 150.0
        dist_sp = float(dist_sp_match.group(1)) if dist_sp_match else 175.0
        bearing = float(bearing_match.group(1)) if bearing_match else 230.0
        d_dia = dist_dia or 8.0

        if lx and ly and thick and main_dia:
            slab_req = SlabScheduleRequest(
                member_id=target_member_id,
                length_ly_mm=ly,
                width_lx_mm=lx,
                thickness_mm=thick,
                support_width_mm=bearing,
                main_bar_dia_mm=main_dia,
                main_bar_spacing_mm=main_sp,
                dist_bar_dia_mm=d_dia,
                dist_bar_spacing_mm=dist_sp,
                clear_cover_mm=20.0,
                is_cranked=True,
                concrete_grade=concrete_grade,
                steel_grade=steel_grade,
                source_references=citations_list,
            )

    elif member_type == "pile":
        dia_match = re.search(r"(?:shaft\s*)?diameter\s*(?:is|=|:)?\s*(\d{3,4})\s*mm", text, re.IGNORECASE)
        len_match = re.search(r"(?:depth|length)\s*(?:is|=|:)?\s*(\d+(?:\.\d+)?)\s*m\b", text, re.IGNORECASE)
        vert_rebar_match = re.search(r"(\d+)[- ]?(?:Y|T|TOR|#|dia|Ø)?\s*(8|10|12|16|20|25|28|32)\b", text, re.IGNORECASE)

        p_dia = float(dia_match.group(1)) if dia_match else None
        p_len = float(len_match.group(1)) if len_match else None
        num_vert = int(vert_rebar_match.group(1)) if vert_rebar_match else None
        bar_dia = float(vert_rebar_match.group(2)) if vert_rebar_match else None

        if not p_dia:
            missing.append("pile_diameter_mm")
        if not p_len:
            missing.append("pile_length_m")
        if not bar_dia:
            missing.append("main_bar_dia_mm")

        embed_match = re.search(r"(?:embedment|anchorage)\s*(?:is|=|:)?\s*(\d{3,4})\s*mm", text, re.IGNORECASE)
        embed_val = float(embed_match.group(1)) if embed_match else 800.0

        spiral_match = re.search(r"(?:spiral|helical)\s*(\d+)\s*mm\s*@\s*(\d+)\s*mm", text, re.IGNORECASE)
        spiral_dia = float(spiral_match.group(1)) if spiral_match else 8.0
        spiral_pitch = float(spiral_match.group(2)) if spiral_match else 150.0

        if p_dia and p_len and bar_dia:
            pile_req = PileScheduleRequest(
                member_id=target_member_id,
                pile_diameter_mm=p_dia,
                pile_length_m=p_len,
                embedment_into_cap_mm=embed_val,
                main_bar_dia_mm=bar_dia,
                num_main_bars=num_vert or 8,
                spiral_bar_dia_mm=spiral_dia,
                spiral_pitch_mm=spiral_pitch,
                stiffener_bar_dia_mm=16.0,
                stiffener_spacing_m=2.0,
                clear_cover_mm=50.0,
                concrete_grade=concrete_grade,
                steel_grade=steel_grade,
                source_references=citations_list,
            )

    elif member_type == "pile_cap":
        len_match = re.search(r"length\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        wid_match = re.search(r"width\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        depth_match = re.search(r"depth\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        piles_match = re.search(r"(\d+)[- ]pile", text, re.IGNORECASE)

        if not len_match or not wid_match:
            dims_match = re.search(r"(\d{3,5})\s*mm?\s*x\s*(\d{3,5})\s*mm?(?:\s*x\s*(\d{3,5})\s*mm?)?", text, re.IGNORECASE)
            if dims_match:
                l_val = float(dims_match.group(1))
                w_val = float(dims_match.group(2))
                d_val = float(dims_match.group(3)) if dims_match.group(3) else (float(depth_match.group(1)) if depth_match else None)
            else:
                l_val = float(len_match.group(1)) if len_match else None
                w_val = float(wid_match.group(1)) if wid_match else None
                d_val = float(depth_match.group(1)) if depth_match else None
        else:
            l_val = float(len_match.group(1))
            w_val = float(wid_match.group(1))
            d_val = float(depth_match.group(1)) if depth_match else None

        num_p = int(piles_match.group(1)) if piles_match else 4

        if not l_val:
            missing.append("length_mm")
        if not w_val:
            missing.append("width_mm")
        if not d_val:
            missing.append("depth_mm")

        bot_rebar = re.search(r"(?:bottom(?:\s*mesh)?)\s*[:=]?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(\d+)\s*(?:@|at)\s*(\d+)", text, re.IGNORECASE)
        top_rebar = re.search(r"(?:top(?:\s*mesh)?)\s*[:=]?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(\d+)\s*(?:@|at)\s*(\d+)", text, re.IGNORECASE)
        bot_dia = float(bot_rebar.group(1)) if bot_rebar else 20.0
        bot_sp = float(bot_rebar.group(2)) if bot_rebar else 150.0
        top_dia = float(top_rebar.group(1)) if top_rebar else 12.0
        top_sp = float(top_rebar.group(2)) if top_rebar else 200.0

        if l_val and w_val and d_val:
            pc_req = PileCapScheduleRequest(
                member_id=target_member_id,
                length_mm=l_val,
                width_mm=w_val,
                depth_mm=d_val,
                num_piles=num_p,
                bottom_mesh_dia_mm=bot_dia,
                bottom_mesh_spacing_mm=bot_sp,
                has_top_mesh=True,
                top_mesh_dia_mm=top_dia,
                top_mesh_spacing_mm=top_sp,
                num_starter_bars=8,
                starter_bar_dia_mm=20.0,
                clear_cover_mm=50.0,
                concrete_grade=concrete_grade,
                steel_grade=steel_grade,
                source_references=citations_list,
            )

    elif member_type == "staircase":
        risers_match = re.search(r"(\d+)\s*risers?\s*@\s*(\d+)\s*mm", text, re.IGNORECASE)
        treads_match = re.search(r"(\d+)\s*treads?\s*@\s*(\d+)\s*mm", text, re.IGNORECASE)
        width_match = re.search(r"(?:flight\s*width|stair\s*width|width)\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        waist_match = re.search(r"(?:waist(?:\s*slab)?(?:\s*thickness)?)\s*(?:is|=|:)?\s*(\d{2,4})\s*mm", text, re.IGNORECASE)

        num_r = int(risers_match.group(1)) if risers_match else None
        r_mm = float(risers_match.group(2)) if risers_match else None
        num_t = int(treads_match.group(1)) if treads_match else None
        t_mm = float(treads_match.group(2)) if treads_match else None
        f_width = float(width_match.group(1)) if width_match else 1200.0
        waist_th = float(waist_match.group(1)) if waist_match else 150.0

        if not num_r:
            missing.append("num_risers")
        if not r_mm:
            missing.append("riser_mm")
        if not num_t:
            missing.append("num_treads")
        if not t_mm:
            missing.append("tread_mm")

        rebar_match = re.search(r"(?:main(?:\s*rebar)?)\s*[:=]?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(\d+)\s*(?:@|at)\s*(\d+)", text, re.IGNORECASE)
        m_dia = float(rebar_match.group(1)) if rebar_match else 12.0
        m_sp = float(rebar_match.group(2)) if rebar_match else 150.0

        if num_r and r_mm and num_t and t_mm:
            stair_req = StaircaseScheduleRequest(
                member_id=target_member_id,
                flight_width_mm=f_width,
                waist_slab_thickness_mm=waist_th,
                riser_mm=r_mm,
                tread_mm=t_mm,
                num_risers=num_r,
                num_treads=num_t,
                bottom_landing_length_mm=1200.0,
                top_landing_length_mm=1200.0,
                main_bar_dia_mm=m_dia,
                main_bar_spacing_mm=m_sp,
                dist_bar_dia_mm=8.0,
                dist_bar_spacing_mm=175.0,
                clear_cover_mm=20.0,
                concrete_grade=concrete_grade,
                steel_grade=steel_grade,
                source_references=citations_list,
            )

    elif member_type == "pier":
        size_match = re.search(r"(\d{3,4})\s*mm\s*x\s*(\d{3,4})\s*mm", text, re.IGNORECASE)
        height_match = re.search(r"height\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        rebar_match = re.search(r"(\d+)\s*[-]?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(8|10|12|16|20|25|28|32)\b", text, re.IGNORECASE)

        dim1 = float(size_match.group(1)) if size_match else None
        dim2 = float(size_match.group(2)) if size_match else None
        h_val = float(height_match.group(1)) if height_match else None
        n_bars = int(rebar_match.group(1)) if rebar_match else None
        b_dia = float(rebar_match.group(2)) if rebar_match else None

        if not dim1 or not dim2:
            missing.append("pier_dimensions")
        if not h_val:
            missing.append("height_mm")
        if not b_dia:
            missing.append("main_bar_dia_mm")

        ties_match = re.search(r"(?:ties?|hoops?)\s*[:=]?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(\d+)\s*(?:mm)?\s*(?:@|at)\s*(\d+)\s*mm", text, re.IGNORECASE)
        tie_dia = float(ties_match.group(1)) if ties_match else 10.0
        tie_sp = float(ties_match.group(2)) if ties_match else 150.0

        if dim1 and dim2 and h_val and b_dia:
            pier_req = PierScheduleRequest(
                member_id=target_member_id,
                shape="rectangular",
                dimension_1_mm=dim1,
                dimension_2_mm=dim2,
                height_mm=h_val,
                starter_embedment_mm=800.0,
                cap_anchorage_mm=800.0,
                main_bar_dia_mm=b_dia,
                num_main_bars=n_bars or 12,
                tie_bar_dia_mm=tie_dia,
                tie_spacing_mm=tie_sp,
                clear_cover_mm=40.0,
                concrete_grade=concrete_grade,
                steel_grade=steel_grade,
                source_references=citations_list,
            )

    elif member_type == "retaining_wall":
        stem_match = re.search(r"stem\s*height\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        base_match = re.search(r"base\s*slab\s*width\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        stem_th_match = re.search(r"stem\s*(?:base\s*)?thickness\s*(?:is|=|:)?\s*(\d{2,4})\s*mm", text, re.IGNORECASE)
        base_th_match = re.search(r"base\s*(?:slab\s*)?thickness\s*(?:is|=|:)?\s*(\d{2,4})\s*mm", text, re.IGNORECASE)
        rebar_match = re.search(r"(?:vertical|main|earth\s*face).*?(?:Y|T|TOR|#|dia|Ø)?\s*(\d+)\s*(?:@|at)\s*(\d+)", text, re.IGNORECASE)

        h_stem = float(stem_match.group(1)) if stem_match else None
        b_base = float(base_match.group(1)) if base_match else None
        t_stem = float(stem_th_match.group(1)) if stem_th_match else 400.0
        d_base = float(base_th_match.group(1)) if base_th_match else 400.0
        v_dia = float(rebar_match.group(1)) if rebar_match else 16.0
        v_sp = float(rebar_match.group(2)) if rebar_match else 150.0

        if not h_stem:
            missing.append("stem_height_mm")
        if not b_base:
            missing.append("base_slab_width_mm")

        if h_stem and b_base:
            rw_req = RetainingWallScheduleRequest(
                member_id=target_member_id,
                wall_length_m=10.0,
                stem_height_mm=h_stem,
                base_slab_width_mm=b_base,
                base_slab_thickness_mm=d_base,
                stem_base_thickness_mm=t_stem,
                toe_projection_mm=600.0,
                main_bar_dia_mm=v_dia,
                main_bar_spacing_mm=v_sp,
                dist_bar_dia_mm=10.0,
                dist_bar_spacing_mm=200.0,
                curtail_alternate_bars=True,
                clear_cover_mm=50.0,
                concrete_grade=concrete_grade,
                steel_grade=steel_grade,
                source_references=citations_list,
            )

    elif member_type in ("footing", "raft"):
        dims = re.search(r"(\d{3,4})\s*mm\s*x\s*(\d{3,4})\s*mm(?:\s*x\s*(\d{3,4})\s*mm)?", text, re.IGNORECASE)
        l_f = float(dims.group(1)) if dims else None
        w_f = float(dims.group(2)) if dims else None
        d_f = float(dims.group(3)) if dims and dims.group(3) else None

        bottom_row = next((r for r in sched_rows if "BOTTOM" in r.layer.upper()), None)
        top_row = next((r for r in sched_rows if "TOP" in r.layer.upper()), None)
        shear_row = next((r for r in sched_rows if "SHEAR" in r.layer.upper() or "LINK" in r.layer.upper()), None)

        if bottom_row and bottom_row.bar_diameter_mm:
            f_dia = bottom_row.bar_diameter_mm
            f_spacing = bottom_row.spacing_mm or 150.0
        else:
            dia_match = re.search(r"(?:Y|T|TOR|#|dia|Ø)\s*(8|10|12|16|20|25|28|32)\b", text, re.IGNORECASE)
            if not dia_match:
                dia_match = re.search(r"(?:Y|T|TOR|#|dia|Ø)?\s*(8|10|12|16|20|25|28|32)\b", text, re.IGNORECASE)
            f_dia = float(dia_match.group(1)) if dia_match else None
            f_spacing = 150.0

        if (not l_f or not w_f or not d_f) and (bottom_row or sched_rows):
            l_f = l_f or 2000.0
            w_f = w_f or 2000.0
            d_f = d_f or 600.0
            notes.append("Standard typical bay dimensions (2000x2000x600mm) applied for schedule table mesh extraction.")
        else:
            if not l_f or not w_f:
                missing.append("footing_plan_dimensions")
            if not d_f:
                missing.append("depth_mm")

        if not f_dia:
            missing.append("bar_diameter_mm")

        if bottom_row and top_row:
            notes.append(
                f"Schedule table detected: Bottom mesh {int(bottom_row.bar_diameter_mm)}mm ({bottom_row.reinforcement}), "
                f"Top mesh {int(top_row.bar_diameter_mm)}mm ({top_row.reinforcement})"
            )
        if shear_row and shear_row.bar_diameter_mm:
            notes.append(f"Shear links: {int(shear_row.bar_diameter_mm)}mm ({shear_row.reinforcement})")

        if l_f and w_f and d_f and f_dia:
            foot_req = FootingMeshRequest(
                member_id=target_member_id,
                length_mm=l_f,
                width_mm=w_f,
                depth_mm=d_f,
                bar_diameter_mm=f_dia,
                spacing_mm=f_spacing,
                clear_cover_mm=50.0,
                concrete_grade=concrete_grade,
                steel_grade=steel_grade,
                source_references=citations_list,
            )

    elif member_type == "beam":
        span_match = re.search(r"(?:clear\s*)?span\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        dia_match = re.search(r"(?:Y|T|TOR|#|dia|Ø)\s*(8|10|12|16|20|25|28|32)\b", text, re.IGNORECASE)
        if not dia_match:
            dia_match = re.search(r"(?:Y|T|TOR|#|dia|Ø)?\s*(8|10|12|16|20|25|28|32)\b", text, re.IGNORECASE)

        b_dims = re.search(r"(\d{2,4})\s*mm?\s*x\s*(\d{2,4})\s*mm?", text, re.IGNORECASE)
        b_w = float(b_dims.group(1)) if b_dims else None
        b_d = float(b_dims.group(2)) if b_dims else None

        supp_match = re.search(r"(?:support|column)\s*width\s*(?:is|=|:)?\s*(\d{2,4})\s*mm", text, re.IGNORECASE)
        supp_w = float(supp_match.group(1)) if supp_match else 300.0

        span = float(span_match.group(1)) if span_match else None
        b_dia = float(dia_match.group(1)) if dia_match else None

        if not span:
            missing.append("clear_span_mm")
        if not b_dia:
            missing.append("bar_diameter_mm")

        if span and b_dia:
            beam_req = BeamBarRequest(
                member_id=target_member_id,
                bar_diameter_mm=b_dia,
                clear_span_mm=span,
                beam_width_mm=b_w,
                beam_depth_mm=b_d,
                left_support_width_mm=supp_w,
                right_support_width_mm=supp_w,
                bar_position="bottom_continuous",
                concrete_grade=concrete_grade,
                steel_grade=steel_grade,
                source_references=citations_list,
            )

    else:
        # Default Column
        # 1. Search for column longitudinal / main reinforcement
        # Covers:
        # - "Longitudinal reinforcement: 8 bars Ø16 mm"
        # - "4-T16 longitudinal rebar" or "4-T16 main rebar"
        # - "8 bars Ø16 mm"
        # - "4-T16", "6-T20"
        main_long_match = re.search(
            r"(?:longitudinal|main)\s*(?:reinforcement|rebar|bars?|steel)?\s*[:=–—\-]?\s*(?:(?:of)?\s*(\d+)\s*bars?\s*(?:of|dia)?)?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(12|16|20|25|28|32|36|40)\b|"
            r"(\d+)\s*[-]?\s*(?:Y|T|TOR|#|dia|Ø)\s*(12|16|20|25|28|32|36|40)\s*(?:longitudinal|main|rebar|bars?)?|"
            r"(\d+)\s*bars?\s*(?:of|dia)?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(12|16|20|25|28|32|36|40)\b",
            text,
            re.IGNORECASE,
        )
        col_dia: float | None = None
        col_num_bars = 4

        if main_long_match:
            n_raw = main_long_match.group(1) or main_long_match.group(3) or main_long_match.group(5)
            d_raw = main_long_match.group(2) or main_long_match.group(4) or main_long_match.group(6)
            if d_raw:
                col_dia = float(d_raw)
            if n_raw:
                col_num_bars = int(n_raw)
        else:
            # Fallback patterns for column longitudinal bars (minimum 12 mm per IS 456 Cl. 26.5.3.1; ignore 6/8 mm ties)
            rebar_patterns = [
                r"(?:Y|T|TOR|#|dia|Ø)\s*[-]?\s*(12|16|20|25|28|32|36|40)\b",
                r"\b(12|16|20|25|28|32|36|40)\s*(?:mm\s*dia|mm\s*bars?|mm\s*diameter|T\b|#\b|Tor\b|Y\b|Ø\b)",
                r"\b(?:rebar|bar)\s*(?:dia(?:meter)?)?\s*(?:is|=|:)?\s*(12|16|20|25|28|32|36|40)\b",
            ]
            for pattern in rebar_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    col_dia = float(match.group(1))
                    break

            # Longitudinal bar count (e.g. "8 bars Ø16 mm", "8-T16", "4-T16", "6 bars")
            num_bars_match = re.search(
                r"(\d+)\s*(?:bars?\s*(?:of|dia)?\s*)?(?:Y|T|TOR|#|dia|Ø)\s*(?:12|16|20|25|28|32|36|40)\b|"
                r"(\d+)\s*[-]?\s*(?:Y|T|TOR|#|dia|Ø)\s*(?:12|16|20|25|28|32|36|40)\b|"
                r"(?:longitudinal\s*(?:reinforcement|rebar)?|main\s*(?:reinforcement|rebar)?)\s*[:=]?\s*(\d+)\s*bars?",
                text,
                re.IGNORECASE,
            )
            if num_bars_match:
                n_raw = num_bars_match.group(1) or num_bars_match.group(2) or num_bars_match.group(3)
                if n_raw:
                    col_num_bars = int(n_raw)

        if not col_dia:
            missing.append("bar_diameter_mm")
            notes.append("Bar diameter not explicitly found in drawing text.")

        # Storey height extraction
        h_match = re.search(r"(?:storey|floor|clear)?\s*height\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        h_val: float | None = None
        if h_match:
            h_val = float(h_match.group(1))
        else:
            meter_match = re.search(r"(?:storey|floor)?\s*height\s*(?:is|=|:)?\s*(\d(?:\.\d{1,2})?)\s*m\b", text, re.IGNORECASE)
            if meter_match:
                h_val = float(meter_match.group(1)) * 1000.0

        if not h_val:
            missing.append("storey_height_mm")
            notes.append("Storey height could not be confirmed from drawing evidence.")

        col_dims = re.search(r"(\d{3,4})\s*(?:mm)?\s*[xX*×]\s*(\d{3,4})\s*(?:mm)?", text)
        col_w = float(col_dims.group(1)) if col_dims else None
        col_d = float(col_dims.group(2)) if col_dims else None

        # Footing embedment: ONLY if explicitly stated in drawing text
        foot_match = re.search(
            r"(?:footing|foundation)\s*(?:depth|embedment)?\s*(?:is|=|:)?\s*(\d{3,4})\s*mm|"
            r"(?:embedment\s*(?:depth|into\s*footing)?)\s*(?:is|=|:)?\s*(\d{3,4})\s*mm",
            text,
            re.IGNORECASE,
        )
        foot_mm = float(foot_match.group(1) or foot_match.group(2)) if foot_match else 0.0

        # Bend allowance: parse explicit mm, multiplier (e.g. 20d, 20 times the dia), or default to +300 mm
        bend_allowance_val = 0.0
        bend_factor_match = re.search(
            r"(?:bend\s*(?:allowance)?|hook)\s*(?:is|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:times\s*(?:the\s*)?)?(?:dia|d\b|bar\s*dia)",
            text,
            re.IGNORECASE,
        )
        bend_mm_match = re.search(
            r"(?:bend\s*(?:allowance)?|hook)\s*(?:is|=|:)?\s*(\d{2,4})\s*mm",
            text,
            re.IGNORECASE,
        )
        if bend_factor_match and col_dia:
            bend_allowance_val = float(bend_factor_match.group(1)) * col_dia
        elif bend_mm_match:
            bend_allowance_val = float(bend_mm_match.group(1))
        else:
            # Default to +300 mm if nothing is mentioned in drawing
            bend_allowance_val = 300.0

        # Transverse lateral ties / stirrups extraction (e.g. "8mm @ 150 c/c", "T8 @ 150", "8 mm dia ties @ 200 mm", "ties: 8mm @ 150")
        tie_match = re.search(
            r"(?:ties|stirrups|links|lateral\s*ties)?\s*[:=]?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(6|8|10|12)\s*(?:mm)?\s*(?:dia)?\s*[@at]\s*(\d{2,3})\s*(?:c/c|mm\s*c/c|mm\s*spacing)?",
            text,
            re.IGNORECASE,
        )
        tie_simple = re.search(
            r"(?:ties|stirrups|links|lateral\s*ties)\s*[:=]?\s*(?:of|dia)?\s*(?:Y|T|TOR|#|dia|Ø)?\s*(6|8|10|12)\s*mm\b",
            text,
            re.IGNORECASE,
        )
        col_tie_dia = 8.0
        col_tie_spacing = None
        if tie_match and (tie_match.group(1) or tie_match.group(2)):
            if tie_match.group(1):
                col_tie_dia = float(tie_match.group(1))
            if tie_match.group(2):
                col_tie_spacing = float(tie_match.group(2))
        elif tie_simple:
            col_tie_dia = float(tie_simple.group(1))

        # Check for dual-zone / confining end-zone pattern:
        col_tie_end_spacing = None
        col_end_zone_len = None
        col_tie_mid_spacing = None

        end_zone_match = re.search(
            r"(?:end\s*zones?|ends?)\s*[:=–—\-]?\s*(\d{2,3})\s*mm\s*c/c\s*(?:for|upto)\s*(\d{2,4})\s*mm|"
            r"(?:end\s*zones?|ends?)\s*[:=–—\-]?\s*(?:(?:for|upto)\s*)?(\d{2,4})\s*mm\s*(?:at\s*each\s*end)?.*?(\d{2,3})\s*mm\s*c/c",
            text,
            re.IGNORECASE,
        )
        if end_zone_match:
            if end_zone_match.group(1) and end_zone_match.group(2):
                col_tie_end_spacing = float(end_zone_match.group(1))
                col_end_zone_len = float(end_zone_match.group(2))
            elif end_zone_match.group(3) and end_zone_match.group(4):
                col_end_zone_len = float(end_zone_match.group(3))
                col_tie_end_spacing = float(end_zone_match.group(4))

        mid_zone_match = re.search(
            r"(?:middle\s*zone|mid\s*zone|middle|other\s*remaining\s*part|remaining\s*part)\s*[:=–—\-]?\s*(?:stirrups?\s*is\s*at\s*)?(\d{2,3})\s*mm",
            text,
            re.IGNORECASE,
        )
        if mid_zone_match:
            col_tie_mid_spacing = float(mid_zone_match.group(1))

        # Lap requirement: only if explicitly specified or if total length exceeds 12m
        has_lap = bool(re.search(r"\blap\b", text, re.IGNORECASE))

        if col_dia and h_val:
            col_req = ColumnBarRequest(
                member_id=target_member_id,
                bar_diameter_mm=col_dia,
                num_bars=col_num_bars,
                storey_height_mm=h_val,
                column_width_mm=col_w,
                column_depth_mm=col_d,
                footing_embedment_mm=foot_mm,
                top_extension_mm=0.0,
                bend_allowance_mm=bend_allowance_val,
                has_lap_splice=has_lap,
                tie_bar_dia_mm=col_tie_dia,
                tie_spacing_mm=col_tie_spacing,
                tie_spacing_end_mm=col_tie_end_spacing,
                end_zone_length_mm=col_end_zone_len,
                tie_spacing_mid_mm=col_tie_mid_spacing,
                concrete_grade=concrete_grade,
                steel_grade=steel_grade,
                source_references=citations_list,
                use_is_code_rules=True,
                deduct_bends=True,
            )

    confidence = max(0.0, round(1.0 - (0.2 * len(missing)), 2))

    return ExtractionOutput(
        member_id=target_member_id,
        member_type=member_type,
        column_request=col_req,
        beam_request=beam_req,
        footing_request=foot_req,
        slab_request=slab_req,
        pile_request=pile_req,
        pile_cap_request=pc_req,
        staircase_request=stair_req,
        pier_request=pier_req,
        retaining_wall_request=rw_req,
        schedule_rows=sched_rows,
        confidence=confidence,
        extracted_from_pages=sorted(list(set(pages))),
        citations=citations_list,
        missing_fields=missing,
        notes=notes,
    )


def extract_parameters_from_evidence(
    question: str,
    chunks: Sequence[RetrievedChunk],
    member_id: str | None = None,
    member_type: str | None = None,
) -> ExtractionOutput:
    """Extract structural parameters using combined chunk evidence."""
    target_id = (member_id or "UNKNOWN").strip().upper()
    combined_text = "\n".join(c.content for c in chunks)
    citations = [c.source_reference for c in chunks if c.source_reference]
    pages = [c.page_number for c in chunks]

    return regex_extract_drawing_dimensions(
        text=combined_text,
        target_member_id=target_id,
        citations=citations,
        pages=pages,
        specified_member_type=member_type,
    )
