import re

from pydantic import BaseModel


class DrawingQuestion(BaseModel):
    raw_question: str
    member_type: str | None
    member_id: str | None
    calculation_intent: str | None
    needs_clarification: bool


MEMBER_PATTERNS = {
    "column": re.compile(r"\b(?:column\s*(?:no\.?\s*)?)?(C\d+)\b", re.IGNORECASE),
    "beam": re.compile(r"\b(?:beam\s*(?:no\.?\s*)?)?(B\d+)\b", re.IGNORECASE),
    "footing": re.compile(r"\b(?:footing\s*(?:no\.?\s*)?)?(F\d+)\b", re.IGNORECASE),
}


def parse_drawing_question(question: str) -> DrawingQuestion:
    normalized = " ".join(question.split())
    for member_type, pattern in MEMBER_PATTERNS.items():
        match = pattern.search(normalized)
        if match:
            intent = "cutting_length" if re.search(r"\bcutting\s+length\b", normalized, re.IGNORECASE) else None
            return DrawingQuestion(
                raw_question=normalized,
                member_type=member_type,
                member_id=match.group(1).upper(),
                calculation_intent=intent,
                needs_clarification=intent is None,
            )
    return DrawingQuestion(raw_question=normalized, member_type=None, member_id=None, calculation_intent=None, needs_clarification=True)
