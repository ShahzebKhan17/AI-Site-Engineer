from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.ingestion.models import ExtractionResult
from app.ingestion.pdf import extract_pdf

router = APIRouter(prefix="/drawings", tags=["drawings"])
MAX_PDF_SIZE_BYTES = 25 * 1024 * 1024


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
        return extract_pdf(contents, file.filename or "drawing.pdf")
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The PDF could not be read.") from error
