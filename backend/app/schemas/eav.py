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


# Format patterns enforced at the API layer. Stored as VARCHAR; SPEC-001 §Organization
# documents the formats. Phone is loose-shape only (no normalization) because the
# clinic platform has no comms feature yet — tighten when one lands.
_NPI_PATTERN = r"^\d{10}$"
_TAX_ID_PATTERN = r"^\d{2}-\d{7}$"
_PHONE_PATTERN = r"^[\d\s\-+().]{7,20}$"
# Two-letter ISO codes (state subdivision, country alpha-2). Uppercase required
# from clients — keeps storage canonical without an auto-uppercase validator.
_ISO_2_PATTERN = r"^[A-Z]{2}$"


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255, description="Legal name of the practice.")
    npi_number: str | None = Field(
        default=None,
        pattern=_NPI_PATTERN,
        description="Organization-level NPI (Type 2). 10 digits.",
    )
    tax_id: str | None = Field(
        default=None,
        pattern=_TAX_ID_PATTERN,
        description="EIN in 'NN-NNNNNNN' format.",
    )
    phone: str | None = Field(
        default=None,
        pattern=_PHONE_PATTERN,
        description="Main practice phone number.",
    )
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(
        default=None,
        pattern=_ISO_2_PATTERN,
        description="ISO-3166-2:US subdivision code, e.g. 'OR'.",
    )
    postal_code: str | None = Field(default=None, max_length=20)
    country: str = Field(
        default="US",
        pattern=_ISO_2_PATTERN,
        description="ISO-3166-1 alpha-2 country code.",
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone identifier (e.g. 'America/New_York').",
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        return _validate_iana_timezone(v)


class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    npi_number: str | None = Field(default=None, pattern=_NPI_PATTERN)
    tax_id: str | None = Field(default=None, pattern=_TAX_ID_PATTERN)
    phone: str | None = Field(default=None, pattern=_PHONE_PATTERN)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, pattern=_ISO_2_PATTERN)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, pattern=_ISO_2_PATTERN)
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
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None
