"""
Pydantic schemas for EAV domain models.

Organization is the root tenant record; every other table scopes to it.
Timezone fields are validated against the IANA tz database via ``zoneinfo``.
"""

import zoneinfo
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
