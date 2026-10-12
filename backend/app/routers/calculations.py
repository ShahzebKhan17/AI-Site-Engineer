from fastapi import APIRouter

from app.engineering.calculators.column import calculate_longitudinal_bar
from app.engineering.models import ColumnBarRequest, ColumnBarResult

router = APIRouter(prefix="/calculations", tags=["calculations"])


@router.post("/column-longitudinal-bar", response_model=ColumnBarResult)
def calculate_column_longitudinal_bar(request: ColumnBarRequest) -> ColumnBarResult:
    """Run deterministic arithmetic over reviewed drawing inputs."""
    return calculate_longitudinal_bar(request)
