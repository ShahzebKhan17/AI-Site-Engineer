"""Footing rebar mesh cutting length and schedule calculator per IS 456:2000 & SP 34:1987."""

from pydantic import BaseModel, Field, field_validator

from app.engineering.models import CalculationBreakdown
from app.engineering.rules.sp34 import calculate_bend_deduction

ENGINE_VERSION = "0.2.0"


class FootingMeshRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)  # e.g. "F1", "F12"
    length_mm: float = Field(gt=0)                       # Footing dimension L in mm
    width_mm: float = Field(gt=0)                        # Footing dimension B in mm
    depth_mm: float = Field(gt=0)                        # Footing depth D in mm
    bar_diameter_mm: float = Field(gt=0, default=12.0)
    spacing_mm: float = Field(gt=0, default=150.0)
    clear_cover_mm: float = Field(ge=25.0, default=50.0) # IS 456 Cl. 26.4.2.2 (min 50mm for footing)
    concrete_grade: str = Field(default="M25")
    steel_grade: str = Field(default="FE500")
    source_references: list[str] = Field(min_length=1)
    deduct_bends: bool = Field(default=True)

    @field_validator("member_id")
    @classmethod
    def normalize_member_id(cls, value: str) -> str:
        return value.strip().upper()


from app.engineering.models import BBSCalculationResult, BBSItem, CalculationBreakdown


class FootingMeshResult(BaseModel):
    member_id: str
    cutting_length_long_mm: float
    cutting_length_short_mm: float
    num_bars_long: int
    num_bars_short: int
    total_mesh_weight_kg: float
    breakdown_long: list[CalculationBreakdown]
    assumptions: list[str]
    source_references: list[str]
    engine_version: str

    def to_bbs_result(self, bar_diameter_mm: float = 12.0) -> BBSCalculationResult:
        unit_wt = round((bar_diameter_mm ** 2) / 162.0, 3)
        cut_long_m = round(self.cutting_length_long_mm / 1000.0, 3)
        cut_short_m = round(self.cutting_length_short_mm / 1000.0, 3)
        tot_long_m = round(cut_long_m * self.num_bars_long, 3)
        tot_short_m = round(cut_short_m * self.num_bars_short, 3)
        item_long = BBSItem(
            bar_mark="Footing Mesh (Long Direction)",
            bar_type="main",
            bar_diameter_mm=bar_diameter_mm,
            num_bars=self.num_bars_long,
            cutting_length_mm=self.cutting_length_long_mm,
            cutting_length_m=cut_long_m,
            total_length_m=tot_long_m,
            unit_weight_kg_m=unit_wt,
            total_weight_kg=round(unit_wt * tot_long_m, 2),
            shape_description="U-shaped bottom mesh bar with vertical 90° end hook legs",
            breakdown=self.breakdown_long,
        )
        item_short = BBSItem(
            bar_mark="Footing Mesh (Short Direction)",
            bar_type="main",
            bar_diameter_mm=bar_diameter_mm,
            num_bars=self.num_bars_short,
            cutting_length_mm=self.cutting_length_short_mm,
            cutting_length_m=cut_short_m,
            total_length_m=tot_short_m,
            unit_weight_kg_m=unit_wt,
            total_weight_kg=round(unit_wt * tot_short_m, 2),
            shape_description="U-shaped bottom mesh bar with vertical 90° end hook legs",
            breakdown=self.breakdown_long,
        )
        return BBSCalculationResult(
            member_id=self.member_id,
            member_type="FOOTING",
            total_cutting_length_m=cut_long_m,
            total_weight_kg=self.total_mesh_weight_kg,
            items=[item_long, item_short],
            assumptions=self.assumptions,
            source_references=self.source_references,
            engine_version=self.engine_version,
        )



def calculate_footing_mesh(request: FootingMeshRequest) -> FootingMeshResult:
    """Calculate Bar Bending Schedule for isolated/raft footing bottom reinforcement mesh.

    Code Provisions:
      - Nominal cover to bottom/sides of footing = 50 mm (IS 456 Cl. 26.4.2.2).
      - Vertical upward bend at ends = (depth - 2 * cover), capped at 300 mm per detailing practice.
      - Standard 2d deduction for each 90-degree bend (SP 34 Cl. 3.2 & IS 2502).
      - Number of bars = int(span / spacing) + 1.
      - Unit weight = d^2 / 162 kg/m.
    """
    cover = request.clear_cover_mm
    bar_dia = request.bar_diameter_mm

    # Straight lengths between side covers
    straight_long = request.length_mm - (2.0 * cover)
    straight_short = request.width_mm - (2.0 * cover)

    # Vertical end bend legs turned upwards
    vert_leg = max(round(request.depth_mm - (2.0 * cover), 1), 150.0)

    # Bend deduction (2 x 90 deg = -4d)
    deduction_mm = calculate_bend_deduction(bar_dia, 90.0).deduction_mm * 2.0 if request.deduct_bends else 0.0

    # Cutting lengths
    cut_long = round(straight_long + (2.0 * vert_leg) - deduction_mm, 1)
    cut_short = round(straight_short + (2.0 * vert_leg) - deduction_mm, 1)

    # Number of bars in each direction
    n_long = int(straight_short / request.spacing_mm) + 1
    n_short = int(straight_long / request.spacing_mm) + 1

    # Total steel weight
    unit_wt = (bar_dia * bar_dia) / 162.0
    total_length_m = ((cut_long * n_long) + (cut_short * n_short)) / 1000.0
    total_weight_kg = round(total_length_m * unit_wt, 2)

    breakdown = [
        CalculationBreakdown(label="Straight bottom span", length_mm=straight_long),
        CalculationBreakdown(label="Left upward vertical leg", length_mm=vert_leg),
        CalculationBreakdown(label="Right upward vertical leg", length_mm=vert_leg),
    ]
    if deduction_mm > 0:
        breakdown.append(CalculationBreakdown(label="Bend deductions (2 x 90 deg: -4d)", length_mm=-deduction_mm))

    assumptions = [
        f"Footing side and bottom nominal cover = {cover} mm per IS 456:2000 Cl. 26.4.2.2.",
        f"Vertical 90-degree end legs ({vert_leg} mm) turned upward to anchor rebar into footing mass.",
        f"Mesh spacing = {request.spacing_mm} mm c/c in both directions.",
        f"Unit steel weight calculated via standard civil code formula d²/162 ({round(unit_wt, 2)} kg/m).",
    ]

    return FootingMeshResult(
        member_id=request.member_id,
        cutting_length_long_mm=cut_long,
        cutting_length_short_mm=cut_short,
        num_bars_long=n_long,
        num_bars_short=n_short,
        total_mesh_weight_kg=total_weight_kg,
        breakdown_long=breakdown,
        assumptions=assumptions,
        source_references=request.source_references,
        engine_version=ENGINE_VERSION,
    )
