from pydantic import BaseModel, Field


class ExtractedChunk(BaseModel):
    content: str
    page_number: int = Field(gt=0)
    chunk_index: int = Field(ge=0)
    source_reference: str
    entity_code: str | None = None
    entity_type: str | None = None
    embedding: list[float] | None = None


class ExtractedMember(BaseModel):
    member_id: str
    member_type: str = "column"
    dimensions: dict[str, float] = Field(default_factory=dict)
    main_bar_diameter_mm: float | None = None
    secondary_bar_diameter_mm: float | None = None
    spacing_mm: float | None = None
    concrete_grade: str = "M25"
    steel_grade: str = "FE500"
    reinforcement_summary: str = ""
    confidence: float = 1.0
    citations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    file_name: str
    page_count: int = Field(ge=0)
    chunks: list[ExtractedChunk]
    extracted_members: list[ExtractedMember] = Field(default_factory=list)

