"""Structured extraction service mapping drawing evidence snippets into engineering calculation models."""

import os
import re
from typing import Sequence
from pydantic import BaseModel, Field

from app.engineering.models import ColumnBarRequest
from app.rag.retrieval import RetrievedChunk


class ExtractionOutput(BaseModel):
    member_id: str
    column_request: ColumnBarRequest | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    extracted_from_pages: list[int] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def regex_extract_drawing_dimensions(
    text: str,
    target_member_id: str,
    citations: list[str],
    pages: list[int],
) -> ExtractionOutput:
    """Deterministic extractor parsing engineering parameters from drawing schedule text."""
    missing: list[str] = []
    notes: list[str] = []

    # Bar diameter extraction: e.g. "4-T16", "T16", "16mm", "16 mm dia", "dia 16", "#16"
    rebar_patterns = [
        r"(?:T|#|Y|Tor|dia(?:meter)?)\s*[-]?\s*(8|10|12|16|20|25|28|32|36|40)\b",
        r"\b(8|10|12|16|20|25|28|32|36|40)\s*(?:mm\s*dia|mm\s*bars?|mm\s*diameter|T\b|#\b|Tor\b)",
        r"\b(?:rebar|bar)\s*(?:dia(?:meter)?)?\s*(?:is|=|:)?\s*(8|10|12|16|20|25|28|32|36|40)\b",
        r"\b(8|10|12|16|20|25|28|32|36|40)\s*mm\b",
    ]
    bar_dia: float | None = None
    for pattern in rebar_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            bar_dia = float(match.group(1))
            break

    if not bar_dia:
        missing.append("bar_diameter_mm")
        notes.append("Bar diameter not explicitly found in drawing text.")

    # Storey height extraction: e.g. "storey height 3200mm", "height = 3.2m", "3200 mm height", "floor height 3000"
    height_match = re.search(r"(?:storey|floor|clear)?\s*height\s*(?:is|=|:)?\s*(\d{3,5})\s*mm", text, re.IGNORECASE)
    height_mm: float | None = None
    if height_match:
        height_mm = float(height_match.group(1))
    else:
        meter_match = re.search(r"(?:storey|floor)?\s*height\s*(?:is|=|:)?\s*(\d(?:\.\d{1,2})?)\s*m\b", text, re.IGNORECASE)
        if meter_match:
            height_mm = float(meter_match.group(1)) * 1000.0

    if not height_mm:
        # Generic 4-digit dimension likely to be storey height (2700 - 4500 mm)
        generic_height = re.search(r"\b(2700|2800|3000|3200|3300|3500|3600|4000)\s*mm\b", text, re.IGNORECASE)
        if generic_height:
            height_mm = float(generic_height.group(1))

    if not height_mm:
        missing.append("storey_height_mm")
        notes.append("Storey height could not be confirmed from drawing evidence.")

    # Footing embedment: e.g. "footing embedment 500mm", "embedment 600 mm", "foundation depth 500"
    footing_match = re.search(r"(?:footing|foundation|embedment|development\s+in\s+footing)\s*(?:depth|embedment)?\s*(?:is|=|:)?\s*(\d{3,4})\s*mm", text, re.IGNORECASE)
    footing_mm = float(footing_match.group(1)) if footing_match else 0.0

    # Concrete grade: e.g. "M20", "M25", "M30", "M35", "M40"
    concrete_match = re.search(r"\b(M20|M25|M30|M35|M40)\b", text, re.IGNORECASE)
    concrete_grade = concrete_match.group(1).upper() if concrete_match else "M25"
    if not concrete_match:
        notes.append("Concrete grade default M25 assumed.")

    # Steel grade: e.g. "Fe500", "Fe415", "Fe550", "Fe 500"
    steel_match = re.search(r"\b(Fe\s*250|Fe\s*415|Fe\s*500|Fe\s*550)\b", text, re.IGNORECASE)
    steel_grade = steel_match.group(1).replace(" ", "").upper() if steel_match else "FE500"
    if not steel_match:
        notes.append("Steel grade default Fe500 assumed.")

    # Calculate confidence
    confidence = 1.0
    if "bar_diameter_mm" in missing:
        confidence -= 0.4
    if "storey_height_mm" in missing:
        confidence -= 0.4

    req: ColumnBarRequest | None = None
    if bar_dia and height_mm:
        req = ColumnBarRequest(
            member_id=target_member_id,
            bar_diameter_mm=bar_dia,
            storey_height_mm=height_mm,
            footing_embedment_mm=footing_mm,
            top_extension_mm=0.0,
            bend_allowance_mm=0.0,
            lap_length_mm=0.0,
            concrete_grade=concrete_grade,
            steel_grade=steel_grade,
            source_references=citations if citations else ["drawing:evidence#unspecified"],
            use_is_code_rules=True,
            deduct_bends=True,
        )

    return ExtractionOutput(
        member_id=target_member_id,
        column_request=req,
        confidence=max(round(confidence, 2), 0.0),
        extracted_from_pages=sorted(list(set(pages))),
        citations=citations,
        missing_fields=missing,
        notes=notes,
    )


def extract_parameters_from_evidence(
    question: str,
    chunks: Sequence[RetrievedChunk],
    member_id: str | None = None,
) -> ExtractionOutput:
    """Extract structural parameters using combined chunk evidence."""
    target_id = (member_id or "C12").strip().upper()
    combined_text = "\n".join(c.content for c in chunks)
    citations = [c.source_reference for c in chunks if c.source_reference]
    pages = [c.page_number for c in chunks]

    # Deterministic pattern extraction
    output = regex_extract_drawing_dimensions(
        text=combined_text,
        target_member_id=target_id,
        citations=citations,
        pages=pages,
    )

    # Optional OpenAI LLM structured enhancement if API key is provided
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and (output.missing_fields or output.confidence < 0.8):
        try:
            import httpx
            prompt = (
                f"You are a Civil Engineering Drawing Information Extractor.\n"
                f"Extract the dimensions for column {target_id} from this drawing evidence:\n"
                f"\"{combined_text}\"\n"
                f"Extract ONLY json with keys: bar_diameter_mm, storey_height_mm, footing_embedment_mm, concrete_grade, steel_grade. "
                f"Do not compute cutting lengths."
            )
            with httpx.Client(timeout=15.0) as client:
                res = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                    },
                )
                if res.status_code == 200:
                    import json
                    parsed = json.loads(res.json()["choices"][0]["message"]["content"])
                    # Use LLM values to fill in missing fields if valid
                    dia = float(parsed.get("bar_diameter_mm", 0) or 0)
                    h = float(parsed.get("storey_height_mm", 0) or 0)
                    if dia > 0 and h > 0 and output.column_request is None:
                        output.column_request = ColumnBarRequest(
                            member_id=target_id,
                            bar_diameter_mm=dia,
                            storey_height_mm=h,
                            footing_embedment_mm=float(parsed.get("footing_embedment_mm", 0) or 0),
                            top_extension_mm=0.0,
                            concrete_grade=parsed.get("concrete_grade", "M25"),
                            steel_grade=parsed.get("steel_grade", "FE500"),
                            source_references=citations,
                            use_is_code_rules=True,
                            deduct_bends=True,
                        )
                        output.confidence = 0.95
                        output.missing_fields = []
                        output.notes.append("Parameters successfully extracted via LLM structured analysis.")
        except Exception:
            pass

    return output
