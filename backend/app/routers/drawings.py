import uuid
from pydantic import BaseModel, Field
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.ingestion.models import ExtractionResult
from app.ingestion.pdf import extract_pdf
from app.ingestion.tabular import parse_tabular_schedule
from app.rag.supabase_client import SupabaseRAGClient

router = APIRouter(prefix="/drawings", tags=["drawings"])
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024


class IngestionResponse(BaseModel):
    file_name: str
    page_count: int
    chunks_count: int
    persisted_count: int
    drawing_id: str


@router.post("/extract", response_model=ExtractionResult)
async def extract_drawing(file: UploadFile = File(...)) -> ExtractionResult:
    """Extract page-cited text from a digitally generated PDF drawing or CSV schedule."""
    fname = (file.filename or "drawing.pdf").lower()
    is_pdf = file.content_type == "application/pdf" or fname.endswith(".pdf")
    is_tabular = fname.endswith(".csv") or fname.endswith(".tsv") or fname.endswith(".txt") or file.content_type in ("text/csv", "text/tab-separated-values", "text/plain")

    if not is_pdf and not is_tabular:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported formats: PDF engineering drawings or CSV/TSV structural bar schedules.",
        )

    contents = await file.read(MAX_FILE_SIZE_BYTES + 1)
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File must be 25 MB or smaller.")

    try:
        if is_pdf:
            extraction = extract_pdf(contents, file.filename or "drawing.pdf")
        else:
            text_str = contents.decode("utf-8", errors="replace")
            extraction = parse_tabular_schedule(text_str, file.filename or "schedule.csv")

        from app.rag.store import add_chunks
        add_chunks(extraction.chunks, drawing_id=file.filename or "uploaded-drawing")
        return extraction
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The drawing or schedule file could not be parsed.",
        ) from error


@router.post("/ingest", response_model=IngestionResponse)
async def ingest_drawing(
    file: UploadFile = File(...),
    drawing_id: str | None = Query(None, description="Optional Supabase drawing ID"),
) -> IngestionResponse:
    """Extract, embed (1536-dim), and persist drawing chunks to Supabase document_chunks."""
    extraction = await extract_drawing(file)
    effective_drawing_id = drawing_id or str(uuid.uuid4())

    rag_client = SupabaseRAGClient()
    persisted = rag_client.persist_chunks(
        drawing_id=effective_drawing_id,
        chunks=extraction.chunks,
        generate_missing_embeddings=True,
    )

    return IngestionResponse(
        file_name=extraction.file_name,
        page_count=extraction.page_count,
        chunks_count=len(extraction.chunks),
        persisted_count=len(persisted),
        drawing_id=effective_drawing_id,
    )
