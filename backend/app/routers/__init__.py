"""
Domain router conventions (TASK-008A; SPEC-007 §12.2).

Every domain router under this package follows the same shape so that
adding a new domain is a copy-and-rename exercise rather than a design
decision. The full convention lives in ``backend/docs/conventions.md``;
the abbreviated form is below for quick reference at the import site.

Required imports (typical):

    from fastapi import APIRouter, Depends, status
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.dependencies import (
        current_org,
        current_person,
        get_db,
        require_permission,
    )
    from app.schemas.<domain> import <Domain>Create, <Domain>Read
    from app.services import <domain> as <domain>_service

    router = APIRouter(prefix="/<resources>", tags=["<resources>"])

Required wiring on every state-changing endpoint:

    @router.post(
        "",
        response_model=<Domain>Read,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_permission("<resource>.create"))],
    )
    async def create_<resource>(
        body: <Domain>Create,
        db: AsyncSession = Depends(get_db),
        org: dict = Depends(current_org),
        actor: dict = Depends(current_person),
    ) -> <Domain>Read:
        result = await <domain>_service.create_<resource>(
            db, org_id=org["id"], actor_id=actor["id"], data=body,
        )
        return <Domain>Read.model_validate(result)

The router never imports SQLAlchemy primitives, never opens a session,
never writes business rules, and never bypasses ``require_permission`` —
TASK-014/015 will replace the stub auth implementation in
``app.core.security``; nothing in this package should break when they do.
"""
