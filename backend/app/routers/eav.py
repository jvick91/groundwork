"""
EAV domain router — Organization CRUD endpoints (SPEC-001 §2).

POST   /organizations            — create a new org (settings.write)
GET    /organizations            — paginated list     (settings.read)
GET    /organizations/{org_id}   — single org         (settings.read)
PATCH  /organizations/{org_id}   — partial update     (settings.write)

Per ADR-009: routes are thin. They depend on a single ``OrganizationService``
factory; ``actor_id`` is closed over inside the service constructor; routers
never import SQLAlchemy.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.dependencies import get_organization_service, require_permission
from app.schemas.eav import OrganizationCreate, OrganizationResponse, OrganizationUpdate
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post(
    "",
    status_code=201,
    response_model=OrganizationResponse,
    dependencies=[require_permission("settings.write")],
)
async def create_organization(
    body: OrganizationCreate,
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizationResponse:
    """Create a new Organization (root tenant record)."""
    org = await service.create(body)
    return OrganizationResponse.model_validate(org)


@router.get(
    "",
    response_model=PaginatedResponse,
    dependencies=[require_permission("settings.read")],
)
async def list_organizations(
    params: PaginationParams = Depends(),
    service: OrganizationService = Depends(get_organization_service),
) -> PaginatedResponse:
    """Return a cursor-paginated list of organizations."""
    items, meta = await service.list(params)
    return PaginatedResponse(
        data=[OrganizationResponse.model_validate(o).model_dump() for o in items],
        pagination=meta,
    )


@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    dependencies=[require_permission("settings.read")],
)
async def get_organization(
    org_id: UUID,
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizationResponse:
    """Retrieve a single Organization by primary key."""
    org = await service.get(org_id)
    return OrganizationResponse.model_validate(org)


@router.patch(
    "/{org_id}",
    response_model=OrganizationResponse,
    dependencies=[require_permission("settings.write")],
)
async def update_organization(
    org_id: UUID,
    body: OrganizationUpdate,
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizationResponse:
    """Partially update an Organization (only provided fields are written)."""
    org = await service.update(org_id, body)
    return OrganizationResponse.model_validate(org)
