"""
EAV domain router — Organization CRUD endpoints (SPEC-001 §2).

POST   /organizations            — create a new org (settings.write)
GET    /organizations            — paginated list     (settings.read)
GET    /organizations/{org_id}   — single org         (settings.read)
PATCH  /organizations/{org_id}   — partial update     (settings.write)
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_auth_context, get_db, require_permission
from app.core.security import AuthContext
from app.schemas.eav import OrganizationCreate, OrganizationResponse, OrganizationUpdate
from app.schemas.schemas import PaginatedResponse, PaginationParams
from app.services import eav_service

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post(
    "",
    status_code=201,
    response_model=OrganizationResponse,
    dependencies=[require_permission("settings.write")],
)
async def create_organization(
    body: OrganizationCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    """Create a new Organization (root tenant record)."""
    org = await eav_service.create_organization(
        db,
        actor_id=auth.person_id,
        data=body,
    )
    return OrganizationResponse.model_validate(org)


@router.get(
    "",
    response_model=PaginatedResponse,
    dependencies=[require_permission("settings.read")],
)
async def list_organizations(
    params: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """Return a cursor-paginated list of organizations."""
    items, meta = await eav_service.list_organizations(db, params=params)
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
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    """Retrieve a single Organization by primary key."""
    org = await eav_service.get_organization(db, org_id)
    return OrganizationResponse.model_validate(org)


@router.patch(
    "/{org_id}",
    response_model=OrganizationResponse,
    dependencies=[require_permission("settings.write")],
)
async def update_organization(
    org_id: UUID,
    body: OrganizationUpdate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    """Partially update an Organization (only provided fields are written)."""
    org = await eav_service.update_organization(
        db,
        org_id=org_id,
        actor_id=auth.person_id,
        data=body,
    )
    return OrganizationResponse.model_validate(org)
