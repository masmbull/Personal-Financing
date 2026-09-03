"""Financial institution schemas."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import InstitutionType


class InstitutionBase(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    legal_name: str = Field(min_length=1, max_length=200)
    short_name: str = Field(min_length=1, max_length=80)
    aliases: Optional[str] = None
    institution_type: InstitutionType = InstitutionType.OTHER_LICENSED
    swift_bic: Optional[str] = Field(None, max_length=11)
    active: bool = True
    source: Optional[str] = Field(None, max_length=100)
    source_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None


class InstitutionCreate(InstitutionBase):
    pass


class InstitutionUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=40)
    legal_name: Optional[str] = Field(None, min_length=1, max_length=200)
    short_name: Optional[str] = Field(None, min_length=1, max_length=80)
    aliases: Optional[str] = None
    institution_type: Optional[InstitutionType] = None
    swift_bic: Optional[str] = Field(None, max_length=11)
    active: Optional[bool] = None
    source: Optional[str] = Field(None, max_length=100)
    source_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None


class InstitutionResponse(InstitutionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    verified_at: Optional[datetime] = None


class InstitutionListResponse(BaseModel):
    items: list[InstitutionResponse]
    total: int
