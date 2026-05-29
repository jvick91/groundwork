"""StrEnum classes for the Identity / RBAC domain (SPEC-002)."""

from enum import StrEnum


class RoleDomain(StrEnum):
    ADMIN = "ADMIN"
    PROVIDER = "PROVIDER"
    CLIENT = "CLIENT"


class InvitationType(StrEnum):
    """Discriminator for the five invitation types (ADR-011 §five-invite-types).

    Type 5 (bootstrap) lives outside the /invitations endpoint — see
    TASK-014E / ADR-013.
    """

    PROVIDER = "provider"
    ADMIN = "admin"
    SYSTEM_ADMIN = "system_admin"
    CROSS_ORG = "cross_org"


class InvitationState(StrEnum):
    """State machine for an Invitation row (ADR-011 §state-machine)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"
