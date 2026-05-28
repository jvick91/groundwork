# TASK-014D: Auth0 Management API Integration

**Status:** Shipped
**Spec sections:** SPEC-007 §3 (auth flow)
**ADRs:** ADR-010
**Depends on:** TASK-014B

## Objective

Implement the backend's Auth0 Management API client: M2M credentials, token caching with refresh, retry/backoff for transient failures, and a typed wrapper around the operations downstream tasks need. Used by TASK-014C (`app_metadata.is_active` sync), TASK-014E (bootstrap user + Auth0 Org creation), TASK-014F (Auth0 organization invitation, Auth0 user creation, Org membership management), and TASK-014J (session/refresh-family revocation).

## Acceptance Criteria

- [ ] `backend/app/services/auth0_management_service.py` — class-per-aggregate `Auth0ManagementService` per ADR-009; constructor injects HTTP client and config
- [ ] Management API token acquired via Client Credentials grant against the management audience configured in TASK-014B
- [ ] Token cached in-process with TTL aligned to Auth0's token lifetime; refreshed automatically on expiry or 401 from API
- [ ] Wrapped operations (each a service method): create user, get user, update `app_metadata`, delete sessions, revoke refresh tokens, create organization, add organization member, remove organization member, create organization invitation, revoke organization invitation
- [ ] Retry with exponential backoff for 429 and 5xx; permanent failure raises a `GroundworkError` subclass (`Auth0ManagementError`)
- [ ] All Management API operations write `AuditLog` entries when invoked by a state-changing service method (the calling service is responsible for the audit row; the Management API client itself is audit-agnostic)
- [ ] Tests: mock the Auth0 HTTP layer; verify retry behavior, token refresh on 401, error propagation
- [ ] No real Auth0 calls in tests (per SPEC-007 §13.4)

## Files

- `backend/app/services/auth0_management_service.py`
- `backend/app/core/exceptions.py` (add `Auth0ManagementError`)
- `backend/tests/test_auth/test_management_api.py`

## Non-goals

- The Post-Login Action sync webhook itself (TASK-014C consumes this client)
- Bootstrap flow (TASK-014E consumes this client)
- Invitation flow (TASK-014F consumes this client)
- Force-kill endpoint (TASK-014J consumes this client)
