"""
Tests for the standard error response contract (SPEC-007 §7).

Each test verifies:
  - Correct HTTP status code
  - Standard envelope shape: {error, message, status, details}
  - Stable error code matches SPEC-007 §7.3

Test routes are registered directly on a fresh app instance per fixture so
no production routes are required and no domain logic is exercised.
"""

from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Query
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.exceptions import (
    AccountInactiveError,
    BadRequestError,
    BridgeRuleViolation,
    ConflictError,
    DomainValidationError,
    ForbiddenError,
    InternalError,
    NotFoundError,
    OrgAccessDeniedError,
    OrganizationRequiredError,
    PrerequisiteNotMetError,
    RateLimitedError,
    ResourceLockedError,
    StateTransitionDeniedError,
    UnauthorizedError,
)
from app.main import create_app

# ---------------------------------------------------------------------------
# Test app fixture — one app with one trigger route per error code
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def error_app() -> FastAPI:
    app = create_app()

    @app.get("/test/bad-request")
    async def raise_bad_request():
        raise BadRequestError("Missing required header.")

    @app.get("/test/organization-required")
    async def raise_organization_required():
        raise OrganizationRequiredError()

    @app.get("/test/unauthorized")
    async def raise_unauthorized():
        raise UnauthorizedError()

    @app.get("/test/account-inactive")
    async def raise_account_inactive():
        raise AccountInactiveError()

    @app.get("/test/forbidden")
    async def raise_forbidden():
        raise ForbiddenError()

    @app.get("/test/org-access-denied")
    async def raise_org_access_denied():
        raise OrgAccessDeniedError()

    widget_id = UUID("00000000-0000-0000-0000-000000000123")

    @app.get("/test/not-found")
    async def raise_not_found():
        raise NotFoundError("Widget", widget_id)

    @app.get("/test/conflict")
    async def raise_conflict():
        raise ConflictError("A widget with this name already exists.")

    @app.get("/test/state-transition-denied")
    async def raise_state_transition():
        raise StateTransitionDeniedError("ClinicalNote", "signed", "draft")

    @app.get("/test/resource-locked")
    async def raise_resource_locked():
        raise ResourceLockedError("ClinicalNote", "note has been signed")

    @app.get("/test/domain-validation-error")
    async def raise_domain_validation():
        raise DomainValidationError(
            "end_time must be after start_time.",
            details=[
                {
                    "field": "end_time",
                    "message": "must be after start_time",
                    "code": "invalid_time_range",
                }
            ],
        )

    @app.get("/test/bridge-rule-violation")
    async def raise_bridge_rule():
        raise BridgeRuleViolation("provider_instance_id", "provider", "client")

    @app.get("/test/prerequisite-not-met")
    async def raise_prerequisite():
        raise PrerequisiteNotMetError("Client has not completed intake consent.")

    @app.get("/test/rate-limited")
    async def raise_rate_limited():
        raise RateLimitedError()

    @app.get("/test/internal-error")
    async def raise_internal():
        raise InternalError()

    @app.get("/test/unhandled-exception")
    async def raise_unhandled():
        raise RuntimeError("database is on fire")

    class _Body(BaseModel):
        name: str

    @app.post("/test/validation-422")
    async def trigger_pydantic_validation(_body: _Body):
        return {"ok": True}

    # Multiple invalid fields in one request (SPEC-007 §7.2 — details is an array).
    class _MultiBody(BaseModel):
        name: str
        age: int
        email: str

    @app.post("/test/validation-422-multi")
    async def trigger_multi_validation(_body: _MultiBody):
        return {"ok": True}

    # Nested field path — SPEC-007 §7.4 uses `content.subjective` as the example.
    class _Content(BaseModel):
        subjective: str

    class _NestedBody(BaseModel):
        content: _Content

    @app.post("/test/validation-422-nested")
    async def trigger_nested_validation(_body: _NestedBody):
        return {"ok": True}

    # Query-param validation — `loc` starts with "query", must be stripped.
    @app.get("/test/validation-422-query")
    async def trigger_query_validation(limit: int = Query(...)):
        return {"limit": limit}

    # Hand-raised HTTPException — must be coerced into the standard envelope.
    @app.get("/test/http-exception")
    async def raise_http_exception():
        raise HTTPException(status_code=403, detail="Custom forbidden message.")

    return app


