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
   - num_bars: total count of primary longitudinal/mesh bars (e.g. 8 for "8 bars Ø16 mm", 4 for "4-T16")
   - dimensions: numeric values in millimeters (mm) where visible (e.g. width_mm, depth_mm, length_mm, storey_height_mm, thickness_mm)
   - footing_embedment_mm: embedment into footing or foundation in mm ONLY if explicitly shown or stated, else 0.0
   - bend_allowance_mm: bend or hook allowance in mm if specified (e.g. 20d or explicit mm), or 300.0 if not specified
   - tie_spacing_end_mm: tie / stirrup spacing in confining / end zones in mm if specified (e.g. 100)
   - end_zone_length_mm: length of confining / end zone at each end in mm if specified (e.g. 300)
   - tie_spacing_mid_mm: tie / stirrup spacing in middle zone in mm if specified (e.g. 150)
   - For STAIRCASE (e.g. ST-01, ST1): extract flight_width_mm, waist_slab_thickness_mm, riser_mm, tread_mm, num_risers, num_treads, has_landings (false if excluded/none, true if present), bottom_landing_length_mm (0 if excluded), top_landing_length_mm (0 if excluded), main_bar_diameter_mm, spacing_mm, secondary_bar_diameter_mm, dist_bar_spacing_mm, clear_cover_mm
   - main_bar_diameter_mm: primary longitudinal/mesh rebar diameter (e.g. 16, 20, 25, 32)
   - secondary_bar_diameter_mm: secondary/stirrup/tie/distribution rebar diameter (e.g. 8, 10)
   - spacing_mm: center-to-center spacing in mm if applicable (e.g. 150, 200)
   - concrete_grade: e.g. "M25", "M30", "M35", "M40" (default "M25" if not specified)
   - steel_grade: e.g. "FE415", "FE500", "FE550" (default "FE500" if not specified)
   - reinforcement_summary: verbatim string from drawing (e.g. "8 bars Ø16 mm, Ø8 mm ties: 100mm end / 150mm mid")
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
      "entity_code": "C-01",
      "entity_type": "column"
    }
  ],
  "extracted_members": [
    {
      "member_id": "C-01",
      "member_type": "column",
      "num_bars": 8,
      "dimensions": {
        "width_mm": 300.0,
        "depth_mm": 450.0,
        "storey_height_mm": 3000.0,
        "footing_embedment_mm": 0.0,
        "bend_allowance_mm": 300.0,
        "tie_spacing_end_mm": 100.0,
        "end_zone_length_mm": 300.0,
        "tie_spacing_mid_mm": 150.0
      },
      "main_bar_diameter_mm": 16.0,
      "secondary_bar_diameter_mm": 8.0,
      "spacing_mm": 150.0,
      "concrete_grade": "M25",
      "steel_grade": "FE500",
      "reinforcement_summary": "8 bars Ø16 mm, Ø8 mm ties: 100mm end / 150mm mid",
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
        
        # Parse or infer num_bars (e.g. from num_bars field or "8 bars Ø16 mm")
        reinf_str = str(m.get("reinforcement_summary", ""))
        num_bars_val = m.get("num_bars") or dims.get("num_bars") or dims.get("num_main_bars")
        if num_bars_val is None and reinf_str:
            nb_match = re.search(r"(\d+)\s*(?:bars?\s*(?:of|dia)?\s*)?(?:Y|T|TOR|#|dia|Ø)\s*\d+|(\d+)\s*[-]?\s*(?:Y|T|TOR|#|dia|Ø)\s*\d+|(\d+)\s*bars?", reinf_str, re.IGNORECASE)
            if nb_match:
                n_raw = nb_match.group(1) or nb_match.group(2) or nb_match.group(3)
                num_bars_val = int(n_raw) if n_raw else None
        
        parsed_num_bars = int(num_bars_val) if num_bars_val is not None else (8 if "8" in reinf_str else 4)
        dims["num_bars"] = parsed_num_bars

        # Default footing embedment to 0.0 if not explicitly supplied
        if "footing_embedment_mm" not in dims:
            dims["footing_embedment_mm"] = 0.0

        # Default bend allowance to 300.0 if not explicitly supplied
        if "bend_allowance_mm" not in dims:
            dims["bend_allowance_mm"] = 300.0

        main_dia = float(m["main_bar_diameter_mm"]) if m.get("main_bar_diameter_mm") is not None else None
        sec_dia = float(m["secondary_bar_diameter_mm"]) if m.get("secondary_bar_diameter_mm") is not None else None
        spacing = float(m["spacing_mm"]) if m.get("spacing_mm") is not None else None
        conf = float(m.get("confidence", 0.95))

        # Beam specific parameter inference from summary or dimensions
        b_count_val = m.get("bottom_bars_count")
        b_dia_val = m.get("bottom_bar_dia_mm")
        t_count_val = m.get("top_bars_count")
        t_dia_val = m.get("top_bar_dia_mm")
        stir_dia_val = m.get("stirrup_dia_mm")
        stir_sp_val = m.get("stirrup_spacing_mm")
        cover_val = m.get("clear_cover_mm") or dims.get("clear_cover_mm") or dims.get("cover_mm")

        comb_reinf = f"{reinf_str} {' '.join(str(n) for n in m.get('notes', []))}"
        if mtype == "beam" or "bottom" in comb_reinf.lower() or "stirrup" in comb_reinf.lower():
            bot_match = re.search(r"bottom.*?(\d+)\s*bars?.*?(\d+)\s*mm", comb_reinf, re.IGNORECASE)
            top_match = re.search(r"top.*?(\d+)\s*bars?.*?(\d+)\s*mm", comb_reinf, re.IGNORECASE)
            stir_match = re.search(r"stirrups?.*?(\d+)\s*mm.*?(\d+)\s*mm\s*c/?c", comb_reinf, re.IGNORECASE) or re.search(r"stirrups?.*?(\d+)\s*mm.*?@\s*(\d+)", comb_reinf, re.IGNORECASE)
            cov_match = re.search(r"(?:clear\s*)?cover.*?(\d+)\s*mm", comb_reinf, re.IGNORECASE)

            if b_count_val is None and bot_match:
                b_count_val = int(bot_match.group(1))
            if b_dia_val is None and bot_match:
                b_dia_val = float(bot_match.group(2))
            if t_count_val is None and top_match:
                t_count_val = int(top_match.group(1))
            if t_dia_val is None and top_match:
                t_dia_val = float(top_match.group(2))
            if stir_dia_val is None and stir_match:
                stir_dia_val = float(stir_match.group(1))
            if stir_sp_val is None and stir_match:
                stir_sp_val = float(stir_match.group(2))
            if cover_val is None and cov_match:
                cover_val = float(cov_match.group(1))

            # Store in dimensions dictionary for easy serialization
            if b_count_val is not None:
                dims["bottom_bars_count"] = float(b_count_val)
            if b_dia_val is not None:
                dims["bottom_bar_dia_mm"] = float(b_dia_val)
            if t_count_val is not None:
                dims["top_bars_count"] = float(t_count_val)
            if t_dia_val is not None:
                dims["top_bar_dia_mm"] = float(t_dia_val)
            if stir_dia_val is not None:
                dims["stirrup_dia_mm"] = float(stir_dia_val)
            if stir_sp_val is not None:
                dims["stirrup_spacing_mm"] = float(stir_sp_val)
            if cover_val is not None:
                dims["clear_cover_mm"] = float(cover_val)

        # Staircase specific parameter inference
        f_width_val = m.get("flight_width_mm") or dims.get("flight_width_mm") or (dims.get("width_mm") if mtype == "staircase" else None)
        waist_th_val = m.get("waist_slab_thickness_mm") or dims.get("waist_slab_thickness_mm") or (dims.get("depth_mm") if mtype == "staircase" else None)
        riser_val = m.get("riser_mm") or dims.get("riser_mm") or dims.get("riser_height_mm")
        tread_val = m.get("tread_mm") or dims.get("tread_mm") or dims.get("tread_width_mm") or dims.get("going_mm")
        num_risers_val = m.get("num_risers") or dims.get("num_risers")
        num_treads_val = m.get("num_treads") or dims.get("num_treads") or dims.get("num_goings")
        has_landings_val = m.get("has_landings") if m.get("has_landings") is not None else dims.get("has_landings")
        bot_land_val = m.get("bottom_landing_length_mm") or dims.get("bottom_landing_length_mm")
        top_land_val = m.get("top_landing_length_mm") or dims.get("top_landing_length_mm")
        dist_sp_val = m.get("dist_bar_spacing_mm") or dims.get("dist_bar_spacing_mm")

        if mtype == "staircase":
            if f_width_val is not None:
                dims["flight_width_mm"] = float(f_width_val)
                dims["width_mm"] = float(f_width_val)
            if waist_th_val is not None:
                dims["waist_slab_thickness_mm"] = float(waist_th_val)
                dims["depth_mm"] = float(waist_th_val)
            if riser_val is not None:
                dims["riser_mm"] = float(riser_val)
            if tread_val is not None:
                dims["tread_mm"] = float(tread_val)
            if num_risers_val is not None:
                dims["num_risers"] = float(num_risers_val)
            if num_treads_val is not None:
                dims["num_treads"] = float(num_treads_val)
            if has_landings_val is not None:
                dims["has_landings"] = 1.0 if has_landings_val else 0.0
            if dist_sp_val is not None:
                dims["dist_bar_spacing_mm"] = float(dist_sp_val)

        members.append(
            ExtractedMember(
                member_id=mid,
                member_type=mtype,
                dimensions=dims,
                num_bars=parsed_num_bars,
                main_bar_diameter_mm=main_dia,
                secondary_bar_diameter_mm=sec_dia,
                spacing_mm=spacing,
                bottom_bars_count=int(b_count_val) if b_count_val is not None else None,
                bottom_bar_dia_mm=float(b_dia_val) if b_dia_val is not None else None,
                top_bars_count=int(t_count_val) if t_count_val is not None else None,
                top_bar_dia_mm=float(t_dia_val) if t_dia_val is not None else None,
                stirrup_dia_mm=float(stir_dia_val) if stir_dia_val is not None else None,
                stirrup_spacing_mm=float(stir_sp_val) if stir_sp_val is not None else None,
                clear_cover_mm=float(cover_val) if cover_val is not None else None,
                flight_width_mm=float(f_width_val) if f_width_val is not None else None,
                waist_slab_thickness_mm=float(waist_th_val) if waist_th_val is not None else None,
                riser_mm=float(riser_val) if riser_val is not None else None,
                tread_mm=float(tread_val) if tread_val is not None else None,
                num_risers=int(num_risers_val) if num_risers_val is not None else None,
                num_treads=int(num_treads_val) if num_treads_val is not None else None,
                has_landings=bool(has_landings_val) if has_landings_val is not None else None,
                bottom_landing_length_mm=float(bot_land_val) if bot_land_val is not None else None,
                top_landing_length_mm=float(top_land_val) if top_land_val is not None else None,
                dist_bar_spacing_mm=float(dist_sp_val) if dist_sp_val is not None else None,
                concrete_grade=str(m.get("concrete_grade", "M25")).upper(),
                steel_grade=str(m.get("steel_grade", "FE500")).upper(),
                reinforcement_summary=reinf_str,
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
