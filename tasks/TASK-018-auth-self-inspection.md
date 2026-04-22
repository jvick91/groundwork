# TASK-018: Auth Self-Inspection Endpoints

**Status:** Not started
**Spec sections:** SPEC-002 §8 (Auth self-inspection); SPEC-007 §3.4 (/auth/me response), §3.5 (/auth/me/permissions response)
**ADRs:** —
**Depends on:** TASK-014, TASK-015

## Objective

Implement `/auth/me` and `/auth/me/permissions` — the two self-inspection endpoints that let the frontend discover who the current user is, what organizations they belong to, and what permissions they have in the current org context.

## Acceptance Criteria

- [ ] `GET /api/v1/auth/me` returns person profile + all organizations with roles per SPEC-007 §3.4
- [ ] `/auth/me` does NOT require `X-Organization-Id` header per SPEC-002 §8
- [ ] `/auth/me` response shape: `{person: {id, first_name, last_name, email}, organizations: [{id, name, roles: [{role_slug, role_name, primary_domain, entity_instance_id}]}]}`
- [ ] `entity_instance_id` in each role entry is nullable — null for roles whose primary_domain has no EAV profile binding (e.g., system_admin) per SPEC-002 §2
- [ ] `GET /api/v1/auth/me/permissions` returns effective permission list for current org per SPEC-007 §3.5
- [ ] `/auth/me/permissions` requires `X-Organization-Id` header
- [ ] `/auth/me/permissions` response shape: `{organization_id, permissions: [{slug, resource, action, conditions}]}`
- [ ] Both endpoints require only `authenticated` — no specific permission slug
- [ ] Tests: verify response shapes, multi-org person sees all orgs, permissions include inherited grants

## Files

- `backend/app/schemas/auth.py` (response schemas)
- `backend/app/routers/auth.py` (auth endpoints)
- `backend/app/services/auth_service.py` (resolution logic)
- `backend/tests/test_auth/test_self_inspection.py`

## Non-goals

- Auth0 login/callback flow (frontend concern)
- Token generation (Auth0 handles this)
