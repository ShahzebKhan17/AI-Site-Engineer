from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.rag.orchestrator import (
    AskQuestionRequest,
    OrchestratedCalculationResponse,
    orchestrate_drawing_question,
)
from app.rag.question_parser import DrawingQuestion, parse_drawing_question
from app.rag.retrieval import RetrievalRequest, RetrievalResponse
from app.rag.supabase_client import SupabaseRAGClient

router = APIRouter(prefix="/questions", tags=["questions"])


class ParseQuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)


@router.post("/parse", response_model=DrawingQuestion)
def parse_question(request: ParseQuestionRequest) -> DrawingQuestion:
    return parse_drawing_question(request.question)


@router.post("/search", response_model=RetrievalResponse)
def search_drawing_evidence(request: RetrievalRequest) -> RetrievalResponse:
    """Retrieve drawing chunks using hybrid search (pgvector + full-text + entity code boost)."""
    parsed = parse_drawing_question(request.query_text)
    entity_filter = request.filter_entity_code or parsed.member_id
    client = SupabaseRAGClient()
    return client.hybrid_search(
        query_text=request.query_text,
        filter_entity_code=entity_filter,
        filter_project_id=request.filter_project_id,
        match_count=request.match_count,
    )


@router.post("/ask", response_model=OrchestratedCalculationResponse)
def ask_question_and_calculate(request: AskQuestionRequest) -> OrchestratedCalculationResponse:
    """End-to-end question processing: parse intent, retrieve drawing chunks, extract parameters, and execute IS 456 calculator."""
    return orchestrate_drawing_question(request)
