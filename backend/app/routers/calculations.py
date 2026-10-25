from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.engineering.calculators.beam import BeamBarRequest, BeamBarResult, calculate_beam_bar_length
from app.engineering.calculators.column import calculate_longitudinal_bar
from app.engineering.calculators.footing import FootingMeshRequest, FootingMeshResult, calculate_footing_mesh
from app.engineering.calculators.pier import PierScheduleRequest, calculate_pier_bbs
from app.engineering.calculators.pile import PileScheduleRequest, calculate_pile_bbs
from app.engineering.calculators.pile_cap import PileCapScheduleRequest, calculate_pile_cap_bbs
from app.engineering.calculators.retaining_wall import RetainingWallScheduleRequest, calculate_retaining_wall_bbs
from app.engineering.calculators.slab import SlabScheduleRequest, calculate_slab_bbs
from app.engineering.calculators.staircase import StaircaseScheduleRequest, calculate_staircase_bbs
from app.engineering.calculators.concrete import (
    ConcreteCalculationResult,
    calculate_member_concrete_volume,
)
from app.engineering.models import BBSCalculationResult, ColumnBarRequest, ColumnBarResult, ProjectBBSResponse
from app.engineering.optimization import (
    ProcurementOrderRequisition,
    optimize_cutting_stock,
)
from app.engineering.project_bbs import generate_consolidated_project_bbs
from app.engineering.qa_qc import QAAuditCertificate, create_qa_audit_certificate

router = APIRouter(prefix="/calculations", tags=["calculations"])


@router.post("/column-longitudinal-bar", response_model=ColumnBarResult)
def calculate_column_longitudinal_bar(request: ColumnBarRequest) -> ColumnBarResult:
    """Run deterministic arithmetic over reviewed column drawing inputs."""
    return calculate_longitudinal_bar(request)


@router.post("/beam-bar", response_model=BeamBarResult)
def calculate_beam_bar(request: BeamBarRequest) -> BeamBarResult:
    """Run deterministic BBS calculation over reviewed beam drawing inputs per IS 456 & SP 34."""
    return calculate_beam_bar_length(request)


@router.post("/footing-mesh", response_model=FootingMeshResult)
def calculate_footing_mesh_reinforcement(request: FootingMeshRequest) -> FootingMeshResult:
    """Run deterministic BBS calculation for isolated/raft footing rebar mesh per IS 456 Cl. 34."""
    return calculate_footing_mesh(request)


@router.post("/slab", response_model=BBSCalculationResult)
def calculate_slab(request: SlabScheduleRequest) -> BBSCalculationResult:
    """Run deterministic BBS calculation for RC slabs (one-way / two-way) per IS 456 & SP 34."""
    return calculate_slab_bbs(request)


@router.post("/pile", response_model=BBSCalculationResult)
def calculate_pile(request: PileScheduleRequest) -> BBSCalculationResult:
    """Run deterministic BBS calculation for RC piles with cage and spiral links per IS 2911."""
    return calculate_pile_bbs(request)


@router.post("/pile-cap", response_model=BBSCalculationResult)
def calculate_pile_cap(request: PileCapScheduleRequest) -> BBSCalculationResult:
    """Run deterministic BBS calculation for pile caps and starter dowels per IS 2911 & IS 456."""
    return calculate_pile_cap_bbs(request)


@router.post("/staircase", response_model=BBSCalculationResult)
def calculate_staircase(request: StaircaseScheduleRequest) -> BBSCalculationResult:
    """Run deterministic BBS calculation for staircase waist flight and landings per IS 456 & SP 34."""
    return calculate_staircase_bbs(request)


@router.post("/pier", response_model=BBSCalculationResult)
def calculate_pier(request: PierScheduleRequest) -> BBSCalculationResult:
    """Run deterministic BBS calculation for bridge piers and pedestals per IS 456 & IRC:112."""
    return calculate_pier_bbs(request)


