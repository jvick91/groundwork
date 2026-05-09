"""StrEnum classes for the EAV domain (SPEC-001)."""

from enum import StrEnum


class FieldType(StrEnum):
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    DATE = "DATE"
    BOOL = "BOOL"
    ENUM = "ENUM"
    FK = "FK"
    JSONB = "JSONB"
