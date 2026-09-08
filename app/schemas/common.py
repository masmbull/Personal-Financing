"""Shared API schemas."""
from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Consistent error envelope returned by every failed API call."""
    error: ErrorDetail


class UserResponse(BaseModel):
    id: int
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime | None = None


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int


class StatsResponse(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int
    total_transactions: int
    total_accounts: int
    admin_count: int
