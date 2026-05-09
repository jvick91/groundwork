"""
AttributeValue type casting and validation engine (SPEC-001 §2).

Pure in-process module — no database access, no ORM model imports.
Each of the seven ``FieldType`` values maps to a cast-and-validate function
that returns a canonicalized string for storage, or raises
``DomainValidationError`` (HTTP 422) if the value violates the type's rules.

Extension point
---------------
``cast_attribute_value`` accepts an optional ``validate_fk_existence`` hook.
TASK-011A leaves it ``None`` (UUID-format check only). TASK-011C wires in an
async closure that captures the request session and org_id and performs the
existence / same-org / type-slug check described in SPEC-001 §2.

The hook's full standalone signature (convenience wrapper for TASK-011C):
    validate_fk_existence(session, value, options, org_id) -> None
    Raises DomainValidationError when the referenced EntityInstance does not
    exist, is soft-deleted, belongs to a different org, or mismatches the
    EntityType slug in ``options``.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app.core.exceptions import DomainValidationError
from app.enums.eav import FieldType

# ---------------------------------------------------------------------------
# Public type alias — TASK-011C binds the concrete implementation.
# The hook already has (session, org_id) captured as a closure; at the
# cast_attribute_value call site only (value, options) remain.
# ---------------------------------------------------------------------------

ValidateFkExistence = Callable[[str, str | None], Awaitable[None]]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_TEXT_LEN = 10_000
_MAX_NUMBER_SIGNIFICANT = 10
_MAX_NUMBER_DECIMALS = 4
_MAX_JSONB_BYTES = 100 * 1024  # 100 KB

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _fail(attr_name: str, reason: str) -> None:
    raise DomainValidationError(
        message=f"{attr_name}: {reason}",
        details=[{"attribute": attr_name, "reason": reason}],
    )


def _cast_text(attr_name: str, value: str) -> str:
    if value == "":
        _fail(attr_name, "empty string is not a valid text value; use null to represent absence")
    if len(value) > _MAX_TEXT_LEN:
        _fail(
            attr_name,
            f"text value exceeds maximum length of {_MAX_TEXT_LEN} characters",
        )
    return value


def _cast_number(attr_name: str, value: str) -> str:
    # Reject exponential notation before Decimal parses it (Decimal accepts "1E+5").
    if "e" in value.lower():
        _fail(attr_name, "number value must not use exponential notation")
    try:
        d = Decimal(value)
    except InvalidOperation:
        _fail(attr_name, f"'{value}' is not a valid decimal number")
        raise  # unreachable; satisfies type checker

    if not d.is_finite():
        _fail(attr_name, "number value must be a finite number (NaN and Infinity are not allowed)")

    _sign, digits, exponent = d.as_tuple()
    n_digits = len(digits)
    n_decimals = max(0, -int(exponent))

    if n_digits > _MAX_NUMBER_SIGNIFICANT:
        _fail(
            attr_name,
            f"number value exceeds {_MAX_NUMBER_SIGNIFICANT} significant digits",
        )
    if n_decimals > _MAX_NUMBER_DECIMALS:
        _fail(
            attr_name,
            f"number value exceeds {_MAX_NUMBER_DECIMALS} decimal places",
        )
    # Canonicalize: strip trailing zeros only when there is no fractional part.
    return str(d)


def _cast_date(attr_name: str, value: str) -> str:
    # Reject any ISO 8601 datetime (contains 'T') or space-separated datetime.
    if "T" in value or " " in value.strip():
        _fail(
            attr_name,
            f"date value '{value}' must be YYYY-MM-DD with no time component",
        )
    try:
        date.fromisoformat(value)
    except ValueError:
        _fail(attr_name, f"date value '{value}' is not a valid calendar date")
    return value


def _cast_bool(attr_name: str, value: str) -> str:
    if value not in ("true", "false"):
        _fail(
            attr_name,
            f"bool value must be exactly 'true' or 'false', got '{value}'",
        )
    return value


def _cast_enum(attr_name: str, value: str, options: Any) -> str:
    if not isinstance(options, list) or len(options) == 0:
        _fail(attr_name, "enum attribute has no options defined")
    if value not in options:
        _fail(
            attr_name,
            f"'{value}' is not a valid option; allowed values are: {options}",
        )
    return value


def _cast_fk_shape(attr_name: str, value: str) -> str:
    """Validate UUID v4 format only — existence check is deferred to TASK-011C."""
    try:
        u = UUID(value)
    except ValueError:
        _fail(attr_name, f"fk value '{value}' is not a valid UUID")
        raise  # unreachable
    if u.version != 4:
        _fail(attr_name, f"fk value '{value}' must be a UUID version 4")
    return str(u)  # canonical lowercase hyphenated form


def _cast_jsonb(attr_name: str, value: str) -> str:
    byte_size = len(value.encode())
    if byte_size > _MAX_JSONB_BYTES:
        _fail(
            attr_name,
            f"jsonb value exceeds maximum serialized size of {_MAX_JSONB_BYTES // 1024} KB",
        )
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        _fail(attr_name, f"jsonb value is not valid JSON: {exc}")
        raise  # unreachable

    if not isinstance(parsed, (dict, list)):
        _fail(attr_name, "jsonb top-level value must be a JSON object or array, not a scalar")
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def cast_attribute_value(
    attr_name: str,
    field_type: FieldType,
    value: str | None,
    options: Any | None = None,
    *,
    validate_fk_existence: ValidateFkExistence | None = None,
) -> str | None:
    """Cast and validate ``value`` against its ``field_type`` rules.

    Returns the canonicalized string to persist as ``AttributeValue.value``,
    or ``None`` when ``value`` is ``None``.

    Raises ``DomainValidationError`` (HTTP 422) on any constraint violation.
    The error message and the ``details`` list both carry ``attr_name`` and the
    specific reason, as required by SPEC-001 §2.

    Parameters
    ----------
    attr_name:
        Human-readable attribute name used in error messages (e.g.
        ``"license_expiry"``).
    field_type:
        The ``FieldType`` of the parent ``EntityAttribute``.
    value:
        Raw string value supplied by the caller. ``None`` means "no value" and
        is returned as-is (required-field enforcement is the caller's concern).
    options:
        The ``options`` JSONB from the parent ``EntityAttribute``.  Required
        for ``enum`` (must be ``list[str]``) and surfaced as the type-slug for
        ``fk`` checks.
    validate_fk_existence:
        Optional async hook injected by callers that own a session.  When
        provided, called after UUID-format validation succeeds.  TASK-011A
        passes ``None``; TASK-011C wires in the existence / same-org /
        type-slug check.  The hook's signature (after session/org_id are
        captured by closure) is ``(value: str, options: str | None) -> None``.
    """
    if value is None:
        return None

    if field_type == FieldType.TEXT:
        return _cast_text(attr_name, value)
    if field_type == FieldType.NUMBER:
        return _cast_number(attr_name, value)
    if field_type == FieldType.DATE:
        return _cast_date(attr_name, value)
    if field_type == FieldType.BOOL:
        return _cast_bool(attr_name, value)
    if field_type == FieldType.ENUM:
        return _cast_enum(attr_name, value, options)
    if field_type == FieldType.FK:
        canonical = _cast_fk_shape(attr_name, value)
        if validate_fk_existence is not None:
            await validate_fk_existence(canonical, options)
        return canonical
    if field_type == FieldType.JSONB:
        return _cast_jsonb(attr_name, value)

    _fail(attr_name, f"unknown field_type '{field_type}'")
    return None  # unreachable; satisfies type checker
