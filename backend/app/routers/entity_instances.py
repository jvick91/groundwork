"""
EntityInstance management endpoints (SPEC-001 §6).

  GET    /entities/{type_slug}        — list instances (paginated)       {type_slug}.read
  POST   /entities/{type_slug}        — create instance with values      {type_slug}.write
  GET    /entities/{type_slug}/{id}   — retrieve instance with values    {type_slug}.read
  PATCH  /entities/{type_slug}/{id}   — update instance / merge values   {type_slug}.write
  DELETE /entities/{type_slug}/{id}   — soft-delete instance             {type_slug}.delete

Permission slugs are dynamically resolved from the path parameter (ADR-001 §3).
Per ADR-009: routers are thin HTTP adapters. All business logic lives in
``EntityInstanceService``.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.dependencies import get_entity_instance_service
from app.core.security import require_type_permission
from app.schemas.eav import (
    EntityInstanceCreate,
    EntityInstanceResponse,
    EntityInstanceUpdate,
)
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.services.entity_instance_service import EntityInstanceService, EntityInstanceWithValues

router = APIRouter(prefix="/entities", tags=["entity-instances"])


def _to_response(iwv: EntityInstanceWithValues) -> EntityInstanceResponse:
    """Build the API response shape from the service's dataclass result."""
    inst = iwv.instance
    return EntityInstanceResponse(
        id=inst.id,
        entity_type_id=inst.entity_type_id,
        organization_id=inst.organization_id,
        person_id=inst.person_id,
        is_active=inst.is_active,
        created_at=inst.created_at,
        updated_at=inst.updated_at,
        deleted_at=inst.deleted_at,
        values=iwv.values,
    )


@router.get(
    "/{type_slug}",
    response_model=PaginatedResponse,
    dependencies=[require_type_permission("read")],
)
async def list_entity_instances(
    type_slug: str,
    params: PaginationParams = Depends(),
    service: EntityInstanceService = Depends(get_entity_instance_service),
) -> PaginatedResponse:
    """Return cursor-paginated non-deleted instances for the given EntityType."""
    items, meta = await service.list(type_slug, params)
    return PaginatedResponse(
        data=[_to_response(iwv).model_dump() for iwv in items],
        pagination=meta,
    )


@router.post(
    "/{type_slug}",
    status_code=201,
    response_model=EntityInstanceResponse,
    dependencies=[require_type_permission("write")],
)
async def create_entity_instance(
    type_slug: str,
    body: EntityInstanceCreate,
    service: EntityInstanceService = Depends(get_entity_instance_service),
) -> EntityInstanceResponse:
    """Create an EntityInstance with initial attribute values."""
    return _to_response(await service.create(type_slug, body))


@router.get(
    "/{type_slug}/{instance_id}",
    response_model=EntityInstanceResponse,
    dependencies=[require_type_permission("read")],
)
async def get_entity_instance(
    type_slug: str,
    instance_id: UUID,
    service: EntityInstanceService = Depends(get_entity_instance_service),
) -> EntityInstanceResponse:
    """Retrieve a single EntityInstance with all its attribute values."""
    return _to_response(await service.get(type_slug, instance_id))


@router.patch(
    "/{type_slug}/{instance_id}",
    response_model=EntityInstanceResponse,
    dependencies=[require_type_permission("write")],
)
async def update_entity_instance(
    type_slug: str,
    instance_id: UUID,
    body: EntityInstanceUpdate,
    service: EntityInstanceService = Depends(get_entity_instance_service),
) -> EntityInstanceResponse:
    """Partially update an EntityInstance and/or merge attribute values."""
    return _to_response(await service.update(type_slug, instance_id, body))


@router.delete(
    "/{type_slug}/{instance_id}",
    status_code=204,
    dependencies=[require_type_permission("delete")],
)
async def delete_entity_instance(
    type_slug: str,
    instance_id: UUID,
    service: EntityInstanceService = Depends(get_entity_instance_service),
) -> None:
    """Soft-delete an EntityInstance (sets deleted_at, BR-05)."""
    await service.delete(type_slug, instance_id)
