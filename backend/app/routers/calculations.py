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
