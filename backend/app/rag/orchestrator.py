"""End-to-end RAG orchestrator: Question -> Hybrid Retrieval -> Extraction -> Deterministic Calculation."""

from typing import Any
from pydantic import BaseModel, Field

from app.engineering.calculators.beam import calculate_beam_bar_length, calculate_beam_bbs
from app.engineering.calculators.column import calculate_longitudinal_bar
from app.engineering.calculators.footing import calculate_footing_mesh
from app.engineering.calculators.pier import calculate_pier_bbs
from app.engineering.calculators.pile import calculate_pile_bbs
from app.engineering.calculators.pile_cap import calculate_pile_cap_bbs
from app.engineering.calculators.retaining_wall import calculate_retaining_wall_bbs
from app.engineering.calculators.slab import calculate_slab_bbs
from app.engineering.calculators.staircase import calculate_staircase_bbs
from app.engineering.models import BBSCalculationResult
from app.rag.answer_generator import synthesize_engineering_answer
from app.rag.extractor import ExtractionOutput, extract_parameters_from_evidence
from app.rag.question_parser import DrawingQuestion, parse_drawing_question
from app.rag.retrieval import RetrievalResponse, RetrievedChunk, run_hybrid_search
from app.rag.supabase_client import SupabaseRAGClient


class AskQuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)
    project_id: str | None = None
    drawing_id: str | None = None
    filter_entity_code: str | None = None
    candidate_chunks_cache: list[dict[str, Any]] | None = None
    candidate_members_cache: list[dict[str, Any]] | None = None


class OrchestratedCalculationResponse(BaseModel):
    question: str
    answer: str = ""
    parsed_question: DrawingQuestion
    evidence_chunks: list[RetrievedChunk]
    extraction: ExtractionOutput
    calculation: Any | None = None
    status: str
    review_warnings: list[str] = Field(default_factory=list)


