from pydantic import BaseModel, Field


class ExtractedChunk(BaseModel):
    content: str
    page_number: int = Field(gt=0)
    chunk_index: int = Field(ge=0)
    source_reference: str
    entity_code: str | None = None
    entity_type: str | None = None
    embedding: list[float] | None = None


class ExtractionResult(BaseModel):
    file_name: str
    page_count: int = Field(ge=0)
    chunks: list[ExtractedChunk]
