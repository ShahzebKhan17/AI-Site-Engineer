from io import BytesIO

from pypdf import PdfReader

from app.ingestion.models import ExtractedChunk, ExtractionResult


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    """Split text with overlap, preferring natural whitespace boundaries."""
    normalized = " ".join(text.split())
    if not normalized:
        return []
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        overlap_target = max(end - overlap, start + 1)
        prev_boundary = normalized.rfind(" ", start, overlap_target)
        if prev_boundary > start:
            start = prev_boundary + 1
        else:
            start = overlap_target
    return chunks


def detect_entity_in_text(text: str) -> tuple[str | None, str | None]:
    """Identify structural member identifier from text snippet."""
    import re
    # Check multi-letter prefixes first to prevent partial match collisions (e.g. PC before P)
    pile_cap_match = re.search(r"\b(?:pile\s*cap\s*(?:no\.?\s*)?)?(PC\d+)\b", text, re.IGNORECASE)
    if pile_cap_match:
        return pile_cap_match.group(1).upper(), "pile_cap"

    pier_match = re.search(r"\b(?:pier|pedestal)\s*(?:no\.?\s*)?(P[RD]\d+)\b|\b(P[RD]\d+)\b", text, re.IGNORECASE)
    if pier_match:
        code = pier_match.group(1) or pier_match.group(2)
        return code.upper(), "pier"

    stair_match = re.search(r"\b(?:stair(?:case)?\s*(?:no\.?\s*)?)?(S[TC]\d+)\b|\b(S[TC]\d+)\b", text, re.IGNORECASE)
    if stair_match:
        code = stair_match.group(1) or stair_match.group(2)
        return code.upper(), "staircase"

    rw_match = re.search(r"\b(?:retaining\s*wall\s*(?:no\.?\s*)?)?(RW\d+|RET\d+)\b", text, re.IGNORECASE)
    if rw_match:
        return rw_match.group(1).upper(), "retaining_wall"

    column_match = re.search(r"\b(?:column\s*(?:no\.?\s*)?)?(C\d+)\b", text, re.IGNORECASE)
    if column_match:
        return column_match.group(1).upper(), "column"

    beam_match = re.search(r"\b(?:beam\s*(?:no\.?\s*)?)?(B\d+)\b", text, re.IGNORECASE)
    if beam_match:
        return beam_match.group(1).upper(), "beam"

    footing_match = re.search(r"\b(?:footing\s*(?:no\.?\s*)?)?(F\d+)\b", text, re.IGNORECASE)
    if footing_match:
        return footing_match.group(1).upper(), "footing"

    pile_match = re.search(r"\b(?:pile\s*(?:no\.?\s*)?)?(P\d+)\b", text, re.IGNORECASE)
    if pile_match:
        return pile_match.group(1).upper(), "pile"

    slab_match = re.search(r"\b(?:slab\s*(?:no\.?\s*)?)?(S\d+)\b", text, re.IGNORECASE)
    if slab_match:
        return slab_match.group(1).upper(), "slab"

    return None, None



def extract_pdf(file_bytes: bytes, file_name: str) -> ExtractionResult:
    reader = PdfReader(BytesIO(file_bytes))
    chunks: list[ExtractedChunk] = []
    for page_index, page in enumerate(reader.pages):
        page_number = page_index + 1
        for text in chunk_text(page.extract_text() or ""):
            entity_code, entity_type = detect_entity_in_text(text)
            chunks.append(ExtractedChunk(
                content=text,
                page_number=page_number,
                chunk_index=len(chunks),
                source_reference=f"drawing:{file_name}#page={page_number}",
                entity_code=entity_code,
                entity_type=entity_type,
            ))
    return ExtractionResult(file_name=file_name, page_count=len(reader.pages), chunks=chunks)
