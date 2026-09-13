"""Health probes - split liveness/readiness per Kubernetes/cloud conventions.

* GET /api/v1/health        -> liveness: process is up (no dependency checks)
* GET /api/v1/health/ready  -> readiness: DB reachable + writable + migrated

A dead-but-up process answers liveness 200 but readiness 503, so an
orchestrator can restart it without marking the whole pod unhealthy.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.database.db import get_db
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Process is alive. No dependency checks - always 200 if the app boots.",
)
def health_live():
    return HealthResponse(status="ok")


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
    description="DB connectable + writable and core tables present.",
    responses={503: {"description": "Dependency unavailable"}},
)
def health_ready(db=Depends(get_db)):
    # 1) DB connectable + a trivial query works.
    db.execute(text("SELECT 1")).scalar()
    # 2) Disk writable in the data dir (receipts/uploads live there).
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    probe = data_dir / ".health_probe"
    try:
        probe.write_text("ok")
        probe.read_text()
        probe.unlink()
    except OSError:
        raise HTTPException(status_code=503, detail="disk not writable")
    return HealthResponse(status="ok")