@router.post("/retaining-wall", response_model=BBSCalculationResult)
def calculate_retaining_wall(request: RetainingWallScheduleRequest) -> BBSCalculationResult:
    """Run deterministic BBS calculation for cantilever retaining wall per IS 456 & SP 34."""
    return calculate_retaining_wall_bbs(request)


class ConcreteVolumeRequest(BaseModel):
    member_type: str = Field(default="column", description="Structural member type: column, beam, footing, slab, pile, pile_cap, pier, retaining_wall, staircase")
    member_id: str = Field(default="M1", description="Identifier of the member")
    concrete_grade: str = Field(default="M25", description="Grade of concrete: M15, M20, M25, M30, M35, M40")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Dimensions dictionary")


@router.post("/concrete-volume", response_model=ConcreteCalculationResult)
def calculate_concrete(request: ConcreteVolumeRequest) -> ConcreteCalculationResult:
    """Calculate exact concrete volume (m³) and IS 456 material breakdown (cement bags, sand, aggregate, water)."""
    return calculate_member_concrete_volume(
        member_type=request.member_type,
        member_id=request.member_id,
        concrete_grade=request.concrete_grade,
        params=request.parameters,
    )


class ParameterCalculationRequest(BaseModel):
    member_id: str
    member_type: str = "column"  # column, beam, footing, slab, pile, pile_cap, pier, staircase, retaining_wall
    dimensions: dict[str, float] = Field(default_factory=dict)
    main_bar_diameter_mm: float = 16.0
    secondary_bar_diameter_mm: float | None = 8.0
    spacing_mm: float | None = 150.0
    concrete_grade: str = "M25"
    steel_grade: str = "FE500"
    citations: list[str] = Field(default_factory=list)


