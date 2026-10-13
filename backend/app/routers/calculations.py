from fastapi import APIRouter

from app.engineering.calculators.beam import BeamBarRequest, BeamBarResult, calculate_beam_bar_length
from app.engineering.calculators.column import calculate_longitudinal_bar
from app.engineering.calculators.footing import FootingMeshRequest, FootingMeshResult, calculate_footing_mesh
from app.engineering.models import ColumnBarRequest, ColumnBarResult

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
