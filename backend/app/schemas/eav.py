"""
Pydantic schemas for EAV domain models.

Organization is the root tenant record; every other table scopes to it.
Timezone fields are validated against the IANA tz database via ``zoneinfo``.
"""

import zoneinfo
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums.eav import FieldType


def _validate_iana_timezone(v: str) -> str:
    try:
        zoneinfo.ZoneInfo(v)
    except (zoneinfo.ZoneInfoNotFoundError, KeyError) as err:
        raise ValueError(f"'{v}' is not a valid IANA timezone identifier.") from err
    return v


# Field-level regex patterns are inlined at use site below per ADR-009 — no
# module-level allowlists, regexes, or pattern dicts in governed files.


class Address(BaseModel):
    """Reusable address shape — nested under parent schemas (ADR-007).

    The DB columns are flat (``address_line1``, ``city``, …) on the parent table;
    the API representation is nested so the same shape can be embedded on Person,
    InsurancePayer, etc. without redefining six fields per consumer.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    line1: str | None = Field(default=None, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{2}$",
        description="ISO-3166-2:US subdivision code, e.g. 'OR'.",
    )
    postal_code: str | None = Field(default=None, max_length=20)
    country: str = Field(
        default="US",
        pattern=r"^[A-Z]{2}$",
        description="ISO-3166-1 alpha-2 country code.",
    )


class AddressUpdate(BaseModel):
    """Partial address update — every field optional including ``country``.

    PATCH semantics: only fields explicitly set are applied (merge, not replace).
    Aligns with the parent ``OrganizationUpdate`` ``exclude_unset`` behaviour.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    line1: str | None = Field(default=None, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255, description="Legal name of the practice.")
    npi_number: str | None = Field(
        default=None,
        pattern=r"^\d{10}$",
        description="Organization-level NPI (Type 2). 10 digits.",
    )
    tax_id: str | None = Field(
        default=None,
        pattern=r"^\d{2}-\d{7}$",
        description="EIN in 'NN-NNNNNNN' format.",
    )
    phone: str | None = Field(
        default=None,
        pattern=r"^[\d\s\-+().]{7,20}$",
        description="Main practice phone number.",
    )
    address: Address = Field(default_factory=Address, description="Mailing address.")
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
    npi_number: str | None = Field(default=None, pattern=r"^\d{10}$")
    tax_id: str | None = Field(default=None, pattern=r"^\d{2}-\d{7}$")
    phone: str | None = Field(default=None, pattern=r"^[\d\s\-+().]{7,20}$")
    address: AddressUpdate | None = None
    timezone: str | None = None
    is_active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_iana_timezone(v)


class OrganizationResponse(BaseModel):
    """Response shape with nested ``address``.

    A pre-validator pulls the flat ORM columns (``address_line1``, ``city``, …)
    into a nested ``address`` dict so the API representation is consistent
    across Create / Update / Response while the DB stays flat.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    npi_number: str | None
    tax_id: str | None
    phone: str | None
    address: Address
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    @model_validator(mode="before")
    @classmethod
    def _nest_address(cls, v: Any) -> Any:
        """Promote flat ORM address columns into a nested ``address`` dict."""
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "name": v.name,
            "npi_number": v.npi_number,
            "tax_id": v.tax_id,
            "phone": v.phone,
            "address": {
                "line1": v.address_line1,
                "line2": v.address_line2,
                "city": v.city,
                "state": v.state,
                "postal_code": v.postal_code,
                "country": v.country,
            },
            "timezone": v.timezone,
            "is_active": v.is_active,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


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
    updated_at: datetime | None


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
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, description="Human name (e.g. 'Nutritionist').")
    slug: str = Field(..., min_length=1, description="URL-safe identifier (e.g. 'nutritionist').")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        return _validate_slug(v)


class EntityTypeUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

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


# ---------------------------------------------------------------------------
# EntityInstance schemas
# ---------------------------------------------------------------------------


class EntityInstanceCreate(BaseModel):
    """Create payload for an EntityInstance.

    ``values`` maps attribute machine-names to their raw string values
    (or ``None`` to explicitly clear a field). All values are validated
    against the parent EntityAttribute's ``field_type`` by the service.
    """

    person_id: UUID | None = None
    values: dict[str, str | None] = Field(default_factory=dict)


class EntityInstanceUpdate(BaseModel):
    """Partial update payload — only supplied fields are applied (PATCH semantics).

    ``values`` is a merge dict: only keys present in the payload are updated.
    Pass ``None`` as a value to clear that attribute.
    """

    is_active: bool | None = None
    person_id: UUID | None = None
    values: dict[str, str | None] | None = None


class EntityInstanceResponse(BaseModel):
    """Response shape for a single EntityInstance with its attribute values.

    ``values`` maps attribute machine-names to their current stored text
    (or ``None`` when unset). Constructed explicitly by the router from the
    ``EntityInstanceWithValues`` dataclass returned by the service.
    """

    id: UUID
    entity_type_id: UUID
    organization_id: UUID
    person_id: UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None
    deleted_at: datetime | None
    values: dict[str, str | None]