@pytest_asyncio.fixture(scope="module")
async def ec(error_app: FastAPI):
    """Error client — AsyncClient wired to the error_app.

    `raise_app_exceptions=False` so we can assert on the 500 response the
    catch-all Exception handler produces.

    Per ADR-010 / TASK-014, requests go through real auth + org-context
    middleware. We seed alice (default identity) and bake her token +
    X-Organization-Id into the client so the test routes (which deliberately
    raise) actually run instead of being intercepted at 401.
    """
    from app.core.database import Database
    from tests.conftest import (
        DEFAULT_ORG_ID,
        _fetch_keycloak_token,
        _seed_default_identity,
    )

    session_factory = Database.get_session_factory()
    async with session_factory() as setup_session:
        await _seed_default_identity(setup_session)
    token = await _fetch_keycloak_token("alice")

    async with AsyncClient(
        transport=ASGITransport(app=error_app, raise_app_exceptions=False),
        base_url="http://test",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": str(DEFAULT_ORG_ID),
        },
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def assert_envelope(data: dict[str, Any], error_code: str, status: int) -> None:
    assert data["error"] == error_code
    assert data["status"] == status
    assert isinstance(data["message"], str) and data["message"]
    assert isinstance(data["details"], list)


# ---------------------------------------------------------------------------
# 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bad_request_returns_400(ec: AsyncClient):
    r = await ec.get("/test/bad-request")
    assert r.status_code == 400
    assert_envelope(r.json(), "bad_request", 400)


@pytest.mark.asyncio
async def test_organization_required_returns_400(ec: AsyncClient):
    r = await ec.get("/test/organization-required")
    assert r.status_code == 400
    assert_envelope(r.json(), "organization_required", 400)


# ---------------------------------------------------------------------------
# 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthorized_returns_401(ec: AsyncClient):
    r = await ec.get("/test/unauthorized")
    assert r.status_code == 401
    assert_envelope(r.json(), "unauthorized", 401)


@pytest.mark.asyncio
async def test_account_inactive_returns_401(ec: AsyncClient):
    r = await ec.get("/test/account-inactive")
    assert r.status_code == 401
    assert_envelope(r.json(), "account_inactive", 401)


# ---------------------------------------------------------------------------
# 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forbidden_returns_403(ec: AsyncClient):
    r = await ec.get("/test/forbidden")
    assert r.status_code == 403
    assert_envelope(r.json(), "forbidden", 403)


@pytest.mark.asyncio
async def test_org_access_denied_returns_403(ec: AsyncClient):
    r = await ec.get("/test/org-access-denied")
    assert r.status_code == 403
    assert_envelope(r.json(), "org_access_denied", 403)


# ---------------------------------------------------------------------------
# 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_not_found_returns_404(ec: AsyncClient):
    r = await ec.get("/test/not-found")
    assert r.status_code == 404
    data = r.json()
    assert_envelope(data, "not_found", 404)
    assert data["details"][0]["resource"] == "Widget"
    # resource_id is serialized as a UUID string (SPEC-007 §7.4 — no PHI).
    assert data["details"][0]["resource_id"] == "00000000-0000-0000-0000-000000000123"


# ---------------------------------------------------------------------------
# 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflict_returns_409(ec: AsyncClient):
    r = await ec.get("/test/conflict")
    assert r.status_code == 409
    assert_envelope(r.json(), "conflict", 409)


@pytest.mark.asyncio
async def test_state_transition_denied_returns_409(ec: AsyncClient):
    r = await ec.get("/test/state-transition-denied")
    assert r.status_code == 409
    data = r.json()
    assert_envelope(data, "state_transition_denied", 409)
    assert data["details"][0]["current_status"] == "signed"
    assert data["details"][0]["target_status"] == "draft"


@pytest.mark.asyncio
async def test_resource_locked_returns_409(ec: AsyncClient):
    r = await ec.get("/test/resource-locked")
    assert r.status_code == 409
    assert_envelope(r.json(), "resource_locked", 409)


# ---------------------------------------------------------------------------
# 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_validation_error_returns_422(ec: AsyncClient):
    r = await ec.get("/test/domain-validation-error")
    assert r.status_code == 422
    assert_envelope(r.json(), "validation_error", 422)


@pytest.mark.asyncio
async def test_bridge_rule_violation_returns_422(ec: AsyncClient):
    r = await ec.get("/test/bridge-rule-violation")
    assert r.status_code == 422
    data = r.json()
    assert_envelope(data, "bridge_rule_violation", 422)
    assert data["details"][0]["expected_type"] == "provider"


@pytest.mark.asyncio
async def test_prerequisite_not_met_returns_422(ec: AsyncClient):
    r = await ec.get("/test/prerequisite-not-met")
    assert r.status_code == 422
    assert_envelope(r.json(), "prerequisite_not_met", 422)


@pytest.mark.asyncio
async def test_pydantic_validation_returns_422_with_field_details(ec: AsyncClient):
    """POST with a missing required field produces {field, message, code} details."""
    r = await ec.post("/test/validation-422", json={})
    assert r.status_code == 422
    data = r.json()
    assert_envelope(data, "validation_error", 422)
    assert len(data["details"]) >= 1
    detail = data["details"][0]
    assert "field" in detail
    assert "message" in detail
    assert "code" in detail


