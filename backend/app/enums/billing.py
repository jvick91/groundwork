"""StrEnum classes for the Billing & Payments domain (SPEC-005)."""

from enum import StrEnum


class InsurancePriority(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class PaymentMethod(StrEnum):
    CASH = "CASH"
    CHECK = "CHECK"
    CARD = "CARD"
    ACH = "ACH"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


class PayerType(StrEnum):
    CLIENT = "CLIENT"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


class PaymentStatus(StrEnum):
    POSTED = "POSTED"
    VOIDED = "VOIDED"


class InvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    VOID = "VOID"