@router.post("/calculate-from-parameters", response_model=Any)
def calculate_from_reviewed_parameters(request: ParameterCalculationRequest) -> Any:
    """Execute deterministic calculation over engineer-reviewed parameters."""
    mtype = request.member_type.lower()
    dims = request.dimensions
    citations = request.citations or [f"drawing:reviewed_member#{request.member_id}"]

    if mtype == "column":
        col_req = ColumnBarRequest(
            member_id=request.member_id,
            bar_diameter_mm=request.main_bar_diameter_mm,
            storey_height_mm=dims.get("storey_height_mm", 3200.0),
            column_width_mm=dims.get("width_mm", 400.0),
            column_depth_mm=dims.get("depth_mm", 600.0),
            footing_embedment_mm=dims.get("footing_embedment_mm", 500.0),
            top_extension_mm=dims.get("top_extension_mm", 0.0),
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            source_references=citations,
            use_is_code_rules=True,
            deduct_bends=True,
        )
        return calculate_longitudinal_bar(col_req)

    if mtype == "beam":
        beam_req = BeamBarRequest(
            member_id=request.member_id,
            bar_diameter_mm=request.main_bar_diameter_mm,
            clear_span_mm=dims.get("length_mm", dims.get("clear_span_mm", 4000.0)),
            beam_width_mm=dims.get("width_mm", 300.0),
            beam_depth_mm=dims.get("depth_mm", 500.0),
            support_width_mm=dims.get("support_width_mm", 300.0),
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            source_references=citations,
            deduct_bends=True,
        )
        return calculate_beam_bar_length(beam_req)

    if mtype in ("footing", "raft"):
        foot_req = FootingMeshRequest(
            member_id=request.member_id,
            bar_diameter_mm=request.main_bar_diameter_mm,
            footing_length_mm=dims.get("length_mm", dims.get("footing_length_mm", 2000.0)),
            footing_width_mm=dims.get("width_mm", dims.get("footing_width_mm", 2000.0)),
            footing_depth_mm=dims.get("depth_mm", dims.get("footing_depth_mm", 500.0)),
            spacing_mm=request.spacing_mm or 150.0,
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            source_references=citations,
        )
        return calculate_footing_mesh(foot_req)

    if mtype == "slab":
        slab_req = SlabScheduleRequest(
            member_id=request.member_id,
            short_span_mm=dims.get("width_mm", dims.get("short_span_mm", 3500.0)),
            long_span_mm=dims.get("length_mm", dims.get("long_span_mm", 5000.0)),
            slab_thickness_mm=dims.get("depth_mm", dims.get("slab_thickness_mm", 150.0)),
            main_bar_dia_mm=request.main_bar_diameter_mm,
            main_bar_spacing_mm=request.spacing_mm or 150.0,
            distribution_bar_dia_mm=request.secondary_bar_diameter_mm or 8.0,
            distribution_bar_spacing_mm=dims.get("distribution_spacing_mm", 200.0),
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            source_references=citations,
        )
        return calculate_slab_bbs(slab_req)

    if mtype == "pile":
        pile_req = PileScheduleRequest(
            member_id=request.member_id,
            pile_diameter_mm=dims.get("width_mm", dims.get("pile_diameter_mm", 600.0)),
            pile_length_m=dims.get("length_mm", dims.get("pile_length_mm", 15000.0)) / 1000.0,
            longitudinal_bars_count=int(dims.get("bars_count", 6)),
            longitudinal_bar_dia_mm=request.main_bar_diameter_mm,
            spiral_bar_dia_mm=request.secondary_bar_diameter_mm or 8.0,
            spiral_pitch_mm=request.spacing_mm or 150.0,
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            source_references=citations,
        )
        return calculate_pile_bbs(pile_req)

    if mtype == "pile_cap":
        pc_req = PileCapScheduleRequest(
            member_id=request.member_id,
            cap_length_mm=dims.get("length_mm", dims.get("cap_length_mm", 2500.0)),
            cap_width_mm=dims.get("width_mm", dims.get("cap_width_mm", 2500.0)),
            cap_depth_mm=dims.get("depth_mm", dims.get("cap_depth_mm", 900.0)),
            main_bar_dia_mm=request.main_bar_diameter_mm,
            main_bar_spacing_mm=request.spacing_mm or 150.0,
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            source_references=citations,
        )
        return calculate_pile_cap_bbs(pc_req)

    if mtype == "pier":
        pier_req = PierScheduleRequest(
            member_id=request.member_id,
            pier_width_mm=dims.get("width_mm", dims.get("pier_width_mm", 800.0)),
            pier_depth_mm=dims.get("depth_mm", dims.get("pier_depth_mm", 1200.0)),
            pier_height_mm=dims.get("storey_height_mm", dims.get("pier_height_mm", 6000.0)),
            longitudinal_bar_dia_mm=request.main_bar_diameter_mm,
            longitudinal_bars_count=int(dims.get("bars_count", 12)),
            tie_bar_dia_mm=request.secondary_bar_diameter_mm or 10.0,
            tie_spacing_mm=request.spacing_mm or 150.0,
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            source_references=citations,
        )
        return calculate_pier_bbs(pier_req)

    if mtype == "staircase":
        stair_req = StaircaseScheduleRequest(
            member_id=request.member_id,
            waist_slab_thickness_mm=dims.get("depth_mm", dims.get("waist_slab_thickness_mm", 150.0)),
            going_length_mm=dims.get("length_mm", dims.get("going_length_mm", 3000.0)),
            riser_height_mm=dims.get("riser_height_mm", 150.0),
            tread_width_mm=dims.get("tread_width_mm", 300.0),
            main_bar_dia_mm=request.main_bar_diameter_mm,
            main_bar_spacing_mm=request.spacing_mm or 150.0,
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            source_references=citations,
        )
        return calculate_staircase_bbs(stair_req)

    if mtype == "retaining_wall":
        rw_req = RetainingWallScheduleRequest(
            member_id=request.member_id,
            stem_height_mm=dims.get("storey_height_mm", dims.get("stem_height_mm", 4000.0)),
            stem_base_thickness_mm=dims.get("depth_mm", dims.get("stem_base_thickness_mm", 400.0)),
            stem_top_thickness_mm=dims.get("width_mm", dims.get("stem_top_thickness_mm", 200.0)),
            vertical_bar_dia_mm=request.main_bar_diameter_mm,
            vertical_bar_spacing_mm=request.spacing_mm or 150.0,
            concrete_grade=request.concrete_grade,
            steel_grade=request.steel_grade,
            source_references=citations,
        )
        return calculate_retaining_wall_bbs(rw_req)

    # Fallback to column
    col_req = ColumnBarRequest(
        member_id=request.member_id,
        bar_diameter_mm=request.main_bar_diameter_mm,
        storey_height_mm=dims.get("storey_height_mm", 3200.0),
        column_width_mm=dims.get("width_mm", 400.0),
        column_depth_mm=dims.get("depth_mm", 600.0),
        concrete_grade=request.concrete_grade,
        steel_grade=request.steel_grade,
        source_references=citations,
    )
    return calculate_longitudinal_bar(col_req)



