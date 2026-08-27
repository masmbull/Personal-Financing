"""Shared API schemas."""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Consistent error envelope returned by every failed API call."""
    error: ErrorDetail