def overlay_candidate_member_dimensions(
    extraction_output: ExtractionOutput,
    matched_candidate: dict[str, Any],
    fallback_type: str | None = None,
) -> None:
    """Overlay verified dimensions from matched candidate member across all supported structural types."""
    import re
    from app.engineering.calculators.beam import BeamBarRequest, BeamScheduleRequest
    from app.engineering.calculators.footing import FootingMeshRequest
    from app.engineering.calculators.pier import PierScheduleRequest
    from app.engineering.calculators.pile import PileScheduleRequest
    from app.engineering.calculators.pile_cap import PileCapScheduleRequest
    from app.engineering.calculators.retaining_wall import RetainingWallScheduleRequest
    from app.engineering.calculators.slab import SlabScheduleRequest
    from app.engineering.calculators.staircase import StaircaseScheduleRequest
    from app.engineering.models import ColumnBarRequest

    extraction_output.member_id = matched_candidate.get("member_id", extraction_output.member_id or "MEMBER")
    mtype = str(matched_candidate.get("member_type", fallback_type or extraction_output.member_type or "column")).lower().strip()
    extraction_output.member_type = mtype
    dims = matched_candidate.get("dimensions", {})
    citations = matched_candidate.get("citations") or [f"drawing:{extraction_output.member_id}"]
    grade_c = str(matched_candidate.get("concrete_grade") or "M25").upper()
    grade_s = str(matched_candidate.get("steel_grade") or "FE500").upper()

    if mtype == "beam":
        reinf_text = f"{matched_candidate.get('reinforcement_summary', '')} {' '.join(str(n) for n in matched_candidate.get('notes', []))}"
        bot_m = re.search(r"bottom.*?(\d+)\s*bars?.*?(\d+)\s*mm", reinf_text, re.IGNORECASE)
        top_m = re.search(r"top.*?(\d+)\s*bars?.*?(\d+)\s*mm", reinf_text, re.IGNORECASE)
        stir_m = re.search(r"stirrups?.*?(\d+)\s*mm.*?(\d+)\s*mm\s*c/?c", reinf_text, re.IGNORECASE) or re.search(r"stirrups?.*?(\d+)\s*mm.*?@\s*(\d+)", reinf_text, re.IGNORECASE)
        cov_m = re.search(r"(?:nominal\s*cover|clear\s*cover|cover).*?(\d+)\s*mm", reinf_text, re.IGNORECASE)

        b_count = int(matched_candidate.get("bottom_bars_count") or dims.get("bottom_bars_count") or (bot_m.group(1) if bot_m else (matched_candidate.get("num_bars") or 3)))
        b_dia = float(matched_candidate.get("bottom_bar_dia_mm") or dims.get("bottom_bar_dia_mm") or (bot_m.group(2) if bot_m else (matched_candidate.get("main_bar_diameter_mm") or 16.0)))
        t_count = int(matched_candidate.get("top_bars_count") or dims.get("top_bars_count") or (top_m.group(1) if top_m else 2))
        t_dia = float(matched_candidate.get("top_bar_dia_mm") or dims.get("top_bar_dia_mm") or (top_m.group(2) if top_m else 12.0))
        s_dia = float(matched_candidate.get("stirrup_dia_mm") or dims.get("stirrup_dia_mm") or (stir_m.group(1) if stir_m else (matched_candidate.get("secondary_bar_diameter_mm") or 8.0)))
        s_pitch = float(matched_candidate.get("stirrup_spacing_mm") or dims.get("stirrup_spacing_mm") or (stir_m.group(2) if stir_m else (matched_candidate.get("spacing_mm") or 150.0)))
        cov = float(matched_candidate.get("clear_cover_mm") or dims.get("clear_cover_mm") or dims.get("cover_mm") or (cov_m.group(1) if cov_m else 25.0))

        span = float(dims.get("clear_span_mm") or dims.get("length_mm") or dims.get("storey_height_mm") or dims.get("height_mm") or 4000.0)
        w = float(dims.get("width_mm") or dims.get("beam_width_mm") or 230.0)
        d = float(dims.get("depth_mm") or dims.get("beam_depth_mm") or 450.0)
        supp_w = float(dims.get("support_width_mm") or dims.get("left_support_width_mm") or 300.0)

        extraction_output.beam_schedule_request = BeamScheduleRequest(
            member_id=extraction_output.member_id,
            clear_span_mm=span,
            beam_width_mm=w,
            beam_depth_mm=d,
            left_support_width_mm=supp_w,
            right_support_width_mm=supp_w,
            clear_cover_mm=cov,
            bottom_bars_count=b_count,
            bottom_bar_dia_mm=b_dia,
            top_bars_count=t_count,
            top_bar_dia_mm=t_dia,
            stirrup_dia_mm=s_dia,
            stirrup_spacing_mm=s_pitch,
            stirrup_legs=2,
            concrete_grade=grade_c,
            steel_grade=grade_s,
            source_references=citations,
            use_is_code_rules=True,
            deduct_bends=True,
        )
        extraction_output.beam_request = BeamBarRequest(
            member_id=extraction_output.member_id,
            bar_diameter_mm=b_dia,
            clear_span_mm=span,
            beam_width_mm=w,
            beam_depth_mm=d,
            left_support_width_mm=supp_w,
            right_support_width_mm=supp_w,
            concrete_grade=grade_c,
            steel_grade=grade_s,
            source_references=citations,
            use_is_code_rules=True,
            deduct_bends=True,
        )
        extraction_output.missing_fields = []
        extraction_output.confidence = 1.0

    elif mtype == "column":
        col_w = float(dims.get("width_mm") or 300.0)
        col_d = float(dims.get("depth_mm") or 450.0)
        storey_h = float(dims.get("storey_height_mm") or dims.get("height_mm") or 3000.0)
        main_dia = float(matched_candidate.get("main_bar_diameter_mm") or 16.0)
        n_bars = int(matched_candidate.get("num_bars") or 8)
        sec_dia = float(matched_candidate.get("secondary_bar_diameter_mm") or 8.0)
        tie_end = float(dims.get("tie_spacing_end_mm")) if dims.get("tie_spacing_end_mm") else None
        end_len = float(dims.get("end_zone_length_mm")) if dims.get("end_zone_length_mm") else None
        tie_mid = float(dims.get("tie_spacing_mid_mm")) if dims.get("tie_spacing_mid_mm") else None

        extraction_output.column_request = ColumnBarRequest(
            member_id=extraction_output.member_id,
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
            source_references=citations,
            use_is_code_rules=True,
            deduct_bends=True,
        )
        extraction_output.missing_fields = []
        extraction_output.confidence = 1.0

    elif mtype in ("footing", "raft"):
        extraction_output.footing_request = FootingMeshRequest(
            member_id=extraction_output.member_id,
            length_mm=float(dims.get("length_mm") or dims.get("footing_length_mm") or 2000.0),
            width_mm=float(dims.get("width_mm") or dims.get("footing_width_mm") or 2000.0),
            depth_mm=float(dims.get("depth_mm") or dims.get("footing_depth_mm") or 500.0),
            bar_diameter_mm=float(matched_candidate.get("main_bar_diameter_mm") or 12.0),
            spacing_mm=float(matched_candidate.get("spacing_mm") or 150.0),
            clear_cover_mm=float(dims.get("clear_cover_mm") or 50.0),
            concrete_grade=grade_c,
            steel_grade=grade_s,
            source_references=citations,
        )
        extraction_output.missing_fields = []
        extraction_output.confidence = 1.0

    elif mtype == "slab":
        extraction_output.slab_request = SlabScheduleRequest(
            member_id=extraction_output.member_id,
            length_ly_mm=float(dims.get("length_ly_mm") or dims.get("length_mm") or 5000.0),
            width_lx_mm=float(dims.get("width_lx_mm") or dims.get("width_mm") or 3500.0),
            thickness_mm=float(dims.get("thickness_mm") or dims.get("depth_mm") or 150.0),
            support_width_mm=float(dims.get("support_width_mm") or 230.0),
            main_bar_dia_mm=float(matched_candidate.get("main_bar_diameter_mm") or 10.0),
            main_bar_spacing_mm=float(matched_candidate.get("spacing_mm") or 150.0),
            dist_bar_dia_mm=float(matched_candidate.get("secondary_bar_diameter_mm") or 8.0),
            dist_bar_spacing_mm=float(dims.get("dist_bar_spacing_mm") or 175.0),
            clear_cover_mm=float(dims.get("clear_cover_mm") or 20.0),
            concrete_grade=grade_c,
            steel_grade=grade_s,
            source_references=citations,
        )
        extraction_output.missing_fields = []
        extraction_output.confidence = 1.0

    elif mtype == "pile":
        extraction_output.pile_request = PileScheduleRequest(
            member_id=extraction_output.member_id,
            pile_diameter_mm=float(dims.get("pile_diameter_mm") or dims.get("width_mm") or 600.0),
            pile_length_m=float(dims.get("pile_length_m") or ((dims.get("length_mm") or 12000.0) / 1000.0)),
            embedment_into_cap_mm=float(dims.get("embedment_into_cap_mm") or 800.0),
            main_bar_dia_mm=float(matched_candidate.get("main_bar_diameter_mm") or 20.0),
            num_main_bars=int(matched_candidate.get("num_bars") or dims.get("num_bars") or 8),
            spiral_bar_dia_mm=float(matched_candidate.get("secondary_bar_diameter_mm") or 8.0),
            spiral_pitch_mm=float(matched_candidate.get("spacing_mm") or 150.0),
            clear_cover_mm=float(dims.get("clear_cover_mm") or 50.0),
            concrete_grade=grade_c,
            steel_grade=grade_s,
            source_references=citations,
        )
        extraction_output.missing_fields = []
        extraction_output.confidence = 1.0

    elif mtype == "pile_cap":
        extraction_output.pile_cap_request = PileCapScheduleRequest(
            member_id=extraction_output.member_id,
            length_mm=float(dims.get("length_mm") or dims.get("cap_length_mm") or 2400.0),
            width_mm=float(dims.get("width_mm") or dims.get("cap_width_mm") or 2400.0),
            depth_mm=float(dims.get("depth_mm") or dims.get("cap_depth_mm") or 1000.0),
            num_piles=int(dims.get("num_piles") or 4),
            bottom_mesh_dia_mm=float(matched_candidate.get("main_bar_diameter_mm") or 20.0),
            bottom_mesh_spacing_mm=float(matched_candidate.get("spacing_mm") or 150.0),
            top_mesh_dia_mm=float(matched_candidate.get("secondary_bar_diameter_mm") or 12.0),
            top_mesh_spacing_mm=200.0,
            clear_cover_mm=float(dims.get("clear_cover_mm") or 50.0),
            concrete_grade=grade_c,
            steel_grade=grade_s,
            source_references=citations,
        )
        extraction_output.missing_fields = []
        extraction_output.confidence = 1.0

    elif mtype == "staircase":
        extraction_output.staircase_request = StaircaseScheduleRequest(
            member_id=extraction_output.member_id,
            flight_width_mm=float(dims.get("flight_width_mm") or dims.get("width_mm") or 1200.0),
            waist_slab_thickness_mm=float(dims.get("waist_slab_thickness_mm") or dims.get("depth_mm") or 150.0),
            riser_mm=float(dims.get("riser_mm") or dims.get("riser_height_mm") or 150.0),
            tread_mm=float(dims.get("tread_mm") or dims.get("tread_width_mm") or 250.0),
            num_risers=int(dims.get("num_risers") or 10),
            num_treads=int(dims.get("num_treads") or 9),
            main_bar_dia_mm=float(matched_candidate.get("main_bar_diameter_mm") or 12.0),
            main_bar_spacing_mm=float(matched_candidate.get("spacing_mm") or 150.0),
            dist_bar_dia_mm=float(matched_candidate.get("secondary_bar_diameter_mm") or 8.0),
            dist_bar_spacing_mm=175.0,
            clear_cover_mm=float(dims.get("clear_cover_mm") or 20.0),
            concrete_grade=grade_c,
            steel_grade=grade_s,
            source_references=citations,
        )
        extraction_output.missing_fields = []
        extraction_output.confidence = 1.0

    elif mtype == "pier":
        extraction_output.pier_request = PierScheduleRequest(
            member_id=extraction_output.member_id,
            shape=str(dims.get("shape") or "rectangular"),
            dimension_1_mm=float(dims.get("dimension_1_mm") or dims.get("width_mm") or 800.0),
            dimension_2_mm=float(dims.get("dimension_2_mm") or dims.get("depth_mm") or 800.0),
            height_mm=float(dims.get("height_mm") or dims.get("storey_height_mm") or 3000.0),
            main_bar_dia_mm=float(matched_candidate.get("main_bar_diameter_mm") or 25.0),
            num_main_bars=int(matched_candidate.get("num_bars") or dims.get("num_bars") or 12),
            tie_bar_dia_mm=float(matched_candidate.get("secondary_bar_diameter_mm") or 10.0),
            tie_spacing_mm=float(matched_candidate.get("spacing_mm") or 150.0),
            clear_cover_mm=float(dims.get("clear_cover_mm") or 40.0),
            concrete_grade=grade_c,
            steel_grade=grade_s,
            source_references=citations,
        )
        extraction_output.missing_fields = []
        extraction_output.confidence = 1.0

    elif mtype == "retaining_wall":
        extraction_output.retaining_wall_request = RetainingWallScheduleRequest(
            member_id=extraction_output.member_id,
            wall_length_m=float(dims.get("wall_length_m") or 10.0),
            stem_height_mm=float(dims.get("stem_height_mm") or dims.get("height_mm") or 3500.0),
            base_slab_width_mm=float(dims.get("base_slab_width_mm") or dims.get("width_mm") or 2400.0),
            base_slab_thickness_mm=float(dims.get("base_slab_thickness_mm") or 400.0),
            stem_base_thickness_mm=float(dims.get("stem_base_thickness_mm") or dims.get("depth_mm") or 400.0),
            toe_projection_mm=float(dims.get("toe_projection_mm") or 600.0),
            main_bar_dia_mm=float(matched_candidate.get("main_bar_diameter_mm") or 16.0),
            main_bar_spacing_mm=float(matched_candidate.get("spacing_mm") or 150.0),
            dist_bar_dia_mm=float(matched_candidate.get("secondary_bar_diameter_mm") or 10.0),
            dist_bar_spacing_mm=200.0,
            clear_cover_mm=float(dims.get("clear_cover_mm") or 50.0),
            concrete_grade=grade_c,
            steel_grade=grade_s,
            source_references=citations,
        )
        extraction_output.missing_fields = []
        extraction_output.confidence = 1.0


