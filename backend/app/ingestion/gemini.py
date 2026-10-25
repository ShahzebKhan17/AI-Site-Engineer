"""Multimodal Document & Drawing Extraction via Google Gemini.

Supports high-precision parsing of:
- Vector and scanned civil drawings (.pdf)
- Blueprint photos, site photos, drawing scans (.png, .jpg, .jpeg, .webp)
- Bar bending schedule tables (.csv, .tsv, .txt)

Extracts page-cited evidence chunks for hybrid RAG and structured engineering
parameters (member IDs, dimensions, rebar diameters, spacing, concrete/steel grades)
ready for deterministic IS 456 / SP 34 / IS 2911 calculations.
"""

import base64
import json
import logging
import os
import re
from typing import Any

import httpx

from app.ingestion.models import ExtractedChunk, ExtractedMember, ExtractionResult

logger = logging.getLogger(__name__)

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash"]
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def get_gemini_api_key() -> str | None:
    """Retrieve Gemini API key from environment variables."""
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def is_gemini_available() -> bool:
    """Check if Gemini API key is configured."""
    return bool(get_gemini_api_key())


GEMINI_EXTRACTION_PROMPT = """You are an expert Civil & Structural Engineer AI specialized in reading structural engineering drawings, blueprints, bar bending schedules (BBS), and site photos.

Analyze the attached structural drawing/document carefully and extract:
1. All text chunks for documentation and semantic search retrieval.
2. All identified structural members (e.g. Columns like C1, C12; Beams like B1, B4; Footings/Rafts like F1, RF1, RAFT; Slabs like S1, S2; Piles like P1; Pile Caps like PC1; Piers like PR1; Staircases like ST1; Retaining Walls like RW1).
3. For each member, extract the exact physical dimensions and reinforcement schedule:
   - member_id: e.g. "C12", "B4", "RAFT", "F1", "S1"
   - member_type: one of ["column", "beam", "footing", "slab", "pile", "pile_cap", "pier", "staircase", "retaining_wall"]
   - dimensions: numeric values in millimeters (mm) where visible (e.g. width_mm, depth_mm, length_mm, storey_height_mm, thickness_mm, embedment_mm)
   - main_bar_diameter_mm: primary longitudinal/mesh rebar diameter (e.g. 16, 20, 25, 32)
   - secondary_bar_diameter_mm: secondary/stirrup/tie/distribution rebar diameter (e.g. 8, 10)
   - spacing_mm: center-to-center spacing in mm if applicable (e.g. 150, 200)
   - concrete_grade: e.g. "M25", "M30", "M35", "M40" (default "M25" if not specified)
   - steel_grade: e.g. "FE415", "FE500", "FE550" (default "FE500" if not specified)
   - reinforcement_summary: verbatim string from drawing (e.g. "4-T16 + 4-T20", "Y16 @ 150 c/c Bottom Mesh", "T8 @ 175 c/c links")
   - confidence: float between 0.0 and 1.0 representing extraction certainty
   - citations: list of drawing sheet / page / section references (e.g. ["Sheet S-02", "Column Schedule Table"])
   - notes: list of important notes or warnings (e.g. lap location, cover requirements)

Respond strictly in valid JSON matching this exact structure:
{
  "page_count": 1,
  "chunks": [
    {
      "content": "verbatim text chunk describing the section or schedule",
      "page_number": 1,
      "source_reference": "Sheet 1 / Section A",
      "entity_code": "C12",
      "entity_type": "column"
    }
  ],
  "extracted_members": [
    {
      "member_id": "C12",
      "member_type": "column",
      "dimensions": {
        "width_mm": 400.0,
        "depth_mm": 600.0,
        "storey_height_mm": 3200.0,
        "footing_embedment_mm": 500.0
      },
      "main_bar_diameter_mm": 16.0,
      "secondary_bar_diameter_mm": 8.0,
      "spacing_mm": 150.0,
      "concrete_grade": "M25",
      "steel_grade": "FE500",
      "reinforcement_summary": "4-T16 longitudinal bars, 8mm ties @ 150 c/c",
      "confidence": 0.98,
      "citations": ["Page 1: Column Schedule"],
      "notes": ["Clear cover 40mm specified"]
    }
  ]
}
Do NOT output markdown code blocks (e.g. ```json). Output only raw JSON.
"""