# ---------------------------------------------------------------------------
# 429
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limited_returns_429(ec: AsyncClient):
    r = await ec.get("/test/rate-limited")
    assert r.status_code == 429
    assert_envelope(r.json(), "rate_limited", 429)


# ---------------------------------------------------------------------------
# 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_internal_error_returns_500(ec: AsyncClient):
    r = await ec.get("/test/internal-error")
    assert r.status_code == 500
    assert_envelope(r.json(), "internal_error", 500)


@pytest.mark.asyncio
async def test_global_handler_returns_generic_500_without_internals(ec: AsyncClient):
    """Unhandled exceptions must not leak internal details (SPEC-007 §7.3)."""
    r = await ec.get("/test/unhandled-exception")
    assert r.status_code == 500
    data = r.json()
    assert_envelope(data, "internal_error", 500)
    assert "database is on fire" not in data["message"]
    assert "database is on fire" not in str(data["details"])
    assert data["details"] == []


# ---------------------------------------------------------------------------
# HTTPException coercion (TASK-003 AC: validation, domain, HTTP, unhandled)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_route_returns_standard_envelope_404(ec: AsyncClient):
    """Starlette's default 404 for unknown routes must use the standard envelope."""
    r = await ec.get("/test/definitely-not-a-real-route-xyz")
    assert r.status_code == 404
    assert_envelope(r.json(), "not_found", 404)


@pytest.mark.asyncio
async def test_method_not_allowed_returns_standard_envelope_405(ec: AsyncClient):
    """POST to a GET-only route must return the standard envelope, not `{detail: ...}`."""
    r = await ec.post("/test/bad-request")
    assert r.status_code == 405
    assert_envelope(r.json(), "method_not_allowed", 405)


@pytest.mark.asyncio
async def test_hand_raised_http_exception_uses_standard_envelope(ec: AsyncClient):
    """`raise HTTPException(...)` inside a route must also return the standard envelope."""
    r = await ec.get("/test/http-exception")
    assert r.status_code == 403
    data = r.json()
    assert_envelope(data, "forbidden", 403)
    assert data["message"] == "Custom forbidden message."


# ---------------------------------------------------------------------------
# Validation loc handling (SPEC-007 §7.2 / §7.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pydantic_validation_nested_field_path(ec: AsyncClient):
    """Nested fields are reported dotted without the leading `body` segment."""
    r = await ec.post("/test/validation-422-nested", json={"content": {}})
    assert r.status_code == 422
    data = r.json()
    assert_envelope(data, "validation_error", 422)
    fields = {d["field"] for d in data["details"]}
    assert "content.subjective" in fields, f"expected 'content.subjective' in {fields}"


@pytest.mark.asyncio
async def test_pydantic_validation_query_param_strips_prefix(ec: AsyncClient):
    """Query-param validation strips the `query` prefix from the reported field."""
    r = await ec.get("/test/validation-422-query")  # missing required `limit`
    assert r.status_code == 422
    data = r.json()
    assert_envelope(data, "validation_error", 422)
    fields = {d["field"] for d in data["details"]}
    assert "limit" in fields, f"expected 'limit' in {fields}"
    for f in fields:
        assert not f.startswith("query"), f"prefix not stripped: {f}"


@pytest.mark.asyncio
async def test_pydantic_validation_multiple_errors(ec: AsyncClient):
    """Multiple invalid fields produce multiple `details` entries (SPEC-007 §7.2)."""
    r = await ec.post("/test/validation-422-multi", json={})
    assert r.status_code == 422
    data = r.json()
    assert_envelope(data, "validation_error", 422)
    assert len(data["details"]) >= 3
    fields = {d["field"] for d in data["details"]}
    assert {"name", "age", "email"}.issubset(fields)


@pytest.mark.asyncio
async def test_pydantic_validation_does_not_echo_submitted_value(ec: AsyncClient):
    """Submitted field values must never appear in the error response (SPEC-007 §7.4)."""
    phi_like_value = "phi-sentinel-8f3a2c19-do-not-leak"
    # `name` expects str and we pass an int → Pydantic fails with the value in hand.
    # Actually we want to pass a string value that violates a constraint — use the
    # multi-field body and pass a non-int `age` so the value lands in Pydantic's
    # `input` field. The handler must strip it.
    r = await ec.post(
        "/test/validation-422-multi",
        json={"name": "ok", "age": phi_like_value, "email": "ok@example.com"},
    )
    assert r.status_code == 422
    body = r.text
    assert phi_like_value not in body, (
        "Submitted value leaked into response — SPEC-007 §7.4 PHI safety violation."
    )