class ProjectBBSRequest(BaseModel):
    project_id: str = "Structural Project"
    candidate_chunks_cache: list[dict[str, Any]] | None = None


@router.post("/project-bbs", response_model=ProjectBBSResponse)
def get_project_bbs(request: ProjectBBSRequest | None = None) -> ProjectBBSResponse:
    """Generate consolidated multi-member Bar Bending Schedule and procurement steel breakdown."""
    chunks = request.candidate_chunks_cache if request else None
    proj_id = request.project_id if request else "Structural Project"
    return generate_consolidated_project_bbs(chunks=chunks, project_id=proj_id)


class OptimizationRequest(BaseModel):
    project_id: str = "Structural Project"
    items: list[dict[str, Any]] | None = None
    candidate_chunks_cache: list[dict[str, Any]] | None = None


@router.post("/optimize-cutting", response_model=ProcurementOrderRequisition)
def optimize_rebar_cutting_patterns(request: OptimizationRequest | None = None) -> ProcurementOrderRequisition:
    """Run 1D Cutting Stock optimization to pack required bar pieces into standard 12.0m commercial stock bars."""
    proj_id = request.project_id if request else "Structural Project"
    target_items = request.items if request and request.items else None

    if not target_items:
        # Default to consolidated project items
        chunks = request.candidate_chunks_cache if request else None
        proj_bbs = generate_consolidated_project_bbs(chunks=chunks, project_id=proj_id)
        target_items = [
            {
                "member_id": it.member_id,
                "bar_mark": it.bar_mark,
                "bar_diameter_mm": it.bar_diameter_mm,
                "cutting_length_mm": it.cutting_length_mm,
                "num_bars": it.num_bars,
            }
            for it in proj_bbs.items
        ]

    return optimize_cutting_stock(items=target_items, project_id=proj_id)


class QASignoffRequest(BaseModel):
    project_id: str = "Structural Project"
    member_id: str | None = None
    member_type: str = "COLUMN"
    engineer_name: str = "Chartered Structural Engineer"
    engineer_license: str = "SE/LIC-VERIFIED"
    organization: str = "Structural Engineering QA/QC Department"
    calculation_data: dict[str, Any] = Field(default_factory=dict)


@router.post("/qa-signoff", response_model=QAAuditCertificate)
def issue_qa_signoff_certificate(request: QASignoffRequest) -> QAAuditCertificate:
    """Generate tamper-proof cryptographic SHA-256 QA/QC audit certificate and IS code compliance checklist."""
    return create_qa_audit_certificate(
        calculation_data=request.calculation_data,
        engineer_name=request.engineer_name,
        engineer_license=request.engineer_license,
        organization=request.organization,
        project_id=request.project_id,
        member_id=request.member_id,
        member_type=request.member_type,
    )
