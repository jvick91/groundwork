"""
Invitation router (TASK-014F / ADR-011, TASK-014G).

  POST   /invitations              — send (invites.send)
  GET    /invitations              — list (invites.read)
  GET    /invitations/{id}         — detail (invites.read)
  POST   /invitations/{id}/resend  — rotate nonce (invites.send)
  DELETE /invitations/{id}         — revoke (invites.revoke)
  POST   /invitations/accept       — accept by nonce+JWT (no auth required)

Per ADR-009 this router is a thin HTTP adapter. All business logic lives in
``InvitationService``.

Uniform response shape (ADR-011 §uniform-response): POST /invitations always
returns ``{status: "pending", invitation_id: "<uuid>"}`` regardless of invite
type or whether the email maps to an existing Person — preventing cross-tenant
email enumeration.

The accept endpoint is public: the invitee has no existing session.  The JWT
in the request body is validated against Auth0 JWKS by this route before the
service method runs.  The ``/api/v1/invitations/accept`` path is therefore
listed in the AuthMiddleware skip list so the middleware does not reject the
missing Authorization header.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_invitation_service, require_permission
from app.core.security import decode_token, fetch_jwks
from app.enums.identity import InvitationState
from app.schemas.identity import (
    InvitationAcceptRequest,
    InvitationAcceptResponse,
    InvitationCreate,
    InvitationResponse,
    InvitationSendResponse,
)
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.services.invitation_service import InvitationService

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post(
    "",
    status_code=201,
    response_model=InvitationSendResponse,
    dependencies=[require_permission("invites.send")],
)
async def send_invitation(
    body: InvitationCreate,
    service: InvitationService = Depends(get_invitation_service),
) -> InvitationSendResponse:
    """Dispatch an invitation.

    The response is always ``{status: "pending", invitation_id: uuid}``
    regardless of whether the email maps to an existing Person (ADR-011).
    """
    invitation = await service.send(body)
    return InvitationSendResponse(invitation_id=invitation.id)


@router.get(
    "",
    response_model=PaginatedResponse,
    dependencies=[require_permission("invites.read")],
)
async def list_invitations(
    state: InvitationState | None = Query(default=None, description="Filter by state."),
    params: PaginationParams = Depends(),
    service: InvitationService = Depends(get_invitation_service),
) -> PaginatedResponse:
    """List invitations for the requesting organisation, optionally filtered by state."""
    items, meta = await service.list(params, state=state)
    return PaginatedResponse(
        data=[InvitationResponse.model_validate(i).model_dump(mode="json") for i in items],
        pagination=meta,
    )


@router.get(
    "/{invitation_id}",
    response_model=InvitationResponse,
    dependencies=[require_permission("invites.read")],
)
async def get_invitation(
    invitation_id: UUID,
    service: InvitationService = Depends(get_invitation_service),
) -> InvitationResponse:
    """Retrieve a single invitation visible to the requesting organisation."""
    invitation = await service.get(invitation_id)
    return InvitationResponse.model_validate(invitation)


@router.post(
    "/{invitation_id}/resend",
    response_model=InvitationResponse,
    dependencies=[require_permission("invites.send")],
)
async def resend_invitation(
    invitation_id: UUID,
    service: InvitationService = Depends(get_invitation_service),
) -> InvitationResponse:
    """Rotate the nonce and re-send the Auth0 invitation email.

    Only valid when the invitation is in ``pending`` state. The old email link
    is invalidated immediately.
    """
    invitation = await service.resend(invitation_id)
    return InvitationResponse.model_validate(invitation)


@router.delete(
    "/{invitation_id}",
    status_code=204,
    response_model=None,
    response_class=Response,
    dependencies=[require_permission("invites.revoke")],
)
async def revoke_invitation(
    invitation_id: UUID,
    service: InvitationService = Depends(get_invitation_service),
) -> None:
    """Revoke a pending invitation.

    Sets ``state = 'revoked'`` and revokes the Auth0 invitation. The row is
    preserved for audit. A new invitation may be sent immediately for the
    same email.
    """
    await service.revoke(invitation_id)


@router.post(
    "/accept",
    status_code=200,
    response_model=InvitationAcceptResponse,
)
async def accept_invitation(
    body: InvitationAcceptRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> InvitationAcceptResponse:
    """Accept an invitation by nonce + JWT.

    Does **not** require an ``X-Organization-Id`` header or an existing auth
    session — the invitee has no account yet (or is joining a new org).
    The JWT in the request body is validated here against Auth0 JWKS; ``sub``
    and ``org_id`` claims are forwarded to the service.

    Returns ``{person_id, person_role_id}`` on success.

    Raises:
        410 Gone: Invitation not found, expired, revoked, or already accepted.
        422 Unprocessable Entity: JWT org_id does not match the invitation's org.
        409 Conflict: Cross-org invite but no matching Person exists yet.
        401 Unauthorized: JWT signature is invalid or the token is expired.
    """
    # JWT validation — skipped in stub mode (no real Auth0 keys available).
    if settings.auth_stub_enabled:
        auth_subject: str = body.jwt  # treat the raw string as the subject for local dev
        jwt_org_id: str | None = None
    else:
        try:
            key_set = await fetch_jwks()
            claims = decode_token(body.jwt, key_set)
        except Exception as exc:
            raise HTTPException(
                status_code=401,
                detail={"error": "unauthorized", "message": "JWT validation failed."},
            ) from exc
        auth_subject = claims.get("sub", "")
        jwt_org_id = claims.get("org_id")

    result = await InvitationService.accept_invitation(
        session=session,
        nonce=body.nonce,
        auth_subject=auth_subject,
        jwt_org_id=jwt_org_id,
        request_ip=request.client.host if request.client else None,
        request_ua=request.headers.get("user-agent"),
    )
    return InvitationAcceptResponse(
        person_id=result.person.id,
        person_role_id=result.person_role.id,
    )
