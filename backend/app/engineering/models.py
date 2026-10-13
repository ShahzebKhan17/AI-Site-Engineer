from pydantic import BaseModel, Field, field_validator


class ColumnBarRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)
    bar_diameter_mm: float = Field(gt=0)
    storey_height_mm: float = Field(gt=0)
    footing_embedment_mm: float = Field(ge=0)
    top_extension_mm: float = Field(ge=0)
    bend_allowance_mm: float = Field(ge=0, default=0)
    lap_length_mm: float = Field(ge=0, default=0)
    concrete_grade: str = Field(min_length=1)
    steel_grade: str = Field(min_length=1)
    source_references: list[str] = Field(min_length=1)
    use_is_code_rules: bool = Field(default=False)
    deduct_bends: bool = Field(default=False)

    @field_validator("member_id")
    @classmethod
    def normalize_member_id(cls, value: str) -> str:
        return value.strip().upper()


class CalculationBreakdown(BaseModel):
    label: str
    length_mm: float


class ColumnBarResult(BaseModel):
    member_id: str
    cutting_length_mm: float
    cutting_length_m: float
    breakdown: list[CalculationBreakdown]
    assumptions: list[str]
    source_references: list[str]
    engine_version: str
    is_code_provisions: dict[str, str | float] | None = None
