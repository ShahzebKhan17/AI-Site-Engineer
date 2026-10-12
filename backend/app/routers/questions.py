from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.rag.question_parser import DrawingQuestion, parse_drawing_question

router = APIRouter(prefix="/questions", tags=["questions"])


class ParseQuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)


@router.post("/parse", response_model=DrawingQuestion)
def parse_question(request: ParseQuestionRequest) -> DrawingQuestion:
    return parse_drawing_question(request.question)
