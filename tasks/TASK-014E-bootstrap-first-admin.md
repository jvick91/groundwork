# TASK-014E: Bootstrap First Admin

**Status:** Shipped
**Spec sections:** SPEC-007 §3 (auth flow), SPEC-002 §8 (Person management)
**ADRs:** ADR-008 Epic 4 (resolves the cold-start gap), ADR-010, ADR-013
**Depends on:** TASK-014D

## Objective

One-shot operator CLI script that provisions the first `Organization`, first `Person`, first `PersonRole(system_admin)`, plus the corresponding Auth0 Organization, Auth0 user, and Auth0 Org membership. Run via `docker exec` / `kubectl exec`. Gated by a deploy-time provisioning token file at a known path on disk; the script validates the token against the file and **deletes the file on success**. No env-var fallback — env vars persist and would allow re-bootstrap.

Delivery via script (not HTTP endpoint) per ADR-013: shell access to the container is the natural capability gate, and avoids adding an unauthenticated HTTP surface.

The bootstrap transaction spans both the application DB and Auth0. The two sides must succeed together; failure leaves the marker file in place so the operator can retry without leaving a half-provisioned tenant.

## Acceptance Criteria

- [x] CLI script `backend/scripts/bootstrap.py` accepts org name, display name, admin name/email, and token file path as arguments
- [x] Token validation reads from `--token-file` arg (defaults to `/var/run/groundwork/bootstrap.token`); constant-time comparison
- [x] Script exits 1 with clear error if the marker file does not exist
- [x] Script exits 1 with "Token mismatch" if the supplied token does not match the file
- [x] Script exits 1 with error message if any `Person` already exists (defensive guard — enforced by `BootstrapService`)
- [x] On success: creates `Organization`, `Person`, `PersonRole(system_admin)`, Auth0 Organization, Auth0 user, and Auth0 Org membership — two-phase saga
- [x] On success: deletes the marker file before returning
- [x] On any failure (DB or Auth0 side): rolls back DB; compensating Auth0 calls issued; marker file not deleted
- [x] Output includes the bootstrapped Person's Auth0 user ID and the password-change ticket URL
- [x] Writes `AuditLog` row with `action='system.bootstrap'`, `actor_person_id` = newly-created Person (self-attributed)

## Files

- `backend/scripts/bootstrap.py` (new — CLI wrapper around BootstrapService)
- `backend/app/services/bootstrap_service.py` (new — two-phase saga, compensating calls)
- `backend/app/services/auth0_management_service.py` (extended: `delete_user`, `delete_organization`, `create_password_change_ticket`)

## Usage

```bash
# 1. Generate and write a token
python -c "import secrets; print(secrets.token_urlsafe(32))" \
    > /var/run/groundwork/bootstrap.token

# 2. Run the script inside the container
docker exec -it groundwork-backend python scripts/bootstrap.py \
    --org-name "acme" \
    --org-display-name "Acme Corp" \
    --admin-first "Alice" \
    --admin-last "Admin" \
    --admin-email "alice@acme.com"
# Token is prompted interactively (avoids shell history)
```

## Non-goals

- Invitation flow (TASK-014F)
- Routine admin creation post-bootstrap (use TASK-014F invitations)
- HTTP endpoint for bootstrap (see ADR-013 — script approach was chosen)
