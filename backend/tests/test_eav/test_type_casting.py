"""
Unit tests for the AttributeValue type casting engine (TASK-011A).

All tests are pure unit tests — no database, no HTTP client, no fixtures.
Each test group covers one FieldType's happy path(s) and every distinct
rejection reason documented in SPEC-001 §2.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import DomainValidationError
from app.enums.eav import FieldType
from app.services.eav_type_casting import cast_attribute_value

pytestmark = pytest.mark.anyio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ATTR = "test_field"


async def _cast(
    field_type: FieldType,
    value: str | None,
    options: object = None,
) -> str | None:
    return await cast_attribute_value(ATTR, field_type, value, options)


def _assert_fail(
    exc_info: pytest.ExceptionInfo[DomainValidationError], expected_fragment: str
) -> None:
    err = exc_info.value
    assert err.error == "validation_error"
    assert err.status_code == 422
    assert expected_fragment in err.message, f"Expected '{expected_fragment}' in '{err.message}'"
    assert any(d["attribute"] == ATTR for d in err.details)


# ---------------------------------------------------------------------------
# None passthrough (all field types)
# ---------------------------------------------------------------------------


async def test_none_value_returns_none_for_all_field_types() -> None:
    for ft in FieldType:
        result = await cast_attribute_value(ATTR, ft, None)
        assert result is None, f"Expected None for field_type={ft} with value=None"


# ---------------------------------------------------------------------------
# TEXT
# ---------------------------------------------------------------------------


class TestText:
    async def test_happy_plain_string(self) -> None:
        assert await _cast(FieldType.TEXT, "hello") == "hello"

    async def test_happy_unicode(self) -> None:
        assert await _cast(FieldType.TEXT, "こんにちは") == "こんにちは"

    async def test_happy_exactly_max_length(self) -> None:
        value = "x" * 10_000
        assert await _cast(FieldType.TEXT, value) == value

    async def test_reject_empty_string(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.TEXT, "")
        _assert_fail(exc, "empty string")

    async def test_reject_over_max_length(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.TEXT, "x" * 10_001)
        _assert_fail(exc, "maximum length")


# ---------------------------------------------------------------------------
# NUMBER
# ---------------------------------------------------------------------------


class TestNumber:
    async def test_happy_integer(self) -> None:
        assert await _cast(FieldType.NUMBER, "42") == "42"

    async def test_happy_decimal(self) -> None:
        assert await _cast(FieldType.NUMBER, "123.45") == "123.45"

    async def test_happy_negative(self) -> None:
        assert await _cast(FieldType.NUMBER, "-9.99") == "-9.99"

    async def test_happy_max_significant_digits(self) -> None:
        # 10 digits, 0 decimal places
        assert await _cast(FieldType.NUMBER, "1234567890") == "1234567890"

    async def test_happy_max_decimal_places(self) -> None:
        # 1 significant digit, 4 decimal places
        assert await _cast(FieldType.NUMBER, "0.0001") == "0.0001"

    async def test_happy_zero(self) -> None:
        assert await _cast(FieldType.NUMBER, "0") == "0"

    async def test_reject_not_a_number(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.NUMBER, "abc")
        _assert_fail(exc, "not a valid decimal number")

    async def test_reject_exponential_notation(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.NUMBER, "1e5")
        _assert_fail(exc, "exponential notation")

    async def test_reject_nan(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.NUMBER, "NaN")
        _assert_fail(exc, "finite")

    async def test_reject_infinity(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.NUMBER, "Infinity")
        _assert_fail(exc, "finite")

    async def test_reject_too_many_significant_digits(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.NUMBER, "12345678901")  # 11 digits
        _assert_fail(exc, "significant digits")

    async def test_reject_too_many_decimal_places(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.NUMBER, "1.00001")  # 5 decimal places
        _assert_fail(exc, "decimal places")


# ---------------------------------------------------------------------------
# DATE
# ---------------------------------------------------------------------------


class TestDate:
    async def test_happy_valid_date(self) -> None:
        assert await _cast(FieldType.DATE, "2026-04-15") == "2026-04-15"

    async def test_happy_leap_day(self) -> None:
        assert await _cast(FieldType.DATE, "2024-02-29") == "2024-02-29"

    async def test_reject_datetime_with_T(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.DATE, "2026-04-15T10:30:00")
        _assert_fail(exc, "no time component")

    async def test_reject_invalid_month(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.DATE, "2026-13-01")
        _assert_fail(exc, "not a valid calendar date")

    async def test_reject_invalid_day(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.DATE, "2026-04-31")
        _assert_fail(exc, "not a valid calendar date")

    async def test_reject_non_leap_feb29(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.DATE, "2026-02-29")
        _assert_fail(exc, "not a valid calendar date")

    async def test_reject_plaintext(self) -> None:
        # "April 15, 2026" contains spaces → triggers the "no time component" branch
        # because the date validator rejects anything with whitespace before trying
        # calendar parsing. The message correctly says YYYY-MM-DD is required.
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.DATE, "April 15, 2026")
        _assert_fail(exc, "YYYY-MM-DD")


# ---------------------------------------------------------------------------
# BOOL
# ---------------------------------------------------------------------------


class TestBool:
    async def test_happy_true(self) -> None:
        assert await _cast(FieldType.BOOL, "true") == "true"

    async def test_happy_false(self) -> None:
        assert await _cast(FieldType.BOOL, "false") == "false"

    async def test_reject_uppercase_true(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.BOOL, "True")
        _assert_fail(exc, "exactly 'true' or 'false'")

    async def test_reject_one(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.BOOL, "1")
        _assert_fail(exc, "exactly 'true' or 'false'")

    async def test_reject_yes(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.BOOL, "yes")
        _assert_fail(exc, "exactly 'true' or 'false'")

    async def test_reject_empty(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.BOOL, "")
        _assert_fail(exc, "exactly 'true' or 'false'")


# ---------------------------------------------------------------------------
# ENUM
# ---------------------------------------------------------------------------


class TestEnum:
    async def test_happy_first_option(self) -> None:
        assert await _cast(FieldType.ENUM, "NJ", ["NJ", "NY", "PA"]) == "NJ"

    async def test_happy_last_option(self) -> None:
        assert await _cast(FieldType.ENUM, "PA", ["NJ", "NY", "PA"]) == "PA"

    async def test_reject_value_not_in_options(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.ENUM, "CA", ["NJ", "NY", "PA"])
        _assert_fail(exc, "not a valid option")

    async def test_reject_case_mismatch(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.ENUM, "nj", ["NJ", "NY", "PA"])
        _assert_fail(exc, "not a valid option")

    async def test_reject_empty_options_list(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.ENUM, "NJ", [])
        _assert_fail(exc, "no options defined")

    async def test_reject_none_options(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.ENUM, "NJ", None)
        _assert_fail(exc, "no options defined")

    async def test_reject_non_list_options(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.ENUM, "NJ", "NJ,NY,PA")
        _assert_fail(exc, "no options defined")


# ---------------------------------------------------------------------------
# FK
# ---------------------------------------------------------------------------

_VALID_UUID_V4 = "550e8400-e29b-41d4-a716-446655440000"
_UUID_V1 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
_UUID_NOT_UUID = "not-a-uuid"


class TestFk:
    async def test_happy_uuid_v4(self) -> None:
        result = await _cast(FieldType.FK, _VALID_UUID_V4)
        assert result == _VALID_UUID_V4

    async def test_happy_normalizes_uppercase_to_lowercase(self) -> None:
        upper = _VALID_UUID_V4.upper()
        result = await _cast(FieldType.FK, upper)
        assert result == _VALID_UUID_V4

    async def test_reject_non_uuid(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.FK, _UUID_NOT_UUID)
        _assert_fail(exc, "not a valid UUID")

    async def test_reject_uuid_v1(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.FK, _UUID_V1)
        _assert_fail(exc, "UUID version 4")

    async def test_hook_called_when_provided(self) -> None:
        called_with: list[tuple[str, str | None]] = []

        async def hook(value: str, options: str | None) -> None:
            called_with.append((value, options))

        result = await cast_attribute_value(
            ATTR,
            FieldType.FK,
            _VALID_UUID_V4,
            "provider",
            validate_fk_existence=hook,
        )
        assert result == _VALID_UUID_V4
        assert called_with == [(_VALID_UUID_V4, "provider")]

    async def test_hook_not_called_when_none(self) -> None:
        # Ensure no error when hook is absent (TASK-011A baseline)
        result = await cast_attribute_value(
            ATTR,
            FieldType.FK,
            _VALID_UUID_V4,
            "provider",
            validate_fk_existence=None,
        )
        assert result == _VALID_UUID_V4

    async def test_hook_rejection_propagates(self) -> None:
        async def rejecting_hook(value: str, options: str | None) -> None:
            raise DomainValidationError(
                message=f"{ATTR}: referenced entity does not exist",
                details=[{"attribute": ATTR, "reason": "referenced entity does not exist"}],
            )

        with pytest.raises(DomainValidationError) as exc:
            await cast_attribute_value(
                ATTR,
                FieldType.FK,
                _VALID_UUID_V4,
                "provider",
                validate_fk_existence=rejecting_hook,
            )
        assert "does not exist" in exc.value.message


# ---------------------------------------------------------------------------
# JSONB
# ---------------------------------------------------------------------------

_JSONB_DICT = '{"key": "value"}'
_JSONB_LIST = "[1, 2, 3]"
_JSONB_NESTED = '{"a": {"b": [1, 2]}}'


class TestJsonb:
    async def test_happy_object(self) -> None:
        assert await _cast(FieldType.JSONB, _JSONB_DICT) == _JSONB_DICT

    async def test_happy_array(self) -> None:
        assert await _cast(FieldType.JSONB, _JSONB_LIST) == _JSONB_LIST

    async def test_happy_nested(self) -> None:
        assert await _cast(FieldType.JSONB, _JSONB_NESTED) == _JSONB_NESTED

    async def test_reject_scalar_string(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.JSONB, '"just a string"')
        _assert_fail(exc, "object or array")

    async def test_reject_scalar_number(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.JSONB, "42")
        _assert_fail(exc, "object or array")

    async def test_reject_scalar_boolean(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.JSONB, "true")
        _assert_fail(exc, "object or array")

    async def test_reject_invalid_json(self) -> None:
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.JSONB, "{not valid json}")
        _assert_fail(exc, "not valid JSON")

    async def test_reject_over_100kb(self) -> None:
        big = json_dumps_big_object(101 * 1024)
        with pytest.raises(DomainValidationError) as exc:
            await _cast(FieldType.JSONB, big)
        _assert_fail(exc, "maximum serialized size")


def json_dumps_big_object(target_bytes: int) -> str:
    """Build a JSON object whose UTF-8 byte count exceeds ``target_bytes``."""
    # Each "kXXXX":"v" entry is ~14 bytes; ~8000 entries ≈ 112 KB.
    entries = target_bytes // 14 + 1
    pairs = ", ".join(f'"k{i:04d}": "v"' for i in range(entries))
    return "{" + pairs + "}"
