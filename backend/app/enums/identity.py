"""StrEnum classes for the Identity / RBAC domain (SPEC-002)."""

from enum import StrEnum


class RoleDomain(StrEnum):
    ADMIN = "ADMIN"
    PROVIDER = "PROVIDER"
    CLIENT = "CLIENT"
