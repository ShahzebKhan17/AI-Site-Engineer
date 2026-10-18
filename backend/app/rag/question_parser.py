import re

from pydantic import BaseModel


class DrawingQuestion(BaseModel):
    raw_question: str
    member_type: str | None
    member_id: str | None
    calculation_intent: str | None
    needs_clarification: bool


MEMBER_PATTERNS = {
    "pile_cap": re.compile(r"\b(?:pile\s*cap\s*(?:no\.?\s*)?)?(PC\d+)\b", re.IGNORECASE),
    "pier": re.compile(r"\b(?:pier|pedestal)\s*(?:no\.?\s*)?(P[RD]\d+)\b|\b(P[RD]\d+)\b", re.IGNORECASE),
    "staircase": re.compile(r"\b(?:stair(?:case)?\s*(?:no\.?\s*)?)?(S[TC]\d+)\b|\b(S[TC]\d+)\b", re.IGNORECASE),
    "retaining_wall": re.compile(r"\b(?:retaining\s*wall\s*(?:no\.?\s*)?)?(RW\d+|RET\d+)\b", re.IGNORECASE),
    "column": re.compile(r"\b(?:column\s*(?:no\.?\s*)?)?(C\d+)\b", re.IGNORECASE),
    "beam": re.compile(r"\b(?:beam\s*(?:no\.?\s*)?)?(B\d+)\b", re.IGNORECASE),
    "footing": re.compile(r"\b(?:footing\s*(?:no\.?\s*)?)?(F\d+)\b", re.IGNORECASE),
    "pile": re.compile(r"\b(?:pile\s*(?:no\.?\s*)?)?(P\d+)\b", re.IGNORECASE),
    "slab": re.compile(r"\b(?:slab\s*(?:no\.?\s*)?)?(S\d+)\b", re.IGNORECASE),
}


def parse_drawing_question(question: str) -> DrawingQuestion:
    normalized = " ".join(question.split())
    for member_type, pattern in MEMBER_PATTERNS.items():
        match = pattern.search(normalized)
        if match:
            extracted_id = (match.group(1) or (match.group(2) if match.lastindex and match.lastindex >= 2 else None) or "").upper()
            intent = "cutting_length" if re.search(
                r"\b(?:cutting\s+length|bbs|bar\s+bending|schedule|rebar|mesh|reinforcement|steel|tonnage|weight)\b",
                normalized,
                re.IGNORECASE,
            ) else None
            return DrawingQuestion(
                raw_question=normalized,
                member_type=member_type,
                member_id=extracted_id,
                calculation_intent=intent,
                needs_clarification=intent is None,
            )
    return DrawingQuestion(raw_question=normalized, member_type=None, member_id=None, calculation_intent=None, needs_clarification=True)

