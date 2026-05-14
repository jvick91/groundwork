"""
Identity domain router — Person CRUD endpoints (SPEC-002 §8).

  GET    /people          — list people in this org via PersonRole join (people.read)
  POST   /people          — create a Person identity record               (people.write)
  GET    /people/{id}     — retrieve a Person scoped through PersonRole   (people.read)
  PATCH  /people/{id}     — partial update                                (people.write)
  DELETE /people/{id}     — soft-delete                                   (people.delete)

Per ADR-009 routers are thin HTTP adapters. All business logic and SQL live
in ``PersonService`` (``app.services.identity_service``).
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.dependencies import get_person_service, require_permission
from app.schemas.identity import PersonCreate, PersonResponse, PersonUpdate
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.services.identity_service import PersonService

router = APIRouter(prefix="/people", tags=["people"])


@router.post(
    "",
    status_code=201,
    response_model=PersonResponse,
    dependencies=[require_permission("people.write")],
)
async def create_person(
    body: PersonCreate,
    service: PersonService = Depends(get_person_service),
) -> PersonResponse:
    """Create a Person identity record (tenant-independent)."""
    person = await service.create(body)
    return PersonResponse.model_validate(person)


@router.get(
    "",
    response_model=PaginatedResponse,
    dependencies=[require_permission("people.read")],
)
async def list_people(
    params: PaginationParams = Depends(),
    service: PersonService = Depends(get_person_service),
) -> PaginatedResponse:
    """Return cursor-paginated people with active PersonRole in this org."""
    items, meta = await service.list(params)
    return PaginatedResponse(
        data=[PersonResponse.model_validate(p).model_dump(mode="json") for p in items],
        pagination=meta,
    )


@router.get(
    "/{person_id}",
    response_model=PersonResponse,
    dependencies=[require_permission("people.read")],
)
async def get_person(
    person_id: UUID,
    service: PersonService = Depends(get_person_service),
) -> PersonResponse:
    """Retrieve a single Person scoped through PersonRole."""
    person = await service.get(person_id)
    return PersonResponse.model_validate(person)


@router.patch(
    "/{person_id}",
    response_model=PersonResponse,
    dependencies=[require_permission("people.write")],
)
async def update_person(
    person_id: UUID,
    body: PersonUpdate,
    service: PersonService = Depends(get_person_service),
) -> PersonResponse:
    """Partially update a Person (only provided fields are written)."""
    person = await service.update(person_id, body)
    return PersonResponse.model_validate(person)


@router.delete(
    "/{person_id}",
    status_code=204,
    dependencies=[require_permission("people.delete")],
)
async def delete_person(
    person_id: UUID,
    service: PersonService = Depends(get_person_service),
) -> None:
    """Soft-delete a Person (sets ``deleted_at``, BR-05)."""
    await service.delete(person_id)
