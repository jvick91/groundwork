"""StrEnum classes for the Compliance domain (SPEC-006)."""

from enum import StrEnum


class ConsentStatus(StrEnum):
    PENDING = "PENDING"
    SIGNED = "SIGNED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class FormType(StrEnum):
    INTAKE = "INTAKE"
    ASSESSMENT = "ASSESSMENT"
    CONSENT = "CONSENT"
    CUSTOM = "CUSTOM"
