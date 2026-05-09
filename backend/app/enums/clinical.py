"""StrEnum classes for the Clinical Notes domain (SPEC-004)."""

from enum import StrEnum


class NoteFormat(StrEnum):
    SOAP = "SOAP"
    DAP = "DAP"
    BIRP = "BIRP"


class NoteStatus(StrEnum):
    DRAFT = "DRAFT"
    SIGNED = "SIGNED"
    COSIGNED = "COSIGNED"
    AMENDMENT_PENDING = "AMENDMENT_PENDING"
