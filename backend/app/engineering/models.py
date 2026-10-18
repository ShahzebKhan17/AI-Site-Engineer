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
    clause: str | None = None


class BBSItem(BaseModel):
    bar_mark: str
    bar_type: str = "main"  # "main", "secondary", "distribution", "tie", "spiral", "stiffener", "top_extra"
    bar_diameter_mm: float
    num_bars: int
    spacing_mm: float | None = None
    cutting_length_mm: float
    cutting_length_m: float
    total_length_m: float
    unit_weight_kg_m: float
    total_weight_kg: float
    shape_description: str
    breakdown: list[CalculationBreakdown] = Field(default_factory=list)


from pydantic import BaseModel, Field, computed_field, field_validator


class BBSCalculationResult(BaseModel):
    member_id: str
    member_type: str  # "COLUMN", "BEAM", "FOOTING", "SLAB", "STAIRCASE", "PILE", "PILE_CAP", "PIER", "RETAINING_WALL"
    total_cutting_length_m: float
    total_cutting_length_mm: float = 0.0
    total_weight_kg: float
    items: list[BBSItem]
    assumptions: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    is_code_provisions: dict[str, str | float] | None = None
    engine_version: str = "0.3.0"

    @computed_field
    @property
    def cutting_length_m(self) -> float:
        return self.total_cutting_length_m

    @computed_field
    @property
    def cutting_length_mm(self) -> float:
        return self.total_cutting_length_mm if self.total_cutting_length_mm > 0 else round(self.total_cutting_length_m * 1000.0, 1)

    @computed_field
    @property
    def breakdown(self) -> list[CalculationBreakdown]:
        res: list[CalculationBreakdown] = []
        for it in self.items:
            res.extend(it.breakdown)
        return res


class ColumnBarResult(BaseModel):
    member_id: str
    cutting_length_mm: float
    cutting_length_m: float
    breakdown: list[CalculationBreakdown]
    assumptions: list[str]
    source_references: list[str]
    engine_version: str
    is_code_provisions: dict[str, str | float] | None = None

    def to_bbs_result(self, bar_diameter_mm: float = 16.0, num_bars: int = 4) -> BBSCalculationResult:
        unit_wt = round((bar_diameter_mm ** 2) / 162.0, 3)
        total_len = round(self.cutting_length_m * num_bars, 3)
        total_wt = round(unit_wt * total_len, 2)
        item = BBSItem(
            bar_mark="Main Longitudinal",
            bar_type="main",
            bar_diameter_mm=bar_diameter_mm,
            num_bars=num_bars,
            cutting_length_mm=self.cutting_length_mm,
            cutting_length_m=self.cutting_length_m,
            total_length_m=total_len,
            unit_weight_kg_m=unit_wt,
            total_weight_kg=total_wt,
            shape_description="Straight vertical column bar with 90° footing bend",
            breakdown=self.breakdown,
        )
        return BBSCalculationResult(
            member_id=self.member_id,
            member_type="COLUMN",
            total_cutting_length_m=self.cutting_length_m,
            total_cutting_length_mm=self.cutting_length_mm,
            total_weight_kg=total_wt,
            items=[item],
            assumptions=self.assumptions,
            source_references=self.source_references,
            is_code_provisions=self.is_code_provisions,
            engine_version=self.engine_version,
        )


class DiameterSummary(BaseModel):
    bar_diameter_mm: float
    total_length_m: float
    unit_weight_kg_m: float
    total_weight_kg: float
    total_weight_tonnes: float


class ConsolidatedBBSItem(BaseModel):
    member_id: str
    member_type: str
    bar_mark: str
    bar_type: str
    bar_diameter_mm: float
    num_bars: int
    cutting_length_mm: float
    cutting_length_m: float
    total_length_m: float
    unit_weight_kg_m: float
    total_weight_kg: float
    shape_description: str
    breakdown: list[CalculationBreakdown] = Field(default_factory=list)


class ProjectBBSResponse(BaseModel):
    project_id: str = "Active Project"
    total_members_count: int
    total_steel_kg: float
    total_steel_tonnes: float
    diameter_summaries: list[DiameterSummary]
    items: list[ConsolidatedBBSItem]
    members: list[BBSCalculationResult]
    assumptions: list[str] = Field(default_factory=list)



