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
    confidence: float = Field(ge=0.0, le=1.0)
    extracted_from_pages: list[int] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


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
    if mid.startswith("F"):
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
    if "footing" in lower:
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

    if member_type == "slab":
        lx_match = re.search(r"(?:Lx|short(?:er)?\s*span|width)\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        ly_match = re.search(r"(?:Ly|long(?:er)?\s*span|length)\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        thick_match = re.search(r"(?:thickness|depth|D)\s*(?:is|=|:)?\s*(\d{2,4})\s*mm", text, re.IGNORECASE)
        main_dia_match = re.search(r"(?:main(?:\s*bottom)?(?: reinforcement| rebar)?)\s*[:=]?\s*T(\d+)", text, re.IGNORECASE)
        dist_dia_match = re.search(r"(?:distribution(?: reinforcement| rebar)?)\s*[:=]?\s*T(\d+)", text, re.IGNORECASE)

        lx = float(lx_match.group(1)) if lx_match else 3000.0
        ly = float(ly_match.group(1)) if ly_match else 4500.0
        thick = float(thick_match.group(1)) if thick_match else 150.0
        main_dia = float(main_dia_match.group(1)) if main_dia_match else 10.0
        dist_dia = float(dist_dia_match.group(1)) if dist_dia_match else 8.0

        slab_req = SlabScheduleRequest(
            member_id=target_member_id,
            length_ly_mm=ly,
            width_lx_mm=lx,
            thickness_mm=thick,
            support_width_mm=230.0,
            main_bar_dia_mm=main_dia,
            main_bar_spacing_mm=150.0,
            dist_bar_dia_mm=dist_dia,
            dist_bar_spacing_mm=175.0,
            clear_cover_mm=20.0,
            is_cranked=True,
            concrete_grade=concrete_grade,
            steel_grade=steel_grade,
            source_references=citations_list,
        )

    elif member_type == "pile":
        dia_match = re.search(r"(?:shaft\s*)?diameter\s*(?:is|=|:)?\s*(\d{3,4})\s*mm", text, re.IGNORECASE)
        len_match = re.search(r"(?:depth|length)\s*(?:is|=|:)?\s*(\d+(?:\.\d+)?)\s*m\b", text, re.IGNORECASE)
        vert_rebar_match = re.search(r"(\d+)[- ]?T(\d+)", text, re.IGNORECASE)

        p_dia = float(dia_match.group(1)) if dia_match else 600.0
        p_len = float(len_match.group(1)) if len_match else 12.0
        num_vert = int(vert_rebar_match.group(1)) if vert_rebar_match else 8
        bar_dia = float(vert_rebar_match.group(2)) if vert_rebar_match else 20.0

        pile_req = PileScheduleRequest(
            member_id=target_member_id,
            pile_diameter_mm=p_dia,
            pile_length_m=p_len,
            embedment_into_cap_mm=800.0,
            main_bar_dia_mm=bar_dia,
            num_main_bars=num_vert,
            spiral_bar_dia_mm=8.0,
            spiral_pitch_mm=150.0,
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

        l_val = float(len_match.group(1)) if len_match else 2400.0
        w_val = float(wid_match.group(1)) if wid_match else 2400.0
        d_val = float(depth_match.group(1)) if depth_match else 1000.0
        num_p = int(piles_match.group(1)) if piles_match else 4

        pc_req = PileCapScheduleRequest(
            member_id=target_member_id,
            length_mm=l_val,
            width_mm=w_val,
            depth_mm=d_val,
            num_piles=num_p,
            bottom_mesh_dia_mm=20.0,
            bottom_mesh_spacing_mm=150.0,
            has_top_mesh=True,
            top_mesh_dia_mm=12.0,
            top_mesh_spacing_mm=200.0,
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
        num_r = int(risers_match.group(1)) if risers_match else 10
        r_mm = float(risers_match.group(2)) if risers_match else 150.0
        num_t = int(treads_match.group(1)) if treads_match else 9
        t_mm = float(treads_match.group(2)) if treads_match else 250.0

        stair_req = StaircaseScheduleRequest(
            member_id=target_member_id,
            flight_width_mm=1200.0,
            waist_slab_thickness_mm=150.0,
            riser_mm=r_mm,
            tread_mm=t_mm,
            num_risers=num_r,
            num_treads=num_t,
            bottom_landing_length_mm=1200.0,
            top_landing_length_mm=1200.0,
            main_bar_dia_mm=12.0,
            main_bar_spacing_mm=150.0,
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
        dim1 = float(size_match.group(1)) if size_match else 800.0
        dim2 = float(size_match.group(2)) if size_match else 800.0
        h_val = float(height_match.group(1)) if height_match else 3000.0

        pier_req = PierScheduleRequest(
            member_id=target_member_id,
            shape="rectangular",
            dimension_1_mm=dim1,
            dimension_2_mm=dim2,
            height_mm=h_val,
            starter_embedment_mm=800.0,
            cap_anchorage_mm=800.0,
            main_bar_dia_mm=25.0,
            num_main_bars=12,
            tie_bar_dia_mm=10.0,
            tie_spacing_mm=150.0,
            clear_cover_mm=40.0,
            concrete_grade=concrete_grade,
            steel_grade=steel_grade,
            source_references=citations_list,
        )

    elif member_type == "retaining_wall":
        stem_match = re.search(r"stem\s*height\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        base_match = re.search(r"base\s*slab\s*width\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        h_stem = float(stem_match.group(1)) if stem_match else 3500.0
        b_base = float(base_match.group(1)) if base_match else 2400.0

        rw_req = RetainingWallScheduleRequest(
            member_id=target_member_id,
            wall_length_m=10.0,
            stem_height_mm=h_stem,
            base_slab_width_mm=b_base,
            base_slab_thickness_mm=400.0,
            stem_base_thickness_mm=400.0,
            toe_projection_mm=600.0,
            main_bar_dia_mm=16.0,
            main_bar_spacing_mm=150.0,
            dist_bar_dia_mm=10.0,
            dist_bar_spacing_mm=200.0,
            curtail_alternate_bars=True,
            clear_cover_mm=50.0,
            concrete_grade=concrete_grade,
            steel_grade=steel_grade,
            source_references=citations_list,
        )

    elif member_type == "beam":
        span_match = re.search(r"(?:clear\s*)?span\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
        dia_match = re.search(r"T(12|16|20|25|28|32)", text, re.IGNORECASE)
        span = float(span_match.group(1)) if span_match else 5000.0
        b_dia = float(dia_match.group(1)) if dia_match else 20.0

        beam_req = BeamBarRequest(
            member_id=target_member_id,
            bar_diameter_mm=b_dia,
            clear_span_mm=span,
            left_support_width_mm=300.0,
            right_support_width_mm=300.0,
            bar_position="bottom_continuous",
            concrete_grade=concrete_grade,
            steel_grade=steel_grade,
            source_references=citations_list,
        )

    elif member_type == "footing":
        dims = re.search(r"(\d{3,4})\s*mm\s*x\s*(\d{3,4})\s*mm(?:\s*x\s*(\d{3,4})\s*mm)?", text, re.IGNORECASE)
        l_f = float(dims.group(1)) if dims else 2000.0
        w_f = float(dims.group(2)) if dims else 2000.0
        d_f = float(dims.group(3)) if dims and dims.group(3) else 600.0
        dia_match = re.search(r"T(10|12|16|20)", text, re.IGNORECASE)
        f_dia = float(dia_match.group(1)) if dia_match else 12.0

        foot_req = FootingMeshRequest(
            member_id=target_member_id,
            length_mm=l_f,
            width_mm=w_f,
            depth_mm=d_f,
            bar_diameter_mm=f_dia,
            spacing_mm=150.0,
            clear_cover_mm=50.0,
            concrete_grade=concrete_grade,
            steel_grade=steel_grade,
            source_references=citations_list,
        )

    else:
        # Default Column
        rebar_patterns = [
            r"(?:T|#|Y|Tor|dia(?:meter)?)\s*[-]?\s*(8|10|12|16|20|25|28|32|36|40)\b",
            r"\b(8|10|12|16|20|25|28|32|36|40)\s*(?:mm\s*dia|mm\s*bars?|mm\s*diameter|T\b|#\b|Tor\b)",
            r"\b(?:rebar|bar)\s*(?:dia(?:meter)?)?\s*(?:is|=|:)?\s*(8|10|12|16|20|25|28|32|36|40)\b",
            r"\b(8|10|12|16|20|25|28|32|36|40)\s*mm\b",
        ]
        col_dia: float | None = None
        for pattern in rebar_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                col_dia = float(match.group(1))
                break

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

        foot_match = re.search(r"(?:footing|foundation|embedment)\s*(?:depth|embedment)?\s*(?:is|=|:)?\s*(\d{3,4})\s*mm", text, re.IGNORECASE)
        foot_mm = float(foot_match.group(1)) if foot_match else 0.0

        confidence = 1.0
        if "bar_diameter_mm" in missing:
            confidence -= 0.4
        if "storey_height_mm" in missing:
            confidence -= 0.4

        if col_dia and h_val:
            col_req = ColumnBarRequest(
                member_id=target_member_id,
                bar_diameter_mm=col_dia,
                storey_height_mm=h_val,
                footing_embedment_mm=foot_mm,
                top_extension_mm=0.0,
                concrete_grade=concrete_grade,
                steel_grade=steel_grade,
                source_references=citations_list,
                use_is_code_rules=True,
                deduct_bends=True,
            )


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
    target_id = (member_id or "C12").strip().upper()
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
