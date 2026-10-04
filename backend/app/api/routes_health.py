"""Health check endpoint."""
from fastapi import APIRouter
from app.earth_engine.ee_client import EEClient
from app.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Returns API health status and GEE authentication state."""
    return HealthResponse(
        status="ok",
        gee_authenticated=EEClient.is_ready(),
        version="1.0.0",
        message=(
            "Earth Engine ready. All systems operational."
            if EEClient.is_ready()
            else "Earth Engine not authenticated. "
                 "Run `earthengine authenticate` or configure a service account."
        ),
    )
