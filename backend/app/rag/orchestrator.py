"""End-to-end RAG orchestrator: Question -> Hybrid Retrieval -> Extraction -> Deterministic Calculation."""

from typing import Any
from pydantic import BaseModel, Field

from app.engineering.calculators.column import calculate_longitudinal_bar
from app.engineering.models import ColumnBarResult
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


from app.rag.answer_generator import synthesize_engineering_answer


class OrchestratedCalculationResponse(BaseModel):
    question: str
    answer: str = ""
    parsed_question: DrawingQuestion
    evidence_chunks: list[RetrievedChunk]
    extraction: ExtractionOutput
    calculation: ColumnBarResult | None = None
    status: str
    review_warnings: list[str] = Field(default_factory=list)


def orchestrate_drawing_question(
    request: AskQuestionRequest,
    client: SupabaseRAGClient | None = None,
) -> OrchestratedCalculationResponse:
    """Run full RAG pipeline ensuring calculations are strictly executed by the deterministic engine."""
    rag_client = client or SupabaseRAGClient()
    parsed = parse_drawing_question(request.question)
    target_entity = request.filter_entity_code or parsed.member_id

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
    )

    if extraction_output.missing_fields:
        warnings.append(
            f"Missing required parameters: {', '.join(extraction_output.missing_fields)}. Engineer input required."
        )

    # Step 3: Calculation Engine Execution
    calc_result: ColumnBarResult | None = None
    is_calc_query = (
        parsed.calculation_intent is not None
        or any(w in request.question.lower() for w in ["cutting length", "bbs", "calculate", "cutting", "bar length"])
    )
    if is_calc_query and extraction_output.column_request:
        calc_result = calculate_longitudinal_bar(extraction_output.column_request)

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
