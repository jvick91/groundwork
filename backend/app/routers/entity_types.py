"""
EntityType and EntityAttribute management endpoints (SPEC-001 §6).

EntityType:
  GET    /entity-types              — list (system + org custom)    entity_types.read
  POST   /entity-types              — create custom type            entity_types.write (flag-gated)
  GET    /entity-types/{slug}       — retrieve by slug              entity_types.read
  PATCH  /entity-types/{slug}       — update (system types blocked) entity_types.write
  DELETE /entity-types/{slug}       — delete (system types blocked) entity_types.delete

EntityAttribute:
  GET    /entity-types/{slug}/attributes           — list attributes       entity_types.read
  POST   /entity-types/{slug}/attributes           — add attribute         entity_types.write
  GET    /entity-types/{slug}/attributes/{attr_id} — single attribute      entity_types.read
  PATCH  /entity-types/{slug}/attributes/{attr_id} — update attribute      entity_types.write
  DELETE /entity-types/{slug}/attributes/{attr_id} — delete attribute      entity_types.delete

Per ADR-009: routers are thin. They depend on a single ``<Aggregate>Service``
factory; ``actor_id`` and ``tenant_id`` are closed over inside the service
constructor; routers never import SQLAlchemy.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.dependencies import (
    get_entity_attribute_service,
    get_entity_type_service,
    require_permission,
)
from app.schemas.eav import (
    EntityAttributeCreate,
    EntityAttributeResponse,
    EntityAttributeUpdate,
    EntityTypeCreate,
    EntityTypeResponse,
    EntityTypeUpdate,
)
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.services.entity_attribute_service import EntityAttributeService
from app.services.entity_type_service import EntityTypeService

router = APIRouter(prefix="/entity-types", tags=["entity-types"])


@router.get(
    "",
    response_model=PaginatedResponse,
    dependencies=[require_permission("entity_types.read")],
)
async def list_entity_types(
    params: PaginationParams = Depends(),
    service: EntityTypeService = Depends(get_entity_type_service),
) -> PaginatedResponse:
    """Return cursor-paginated EntityTypes (system + org-scoped custom)."""
    items, meta = await service.list(params)
    return PaginatedResponse(
        data=[EntityTypeResponse.model_validate(et).model_dump() for et in items],
        pagination=meta,
    )


@router.post(
    "",
    status_code=201,
    response_model=EntityTypeResponse,
    dependencies=[require_permission("entity_types.write")],
)
async def create_entity_type(
    body: EntityTypeCreate,
    service: EntityTypeService = Depends(get_entity_type_service),
) -> EntityTypeResponse | JSONResponse:
    """Create a custom EntityType.

    Gated behind ``custom_entity_types_enabled``. When the flag is off,
    returns HTTP 501 so that auto-permission generation (TASK-019) can be
    implemented before any custom type is live.
    """
    if not settings.custom_entity_types_enabled:
        return JSONResponse(
            status_code=501,
            content={
                "error": "not_implemented",
                "message": (
                    "Custom EntityType creation is not available until auto-permission "
                    "generation (TASK-019) lands."
                ),
                "details": [],
            },
        )

    et = await service.create(body)
    return EntityTypeResponse.model_validate(et)


@router.get(
    "/{slug}",
    response_model=EntityTypeResponse,
    dependencies=[require_permission("entity_types.read")],
)
async def get_entity_type(
    slug: str,
    service: EntityTypeService = Depends(get_entity_type_service),
) -> EntityTypeResponse:
    """Retrieve a single EntityType by slug."""
    et = await service.get_by_slug(slug)
    return EntityTypeResponse.model_validate(et)


@router.patch(
    "/{slug}",
    response_model=EntityTypeResponse,
    dependencies=[require_permission("entity_types.write")],
)
async def update_entity_type(
    slug: str,
    body: EntityTypeUpdate,
    service: EntityTypeService = Depends(get_entity_type_service),
) -> EntityTypeResponse:
    """Partially update a custom EntityType (system types return 409)."""
    et = await service.update(slug, body)
    return EntityTypeResponse.model_validate(et)


@router.delete(
    "/{slug}",
    status_code=204,
    dependencies=[require_permission("entity_types.delete")],
)
async def delete_entity_type(
    slug: str,
    service: EntityTypeService = Depends(get_entity_type_service),
) -> None:
    """Delete a custom EntityType (system types return 409)."""
    await service.delete(slug)


# ---------------------------------------------------------------------------
# EntityAttribute endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{slug}/attributes",
    response_model=PaginatedResponse,
    dependencies=[require_permission("entity_types.read")],
)
async def list_entity_attributes(
    slug: str,
    params: PaginationParams = Depends(),
    type_service: EntityTypeService = Depends(get_entity_type_service),
    service: EntityAttributeService = Depends(get_entity_attribute_service),
) -> PaginatedResponse:
    """Return cursor-paginated attributes for the given EntityType."""
    et = await type_service.get_by_slug(slug)
    items, meta = await service.list(et.id, params)
    return PaginatedResponse(
        data=[EntityAttributeResponse.model_validate(ea).model_dump() for ea in items],
        pagination=meta,
    )


@router.post(
    "/{slug}/attributes",
    status_code=201,
    response_model=EntityAttributeResponse,
    dependencies=[require_permission("entity_types.write")],
)
async def create_entity_attribute(
    slug: str,
    body: EntityAttributeCreate,
    type_service: EntityTypeService = Depends(get_entity_type_service),
    service: EntityAttributeService = Depends(get_entity_attribute_service),
) -> EntityAttributeResponse:
    """Add an attribute to an EntityType (system types are extensible)."""
    et = await type_service.get_by_slug(slug)
    ea = await service.create(et.id, body)
    return EntityAttributeResponse.model_validate(ea)


@router.get(
    "/{slug}/attributes/{attr_id}",
    response_model=EntityAttributeResponse,
    dependencies=[require_permission("entity_types.read")],
)
async def get_entity_attribute(
    slug: str,
    attr_id: UUID,
    type_service: EntityTypeService = Depends(get_entity_type_service),
    service: EntityAttributeService = Depends(get_entity_attribute_service),
) -> EntityAttributeResponse:
    """Retrieve a single EntityAttribute by ID."""
    et = await type_service.get_by_slug(slug)
    ea = await service.get(attr_id, et.id)
    return EntityAttributeResponse.model_validate(ea)


@router.patch(
    "/{slug}/attributes/{attr_id}",
    response_model=EntityAttributeResponse,
    dependencies=[require_permission("entity_types.write")],
)
async def update_entity_attribute(
    slug: str,
    attr_id: UUID,
    body: EntityAttributeUpdate,
    type_service: EntityTypeService = Depends(get_entity_type_service),
    service: EntityAttributeService = Depends(get_entity_attribute_service),
) -> EntityAttributeResponse:
    """Partially update an EntityAttribute definition."""
    et = await type_service.get_by_slug(slug)
    ea = await service.update(attr_id, et.id, body)
    return EntityAttributeResponse.model_validate(ea)


@router.delete(
    "/{slug}/attributes/{attr_id}",
    status_code=204,
    dependencies=[require_permission("entity_types.delete")],
)
async def delete_entity_attribute(
    slug: str,
    attr_id: UUID,
    type_service: EntityTypeService = Depends(get_entity_type_service),
    service: EntityAttributeService = Depends(get_entity_attribute_service),
) -> None:
    """Delete an EntityAttribute (seed attributes on system types return 409)."""
    et = await type_service.get_by_slug(slug)
    await service.delete(attr_id, et)
