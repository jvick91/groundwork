"""
Pydantic schemas for EAV domain models.

Organization is the root tenant record; every other table scopes to it.
Timezone fields are validated against the IANA tz database via ``zoneinfo``.
"""

import zoneinfo
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.models import FieldType


def _validate_iana_timezone(v: str) -> str:
    try:
        zoneinfo.ZoneInfo(v)
    except (zoneinfo.ZoneInfoNotFoundError, KeyError) as err:
        raise ValueError(f"'{v}' is not a valid IANA timezone identifier.") from err
    return v


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Legal name of the practice.")
    npi_number: str | None = Field(default=None, description="Organization-level NPI (Type 2).")
    tax_id: str | None = Field(default=None, description="EIN or tax identifier.")
    phone: str | None = Field(default=None, description="Main practice phone number.")
    address: str | None = Field(default=None, description="Full mailing address.")
    timezone: str = Field(
        default="UTC",
        description="IANA timezone identifier (e.g. 'America/New_York').",
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        return _validate_iana_timezone(v)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    npi_number: str | None = None
    tax_id: str | None = None
    phone: str | None = None
    address: str | None = None
    timezone: str | None = None
    is_active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_iana_timezone(v)


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    npi_number: str | None
    tax_id: str | None
    phone: str | None
    address: str | None
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None


# ---------------------------------------------------------------------------
# EntityAttribute schemas
# ---------------------------------------------------------------------------


class EntityAttributeCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Machine name (e.g. 'license_number').")
    display_name: str = Field(..., min_length=1, description="Human label.")
    field_type: FieldType
    is_required: bool = False
    options: Any | None = Field(
        default=None,
        description="Enum choices (list[str]) or FK target slug (str).",
    )
    display_order: int = Field(default=0, ge=0)


class EntityAttributeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    display_name: str | None = None
    field_type: FieldType | None = None
    is_required: bool | None = None
    options: Any | None = None
    display_order: int | None = Field(default=None, ge=0)


class EntityAttributeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type_id: UUID
    name: str
    display_name: str
    field_type: FieldType
    is_required: bool
    options: Any | None
    display_order: int
    created_at: datetime


# ---------------------------------------------------------------------------
# EntityType schemas
# ---------------------------------------------------------------------------


def _validate_slug(v: str) -> str:
    import re

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", v):
        raise ValueError(
            "Slug must be lowercase alphanumeric with optional hyphens "
            "(e.g. 'nutritionist', 'speech-language-therapist')."
        )
    return v


class EntityTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Human name (e.g. 'Nutritionist').")
    slug: str = Field(..., min_length=1, description="URL-safe identifier (e.g. 'nutritionist').")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        return _validate_slug(v)


class EntityTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    slug: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_slug(v)


class EntityTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    name: str
    slug: str
    is_system_type: bool
    is_person_subtype: bool
    created_at: datetime