def extract_with_gemini(
    file_bytes: bytes,
    file_name: str,
    mime_type: str = "application/pdf",
    timeout_seconds: float = 45.0,
) -> ExtractionResult:
    """Extract page-cited chunks and engineering parameters using Gemini Multimodal Vision API."""
    api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is not set.")

    b64_data = base64.b64encode(file_bytes).decode("utf-8")

    # Normalize mime type
    normalized_mime = mime_type
    if mime_type in ("image/jpg", "image/jpeg") or file_name.lower().endswith((".jpg", ".jpeg")):
        normalized_mime = "image/jpeg"
    elif mime_type == "image/png" or file_name.lower().endswith(".png"):
        normalized_mime = "image/png"
    elif mime_type == "image/webp" or file_name.lower().endswith(".webp"):
        normalized_mime = "image/webp"
    elif mime_type == "application/pdf" or file_name.lower().endswith(".pdf"):
        normalized_mime = "application/pdf"
    elif mime_type in ("text/csv", "text/plain") or file_name.lower().endswith((".csv", ".tsv", ".txt")):
        normalized_mime = "text/plain"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": normalized_mime,
                            "data": b64_data,
                        }
                    },
                    {
                        "text": GEMINI_EXTRACTION_PROMPT,
                    },
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
        },
    }

    last_error: Exception | None = None
    with httpx.Client(timeout=timeout_seconds) as client:
        for model in GEMINI_MODELS:
            url = f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key}"
            try:
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    candidate = data.get("candidates", [{}])[0]
                    content_parts = candidate.get("content", {}).get("parts", [])
                    raw_text = content_parts[0].get("text", "") if content_parts else ""
                    return _parse_gemini_json_response(raw_text, file_name)
                else:
                    logger.warning(
                        "Gemini model %s returned status %d: %s",
                        model,
                        response.status_code,
                        response.text[:300],
                    )
            except Exception as e:
                last_error = e
                logger.warning("Gemini model %s failed: %s", model, e)
                continue

    raise RuntimeError(f"All Gemini models failed extraction. Last error: {last_error}")


def _parse_gemini_json_response(raw_text: str, file_name: str) -> ExtractionResult:
    """Parse raw LLM response into strongly-typed ExtractionResult model."""
    cleaned = raw_text.strip()
    # Strip markdown formatting if present
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except Exception as err:
        logger.error("Failed to parse JSON from Gemini response: %s. Raw: %s", err, cleaned[:500])
        # Return fallback result
        return ExtractionResult(
            file_name=file_name,
            page_count=1,
            chunks=[
                ExtractedChunk(
                    content=cleaned[:1000] if cleaned else "No text extracted.",
                    page_number=1,
                    chunk_index=0,
                    source_reference=f"drawing:{file_name}#page=1",
                )
            ],
            extracted_members=[],
        )

    page_count = int(parsed.get("page_count", 1))
    raw_chunks = parsed.get("chunks", [])
    raw_members = parsed.get("extracted_members", [])

    chunks: list[ExtractedChunk] = []
    for idx, c in enumerate(raw_chunks):
        p_num = max(1, int(c.get("page_number", 1)))
        source_ref = c.get("source_reference") or f"drawing:{file_name}#page={p_num}"
        chunks.append(
            ExtractedChunk(
                content=str(c.get("content", "")).strip(),
                page_number=p_num,
                chunk_index=idx,
                source_reference=source_ref,
                entity_code=c.get("entity_code"),
                entity_type=c.get("entity_type"),
            )
        )

    # If no chunks were extracted, create at least one from member summaries
    if not chunks and raw_members:
        for idx, m in enumerate(raw_members):
            mid = m.get("member_id", "MEMBER")
            reinf = m.get("reinforcement_summary", "")
            chunks.append(
                ExtractedChunk(
                    content=f"Structural Member {mid}: {reinf}. Grade {m.get('concrete_grade', 'M25')}/{m.get('steel_grade', 'FE500')}",
                    page_number=1,
                    chunk_index=idx,
                    source_reference=f"drawing:{file_name}#page=1",
                    entity_code=mid,
                    entity_type=m.get("member_type"),
                )
            )

    members: list[ExtractedMember] = []
    for m in raw_members:
        mid = str(m.get("member_id", "UNKNOWN")).strip().upper()
        mtype = str(m.get("member_type", "column")).strip().lower()
        dims = {k: float(v) for k, v in m.get("dimensions", {}).items() if v is not None and isinstance(v, (int, float))}
        
        main_dia = float(m["main_bar_diameter_mm"]) if m.get("main_bar_diameter_mm") is not None else None
        sec_dia = float(m["secondary_bar_diameter_mm"]) if m.get("secondary_bar_diameter_mm") is not None else None
        spacing = float(m["spacing_mm"]) if m.get("spacing_mm") is not None else None
        conf = float(m.get("confidence", 0.95))

        members.append(
            ExtractedMember(
                member_id=mid,
                member_type=mtype,
                dimensions=dims,
                main_bar_diameter_mm=main_dia,
                secondary_bar_diameter_mm=sec_dia,
                spacing_mm=spacing,
                concrete_grade=str(m.get("concrete_grade", "M25")).upper(),
                steel_grade=str(m.get("steel_grade", "FE500")).upper(),
                reinforcement_summary=str(m.get("reinforcement_summary", "")),
                confidence=conf,
                citations=m.get("citations", [f"drawing:{file_name}"]),
                notes=m.get("notes", []),
            )
        )

    return ExtractionResult(
        file_name=file_name,
        page_count=max(1, page_count),
        chunks=chunks,
        extracted_members=members,
    )
