from fastapi import APIRouter

from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Liveness probe for load balancers and monitoring.",
    responses={200: {"description": "Application is healthy"}},
)
def health():
    return HealthResponse(status="ok")
