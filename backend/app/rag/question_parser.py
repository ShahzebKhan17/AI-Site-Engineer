import re

from pydantic import BaseModel


class DrawingQuestion(BaseModel):
    raw_question: str
    member_type: str | None
    member_id: str | None
    calculation_intent: str | None
    needs_clarification: bool


MEMBER_PATTERNS = {
    "pile_cap": re.compile(r"\b(?:pile\s*cap\s*(?:no\.?\s*)?)?(PC[-\s]?\d+)\b", re.IGNORECASE),
    "pier": re.compile(r"\b(?:pier|pedestal)\s*(?:no\.?\s*)?(P[RD][-\s]?\d+)\b|\b(P[RD][-\s]?\d+)\b", re.IGNORECASE),
    "staircase": re.compile(r"\b(?:stair(?:case)?\s*(?:no\.?\s*)?)?(S[TC][-\s]?\d+)\b|\b(S[TC][-\s]?\d+)\b", re.IGNORECASE),
    "retaining_wall": re.compile(r"\b(?:retaining\s*wall\s*(?:no\.?\s*)?)?(RW[-\s]?\d+|RET[-\s]?\d+)\b", re.IGNORECASE),
    "column": re.compile(r"\b(?:column\s*(?:no\.?\s*)?)?(C[-\s]?\d+)\b", re.IGNORECASE),
    "beam": re.compile(r"\b(?:beam\s*(?:no\.?\s*)?)?(B[-\s]?\d+)\b", re.IGNORECASE),
    "footing": re.compile(
        r"\b(?:raft\s*(?:foundation|footing|slab)?\s*(?:no\.?\s*)?(RF[-\s]?\d+|R[-\s]?\d+)?|isolated\s*footing\s*(?:no\.?\s*)?(F[-\s]?\d+)?|footing\s*(?:no\.?\s*)?(F[-\s]?\d+)?|foundation\s*(?:no\.?\s*)?(F[-\s]?\d+|RF[-\s]?\d+)?|(F[-\s]?\d+)|(RF[-\s]?\d+)|raft)\b",
        re.IGNORECASE,
    ),
    "pile": re.compile(r"\b(?:pile\s*(?:no\.?\s*)?)?(P[-\s]?\d+)\b", re.IGNORECASE),
    "slab": re.compile(r"\b(?:slab\s*(?:no\.?\s*)?)?(S[-\s]?\d+)\b", re.IGNORECASE),
}

GENERIC_MEMBER_PATTERNS = {
    "pile_cap": re.compile(r"\bpile\s*cap\b", re.IGNORECASE),
    "pier": re.compile(r"\b(?:pier|pedestal)\b", re.IGNORECASE),
    "staircase": re.compile(r"\bstair(?:case)?\b", re.IGNORECASE),
    "retaining_wall": re.compile(r"\bretaining\s*wall\b", re.IGNORECASE),
    "column": re.compile(r"\bcolumn\b", re.IGNORECASE),
    "beam": re.compile(r"\bbeam\b", re.IGNORECASE),
    "footing": re.compile(r"\b(?:footing|foundation|raft)\b", re.IGNORECASE),
    "pile": re.compile(r"\bpile\b", re.IGNORECASE),
    "slab": re.compile(r"\bslab\b", re.IGNORECASE),
}


def parse_drawing_question(question: str) -> DrawingQuestion:
    normalized = " ".join(question.split())

    matched_type = None
    extracted_id = ""

    # Phase 1: Explicit member ID matching
    for member_type, pattern in MEMBER_PATTERNS.items():
        match = pattern.search(normalized)
        if match:
            matched_type = member_type
            for g in match.groups():
                if g:
                    extracted_id = g.upper()
                    break
            if not extracted_id:
                if "raft" in normalized.lower():
                    extracted_id = "RAFT"
                elif member_type == "footing" and "foundation" in normalized.lower():
                    extracted_id = "FOUNDATION"
                elif member_type == "footing":
                    extracted_id = "FOOTING"
            break

    # Phase 2: Generic member keyword matching if no specific ID matched
    if not matched_type:
        for member_type, pattern in GENERIC_MEMBER_PATTERNS.items():
            if pattern.search(normalized):
                matched_type = member_type
                if member_type == "footing" and "raft" in normalized.lower():
                    extracted_id = "RAFT"
                else:
                    extracted_id = member_type.upper()
                break

    if matched_type:
        if re.search(r"\b(?:concrete|volume|m3|cubic\s*meters?|cement|bags?|sand|aggregate|water-cement|mix)\b", normalized, re.IGNORECASE):
            intent = "concrete_volume"
        elif re.search(
            r"\b(?:cutting\s+length|bbs|bar\s+bending|schedule|rebar|mesh|reinforcement|steel|tonnage|weight|dia|diameter)\b",
            normalized,
            re.IGNORECASE,
        ):
            intent = "cutting_length"
        else:
            intent = None

        return DrawingQuestion(
            raw_question=normalized,
            member_type=matched_type,
            member_id=extracted_id or None,
            calculation_intent=intent,
            needs_clarification=intent is None,
        )

    return DrawingQuestion(raw_question=normalized, member_type=None, member_id=None, calculation_intent=None, needs_clarification=True)

