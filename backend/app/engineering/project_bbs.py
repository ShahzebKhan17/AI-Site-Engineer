"""Consolidated Project Bar Bending Schedule (BBS) and Steel Procurement Aggregator per IS 456 & SP 34."""

from collections import defaultdict
from typing import Any

from app.engineering.calculators.beam import calculate_beam_bar_length
from app.engineering.calculators.column import calculate_longitudinal_bar
from app.engineering.calculators.footing import calculate_footing_mesh
from app.engineering.calculators.pier import calculate_pier_bbs
from app.engineering.calculators.pile import calculate_pile_bbs
from app.engineering.calculators.pile_cap import calculate_pile_cap_bbs
from app.engineering.calculators.retaining_wall import calculate_retaining_wall_bbs
from app.engineering.calculators.slab import calculate_slab_bbs
from app.engineering.calculators.staircase import calculate_staircase_bbs
from app.engineering.models import (
    BBSCalculationResult,
    ConsolidatedBBSItem,
    DiameterSummary,
    ProjectBBSResponse,
)
from app.ingestion.pdf import detect_entity_in_text
from app.rag.extractor import extract_parameters_from_evidence
from app.rag.retrieval import RetrievedChunk
from app.rag.store import get_all_chunks


def generate_consolidated_project_bbs(
    chunks: list[dict[str, Any]] | None = None,
    project_id: str = "Structural Project",
    allow_demo_fallback: bool = False,
    candidate_members_cache: list[dict[str, Any]] | None = None,
) -> ProjectBBSResponse:
    """Scan all project drawing chunks, calculate BBS for each structural member, and aggregate steel tonnage by diameter."""
    if chunks and len(chunks) > 0:
        all_chunks_raw = chunks
    elif allow_demo_fallback:
        all_chunks_raw = get_all_chunks()
    else:
        all_chunks_raw = []

    # Convert raw chunk dicts into RetrievedChunk models
    retrieved_chunks: list[RetrievedChunk] = []
    entity_to_chunks: dict[str, list[RetrievedChunk]] = defaultdict(list)

    for c in all_chunks_raw:
        rc = RetrievedChunk(
            chunk_id=c.get("chunk_id", c.get("id", "chunk")),
            drawing_id=c.get("drawing_id", "drawing.pdf"),
            content=c.get("content", ""),
            page_number=c.get("page_number", 1),
            source_reference=c.get("source_reference", c.get("metadata", {}).get("source_reference", "Drawing Sheet")),
            entity_code=c.get("entity_code"),
            entity_type=c.get("entity_type"),
        )
        retrieved_chunks.append(rc)

        # Detect entity if missing
        ecode = rc.entity_code
        if not ecode or ecode == "GENERAL":
            det_code, _ = detect_entity_in_text(rc.content)
            if det_code:
                ecode = det_code

        if ecode and ecode != "GENERAL":
            entity_to_chunks[ecode.upper().strip()].append(rc)

    # Ensure all candidate members are represented
    if candidate_members_cache:
        for cand in candidate_members_cache:
            cid = str(cand.get("member_id", "")).strip().upper()
            if cid and cid not in entity_to_chunks:
                entity_to_chunks[cid] = retrieved_chunks

    # Fallback to standard baseline members ONLY if explicitly allowed (e.g. Demo Mode)
    if not entity_to_chunks and allow_demo_fallback:
        default_members = ["C12", "B4", "F1", "S1", "P1", "PC1", "ST1", "PR1", "RW1"]
        for m in default_members:
            entity_to_chunks[m] = retrieved_chunks

    # Construction sequencing order: Piles -> Pile Caps -> Footings -> Piers -> Columns -> Beams -> Slabs -> Stairs -> Retaining Walls
    def sort_key(member_id: str) -> int:
        mid = member_id.upper()
        if mid.startswith("P") and not mid.startswith("PC") and not mid.startswith("PR"):
            return 1
        if mid.startswith("PC"):
            return 2
        if mid.startswith("F"):
            return 3
        if mid.startswith("PR") or mid.startswith("PD"):
            return 4
        if mid.startswith("C"):
            return 5
        if mid.startswith("B"):
            return 6
        if mid.startswith("S") and not mid.startswith("ST") and not mid.startswith("SC"):
            return 7
        if mid.startswith("ST") or mid.startswith("SC"):
            return 8
        if mid.startswith("RW") or mid.startswith("RET"):
            return 9
        return 10

    sorted_entities = sorted(entity_to_chunks.keys(), key=sort_key)

    members_results: list[BBSCalculationResult] = []
    consolidated_items: list[ConsolidatedBBSItem] = []

    for entity_id in sorted_entities:
        e_chunks = entity_to_chunks[entity_id]
        extraction = extract_parameters_from_evidence(
            question=f"What is the cutting length and Bar Bending Schedule for {entity_id}?",
            chunks=e_chunks,
            member_id=entity_id,
        )

        # Overlay verified parameters from candidate_members_cache if present
        matched_cand: dict[str, Any] | None = None
        if candidate_members_cache:
            norm_id = entity_id.upper().replace(" ", "").replace("-", "")
            for cand in candidate_members_cache:
                cand_norm = str(cand.get("member_id", "")).upper().replace(" ", "").replace("-", "")
                if cand_norm == norm_id:
                    matched_cand = cand
                    break

        if matched_cand:
            dims = matched_cand.get("dimensions", {})
            mtype = matched_cand.get("member_type", extraction.member_type).lower()
            extraction.member_type = mtype
            if mtype == "column":
                col_w = float(dims.get("width_mm") or 300.0)
                col_d = float(dims.get("depth_mm") or 450.0)
                storey_h = float(dims.get("storey_height_mm") or dims.get("height_mm") or 3000.0)
                main_dia = float(matched_cand.get("main_bar_diameter_mm") or 16.0)
                n_bars = int(matched_cand.get("num_bars") or 8)
                sec_dia = float(matched_cand.get("secondary_bar_diameter_mm") or 8.0)
                grade_c = matched_cand.get("concrete_grade") or "M25"
                grade_s = matched_cand.get("steel_grade") or "FE500"
                tie_end = float(dims.get("tie_spacing_end_mm")) if dims.get("tie_spacing_end_mm") else None
                end_len = float(dims.get("end_zone_length_mm")) if dims.get("end_zone_length_mm") else None
                tie_mid = float(dims.get("tie_spacing_mid_mm")) if dims.get("tie_spacing_mid_mm") else None

                from app.engineering.models import ColumnBarRequest
                extraction.column_request = ColumnBarRequest(
                    member_id=entity_id,
                    bar_diameter_mm=main_dia,
                    num_bars=n_bars,
                    storey_height_mm=storey_h,
                    column_width_mm=col_w,
                    column_depth_mm=col_d,
                    footing_embedment_mm=float(dims.get("footing_embedment_mm") or 0.0),
                    bend_allowance_mm=float(dims.get("bend_allowance_mm") or 300.0),
                    tie_bar_dia_mm=sec_dia,
                    tie_spacing_mm=float(dims.get("spacing_mm") or 150.0),
                    tie_spacing_end_mm=tie_end,
                    end_zone_length_mm=end_len,
                    tie_spacing_mid_mm=tie_mid,
                    concrete_grade=grade_c,
                    steel_grade=grade_s,
                    source_references=matched_cand.get("citations") or [f"drawing:{entity_id}"],
                    use_is_code_rules=True,
                    deduct_bends=True,
                )

        mtype = extraction.member_type
        calc_result: BBSCalculationResult | None = None

        try:
            if mtype == "slab" and extraction.slab_request:
                calc_result = calculate_slab_bbs(extraction.slab_request)
            elif mtype == "pile" and extraction.pile_request:
                calc_result = calculate_pile_bbs(extraction.pile_request)
            elif mtype == "pile_cap" and extraction.pile_cap_request:
                calc_result = calculate_pile_cap_bbs(extraction.pile_cap_request)
            elif mtype == "staircase" and extraction.staircase_request:
                calc_result = calculate_staircase_bbs(extraction.staircase_request)
            elif mtype == "pier" and extraction.pier_request:
                calc_result = calculate_pier_bbs(extraction.pier_request)
            elif mtype == "retaining_wall" and extraction.retaining_wall_request:
                calc_result = calculate_retaining_wall_bbs(extraction.retaining_wall_request)
            elif mtype == "beam" and extraction.beam_request:
                calc_result = calculate_beam_bar_length(extraction.beam_request).to_bbs_result()
            elif mtype == "footing" and extraction.footing_request:
                calc_result = calculate_footing_mesh(extraction.footing_request).to_bbs_result()
            elif extraction.column_request:
                calc_result = calculate_longitudinal_bar(extraction.column_request).to_bbs_result()
        except Exception:
            calc_result = None

        if calc_result:
            members_results.append(calc_result)
            for it in calc_result.items:
                consolidated_items.append(
                    ConsolidatedBBSItem(
                        member_id=calc_result.member_id,
                        member_type=calc_result.member_type,
                        bar_mark=it.bar_mark,
                        bar_type=it.bar_type,
                        bar_diameter_mm=it.bar_diameter_mm,
                        num_bars=it.num_bars,
                        cutting_length_mm=it.cutting_length_mm,
                        cutting_length_m=it.cutting_length_m,
                        total_length_m=it.total_length_m,
                        unit_weight_kg_m=it.unit_weight_kg_m,
                        total_weight_kg=it.total_weight_kg,
                        shape_description=it.shape_description,
                        breakdown=it.breakdown if it.breakdown else calc_result.breakdown,
                    )
                )

    # Group steel by rebar diameter
    diameter_groups: dict[float, list[ConsolidatedBBSItem]] = defaultdict(list)
    for it in consolidated_items:
        diameter_groups[it.bar_diameter_mm].append(it)

    diameter_summaries: list[DiameterSummary] = []
    for dia in sorted(diameter_groups.keys()):
        items_for_dia = diameter_groups[dia]
        total_len = round(sum(i.total_length_m for i in items_for_dia), 2)
        unit_wt = round((dia ** 2) / 162.0, 3)
        total_wt = round(sum(i.total_weight_kg for i in items_for_dia), 2)
        total_tonnes = round(total_wt / 1000.0, 3)
        diameter_summaries.append(
            DiameterSummary(
                bar_diameter_mm=dia,
                total_length_m=total_len,
                unit_weight_kg_m=unit_wt,
                total_weight_kg=total_wt,
                total_weight_tonnes=total_tonnes,
            )
        )

    grand_total_kg = round(sum(d.total_weight_kg for d in diameter_summaries), 2)
    grand_total_tonnes = round(grand_total_kg / 1000.0, 3)

    total_concrete_vol = round(sum(m.concrete_volume_m3 or 0.0 for m in members_results), 3)
    total_dry_vol = round(sum(m.dry_volume_m3 or 0.0 for m in members_results), 3)
    total_cement_bags = round(sum(m.cement_bags or 0.0 for m in members_results), 2)
    total_sand = round(sum(m.sand_m3 or 0.0 for m in members_results), 3)
    total_aggregate = round(sum(m.aggregate_m3 or 0.0 for m in members_results), 3)

    assumptions = [
        "All reinforcement steel conforming to IS 1786 High Yield Strength Deformed (HYSD) Fe500.",
        "Unit steel weights calculated strictly per IS 456 formula: Weight = d² / 162 kg/m.",
        "Standard elongation bend deductions applied per SP 34:1987 Cl. 3.2 & IS 2502 (-2d for 90°, -1d for 45°).",
        "Confinement lap zones and development lengths calculated per IS 456 Cl. 26.2.1 and SP 34 Cl. 7.2.",
        "Concrete material requirements based on dry volume factor 1.54x and IS 456:2000 mix ratios with standard 50 kg cement bags.",
    ]

    return ProjectBBSResponse(
        project_id=project_id,
        total_members_count=len(members_results),
        total_steel_kg=grand_total_kg,
        total_steel_tonnes=grand_total_tonnes,
        total_concrete_volume_m3=total_concrete_vol,
        total_dry_volume_m3=total_dry_vol,
        total_cement_bags=total_cement_bags,
        total_sand_m3=total_sand,
        total_aggregate_m3=total_aggregate,
        diameter_summaries=diameter_summaries,
        items=consolidated_items,
        members=members_results,
        assumptions=assumptions,
    )
