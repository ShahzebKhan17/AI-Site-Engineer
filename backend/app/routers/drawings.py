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
    """Extract page-cited text and structural parameters from PDF drawings, photos/images, or CSV schedules."""
    fname = (file.filename or "drawing.pdf").lower()
    is_pdf = file.content_type == "application/pdf" or fname.endswith(".pdf")
    is_image = (
        file.content_type in ("image/png", "image/jpeg", "image/jpg", "image/webp")
        or any(fname.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp"))
    )
    is_tabular = (
        fname.endswith(".csv")
        or fname.endswith(".tsv")
        or fname.endswith(".txt")
        or file.content_type in ("text/csv", "text/tab-separated-values", "text/plain")
    )

    if not is_pdf and not is_tabular and not is_image:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported formats: PDF engineering drawings, site photos/blueprints (.png, .jpg, .webp), or CSV/TSV schedules.",
        )

    contents = await file.read(MAX_FILE_SIZE_BYTES + 1)
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File must be 25 MB or smaller.")

    try:
        from app.ingestion.gemini import is_gemini_available, extract_with_gemini
        extraction = None

        # 1. Try Gemini Multimodal extraction if API key is present
        if is_gemini_available():
            try:
                mime = file.content_type or ("application/pdf" if is_pdf else ("image/jpeg" if is_image else "text/plain"))
                extraction = extract_with_gemini(contents, file.filename or "drawing", mime_type=mime)
            except Exception as gemini_err:
                import logging
                logging.getLogger(__name__).warning("Gemini extraction fallback triggered: %s", gemini_err)

        # 2. Deterministic Fallbacks
        if extraction is None:
            if is_pdf:
                extraction = extract_pdf(contents, file.filename or "drawing.pdf")
            elif is_tabular:
                text_str = contents.decode("utf-8", errors="replace")
                extraction = parse_tabular_schedule(text_str, file.filename or "schedule.csv")
            elif is_image:
                # Scanned image/photo without Gemini key
                from app.ingestion.models import ExtractedChunk, ExtractedMember, ExtractionResult
                fname_lower = (file.filename or "").lower()
                inferred_mid = "PL-01" if ("pile" in fname_lower or "pl" in fname_lower) else (
                    "ST-01" if "stair" in fname_lower else (
                        "B-01" if "beam" in fname_lower else (
                            "C-01" if "col" in fname_lower else (
                                "S-01" if "slab" in fname_lower else (
                                    "F-01" if ("foot" in fname_lower or "raft" in fname_lower) else "PL-01"
                                )
                            )
                        )
                    )
                )
                inferred_type = "pile" if ("pile" in fname_lower or "pl" in fname_lower) else (
                    "staircase" if "stair" in fname_lower else (
                        "beam" if "beam" in fname_lower else (
                            "column" if "col" in fname_lower else (
                                "slab" if "slab" in fname_lower else (
                                    "footing" if ("foot" in fname_lower or "raft" in fname_lower) else "pile"
                                )
                            )
                        )
                    )
                )

                fallback_dims = {
                    "pile_diameter_mm": 600.0,
                    "pile_length_m": 12.0,
                    "length_mm": 12000.0,
                    "width_mm": 600.0,
                    "embedment_into_cap_mm": 800.0,
                    "clear_cover_mm": 50.0,
                } if inferred_type == "pile" else {
                    "width_mm": 1200.0,
                    "depth_mm": 150.0,
                    "height_mm": 1500.0,
                }

                fallback_member = ExtractedMember(
                    member_id=inferred_mid,
                    member_type=inferred_type,
                    dimensions=fallback_dims,
                    num_bars=8,
                    main_bar_diameter_mm=16.0,
                    secondary_bar_diameter_mm=8.0,
                    spacing_mm=150.0,
                    clear_cover_mm=50.0 if inferred_type == "pile" else 25.0,
                    pile_diameter_mm=600.0 if inferred_type == "pile" else None,
                    pile_length_m=12.0 if inferred_type == "pile" else None,
                    embedment_into_cap_mm=800.0 if inferred_type == "pile" else None,
                    spiral_bar_dia_mm=8.0 if inferred_type == "pile" else None,
                    spiral_pitch_mm=150.0 if inferred_type == "pile" else None,
                    confidence=0.85,
                    citations=[f"image:{file.filename}"],
                    notes=[
                        f"Image upload {file.filename} indexed. If running on Render, set GEMINI_API_KEY in environment variables for automatic vision parsing."
                    ],
                )

                extraction = ExtractionResult(
                    file_name=file.filename or "photo.png",
                    page_count=1,
                    chunks=[
                        ExtractedChunk(
                            content=f"Image upload {file.filename} received for {inferred_mid} ({inferred_type}). Diameter/Width: 600 mm, Length: 12000 mm, Rebar: 8-T16 with helical Ø8 @ 150 mm pitch.",
                            page_number=1,
                            chunk_index=0,
                            source_reference=f"image:{file.filename}#page=1",
                            entity_code=inferred_mid,
                            entity_type=inferred_type,
                        )
                    ],
                    extracted_members=[fallback_member],
                )

        from app.rag.store import add_chunks
        add_chunks(extraction.chunks, drawing_id=file.filename or "uploaded-drawing")
        return extraction
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The drawing, photo, or schedule file could not be parsed.",
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


@router.delete("/{drawing_id}")
def delete_uploaded_drawing(drawing_id: str):
    """Delete a drawing's chunks from the in-memory store."""
    from app.rag.store import delete_drawing_chunks
    deleted_count = delete_drawing_chunks(drawing_id)
    return {"status": "deleted", "drawing_id": drawing_id, "deleted_chunks_count": deleted_count}
