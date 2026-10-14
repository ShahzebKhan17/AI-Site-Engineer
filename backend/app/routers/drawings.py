import uuid
from pydantic import BaseModel, Field
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.ingestion.models import ExtractionResult
from app.ingestion.pdf import extract_pdf
from app.rag.supabase_client import SupabaseRAGClient

router = APIRouter(prefix="/drawings", tags=["drawings"])
MAX_PDF_SIZE_BYTES = 25 * 1024 * 1024


class IngestionResponse(BaseModel):
    file_name: str
    page_count: int
    chunks_count: int
    persisted_count: int
    drawing_id: str


@router.post("/extract", response_model=ExtractionResult)
async def extract_drawing(file: UploadFile = File(...)) -> ExtractionResult:
    """Extract page-cited text from a digitally generated PDF drawing."""
    is_pdf = file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only PDF drawings are supported in this phase.")
    contents = await file.read(MAX_PDF_SIZE_BYTES + 1)
    if len(contents) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF must be 25 MB or smaller.")
    try:
        extraction = extract_pdf(contents, file.filename or "drawing.pdf")
        from app.rag.store import add_chunks
        add_chunks(extraction.chunks, drawing_id=file.filename or "uploaded-drawing")
        return extraction
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The PDF could not be read.") from error


@router.post("/ingest", response_model=IngestionResponse)
async def ingest_drawing(
    file: UploadFile = File(...),
    drawing_id: str | None = Query(None, description="Optional Supabase drawing ID"),
) -> IngestionResult if False else IngestionResponse:
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