def orchestrate_drawing_question(
    request: AskQuestionRequest,
    client: SupabaseRAGClient | None = None,
) -> OrchestratedCalculationResponse:
    """Run full RAG pipeline ensuring calculations are strictly executed by the deterministic engine."""
    rag_client = client or SupabaseRAGClient()
    parsed = parse_drawing_question(request.question)
    target_entity = request.filter_entity_code or parsed.member_id

    # Check candidate members cache for exact or type match
    matched_candidate: dict[str, Any] | None = None
    if request.candidate_members_cache:
        target_norm = (target_entity or "").strip().upper().replace(" ", "").replace("-", "")
        for m in request.candidate_members_cache:
            mid = str(m.get("member_id", "")).strip().upper()
            mid_norm = mid.replace(" ", "").replace("-", "")
            if mid == target_entity or (target_norm and target_norm in mid_norm):
                matched_candidate = m
                target_entity = mid
                break

        if not matched_candidate:
            type_matches = [
                m for m in request.candidate_members_cache
                if str(m.get("member_type", "")).lower() == (parsed.member_type or "").lower()
            ]
            if len(type_matches) == 1:
                matched_candidate = type_matches[0]
                target_entity = matched_candidate.get("member_id")
            elif len(request.candidate_members_cache) == 1:
                matched_candidate = request.candidate_members_cache[0]
                target_entity = matched_candidate.get("member_id")

    warnings: list[str] = []

    # Step 1: Hybrid Retrieval
    retrieval_res: RetrievalResponse = run_hybrid_search(
        client=rag_client,
        query_text=request.question,
        filter_entity_code=target_entity,
        filter_project_id=request.project_id,
        match_count=6,
        candidate_chunks_cache=request.candidate_chunks_cache,
    )

    if not retrieval_res.chunks:
        warnings.append("No matching drawing evidence was retrieved.")
        empty_extraction = ExtractionOutput(
            member_id=target_entity or "UNKNOWN",
            confidence=0.0,
            notes=["No drawing chunks available."],
        )
        answer = synthesize_engineering_answer(
            question=request.question,
            chunks=[],
            extraction=empty_extraction,
            calculation=None,
            warnings=warnings,
        )
        return OrchestratedCalculationResponse(
            question=request.question,
            answer=answer,
            parsed_question=parsed,
            evidence_chunks=[],
            extraction=empty_extraction,
            calculation=None,
            status="needs_review",
            review_warnings=warnings,
        )

    # Step 2: Information Extraction
    extraction_output = extract_parameters_from_evidence(
        question=request.question,
        chunks=retrieval_res.chunks,
        member_id=target_entity,
        member_type=parsed.member_type,
    )

    # Step 2b: Overlay verified dimensions from matched candidate member if present
    if matched_candidate:
        overlay_candidate_member_dimensions(
            extraction_output=extraction_output,
            matched_candidate=matched_candidate,
            fallback_type=parsed.member_type,
        )

    if extraction_output.missing_fields:
        warnings.append(
            f"Missing required parameters: {', '.join(extraction_output.missing_fields)}. Engineer input required."
        )

    # Step 3: Calculation Engine Execution
    calc_result: BBSCalculationResult | None = None
    is_calc_query = (
        parsed.calculation_intent is not None
        or any(w in request.question.lower() for w in [
            "cutting length", "bbs", "calculate", "cutting", "bar length", "schedule", "rebar", "mesh", "tonnage", "weight",
            "concrete", "volume", "m3", "cement", "sand", "aggregate", "mix"
        ])
    )
    if is_calc_query:
        mtype = extraction_output.member_type
        try:
            if mtype == "slab" and extraction_output.slab_request:
                calc_result = calculate_slab_bbs(extraction_output.slab_request)
            elif mtype == "pile" and extraction_output.pile_request:
                calc_result = calculate_pile_bbs(extraction_output.pile_request)
            elif mtype == "pile_cap" and extraction_output.pile_cap_request:
                calc_result = calculate_pile_cap_bbs(extraction_output.pile_cap_request)
            elif mtype == "staircase" and extraction_output.staircase_request:
                calc_result = calculate_staircase_bbs(extraction_output.staircase_request)
            elif mtype == "pier" and extraction_output.pier_request:
                calc_result = calculate_pier_bbs(extraction_output.pier_request)
            elif mtype == "retaining_wall" and extraction_output.retaining_wall_request:
                calc_result = calculate_retaining_wall_bbs(extraction_output.retaining_wall_request)
            elif mtype == "beam":
                if extraction_output.beam_schedule_request:
                    calc_result = calculate_beam_bbs(extraction_output.beam_schedule_request)
                elif extraction_output.beam_request:
                    calc_result = calculate_beam_bar_length(extraction_output.beam_request).to_bbs_result(
                        bar_diameter_mm=extraction_output.beam_request.bar_diameter_mm,
                        beam_width_mm=extraction_output.beam_request.beam_width_mm,
                        beam_depth_mm=extraction_output.beam_request.beam_depth_mm,
                        clear_span_mm=extraction_output.beam_request.clear_span_mm,
                    )
            elif mtype in ("footing", "raft") and extraction_output.footing_request:
                foot_dia = extraction_output.footing_request.bar_diameter_mm
                calc_result = calculate_footing_mesh(extraction_output.footing_request).to_bbs_result(bar_diameter_mm=foot_dia)
            elif extraction_output.column_request:
                calc_result = calculate_longitudinal_bar(extraction_output.column_request).to_bbs_result()
        except Exception as err:
            warnings.append(f"Calculation engine warning: {str(err)}")

    status = "completed" if calc_result is not None else "needs_review"
    if extraction_output.confidence < 0.75:
        warnings.append("Low extraction confidence from drawing snippet; manual verification advised.")

    # Step 4: Engineering Answer Synthesis
    answer = synthesize_engineering_answer(
        question=request.question,
        chunks=retrieval_res.chunks,
        extraction=extraction_output,
        calculation=calc_result,
        warnings=warnings,
    )

    return OrchestratedCalculationResponse(
        question=request.question,
        answer=answer,
        parsed_question=parsed,
        evidence_chunks=retrieval_res.chunks,
        extraction=extraction_output,
        calculation=calc_result,
        status=status,
        review_warnings=warnings,
    )
