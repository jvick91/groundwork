"""ASGI middleware for the Groundwork backend.

Per ADR-009 (2026-05-19 amendment) ``middleware/`` is a permitted folder
for named ASGI request-pipeline concerns. Generic catch-all names like
``helpers/`` and ``utils/`` remain forbidden.

Current members:

* ``AuthMiddleware`` (``auth.py``) — JWT validation, person resolution,
  attaches ``request.state.jwt_claims`` and ``request.state.auth``.
* ``OrganizationMiddleware`` (``organization.py``) — ``X-Organization-Id``
  extraction and active-PersonRole check; attaches
  ``request.state.organization_id``.
"""

from app.middleware.auth import AuthMiddleware
from app.middleware.organization import OrganizationMiddleware

__all__ = ["AuthMiddleware", "OrganizationMiddleware"]
