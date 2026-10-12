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
        start = max(end - overlap, start + 1)
    return chunks


def extract_pdf(file_bytes: bytes, file_name: str) -> ExtractionResult:
    reader = PdfReader(BytesIO(file_bytes))
    chunks: list[ExtractedChunk] = []
    for page_index, page in enumerate(reader.pages):
        page_number = page_index + 1
        for text in chunk_text(page.extract_text() or ""):
            chunks.append(ExtractedChunk(
                content=text,
                page_number=page_number,
                chunk_index=len(chunks),
                source_reference=f"drawing:{file_name}#page={page_number}",
            ))
    return ExtractionResult(file_name=file_name, page_count=len(reader.pages), chunks=chunks)
