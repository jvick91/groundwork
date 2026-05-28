# Auth0 Post-Login Actions — Failure-Mode Contract & Staleness Window

**TASK**: TASK-014C  
**ADR**: ADR-010 §4 (Identity Lifecycle Events)  
**Last updated**: 2026-05-27

---

## Overview

The Post-Login Action (`auth0/post-login-action.js`) runs inside Auth0 after
every successful authentication, before the JWT is issued. It is the
**last** fail-closed gate before the user receives tokens.

The backend (`Auth0SyncService`) is the **write path**: it pushes state changes
(deactivate, soft-delete) to `app_metadata`. The Action is the **read path**:
it gates on what is already there.

---

## What the Action Does

| Order | Gate / Step | Fail Behaviour |
|-------|------------|----------------|
| 1 | Email verification | `api.access.deny()` — no token issued |
| 2 | `app_metadata.is_active` check | `api.access.deny()` — no token issued |
| 3 | Enrich JWT with `org_id`, `is_active` | Skip enrichment if org is absent |

---

## Staleness Window

`app_metadata` is **not a real-time state store**. There is a bounded window
during which the Action's decision can lag behind the authoritative DB row.

### Activation (Person created → `is_active: true` pushed)

1. Backend creates Person row: `is_active = true`.
2. `PersonService.create()` does **not** call `Auth0SyncService` — the person has no
   `auth_subject` yet at creation time (Auth0 user is created first via
   the invitation flow, which sets `app_metadata.is_active = false` by default).
3. When the invitation is accepted and the backend webhook processes it, it calls
   `Auth0SyncService.sync_person_status(auth_subject, is_active=True)`.
4. From that point the user can log in.

**Maximum activation lag**: Negligible — the sync happens synchronously before
the 201 response returns to the caller.

### Deactivation (Person.is_active → False or soft-deleted)

1. Backend writes `is_active = false` / `deleted_at` to the DB.
2. `PersonService.update()` / `PersonService.delete()` calls
   `Auth0SyncService.sync_person_status(auth_subject, is_active=False)` **within
   the same DB transaction**.
3. If the Management API call succeeds, the DB transaction commits and `app_metadata`
   is updated atomically (from the caller's perspective).
4. On next login attempt, the Action reads `app_metadata.is_active = false` and denies.

**Maximum deactivation lag for new logins**: Near-zero (sync is transactional).

**Existing access tokens remain valid** until their TTL expires (configured to
15 minutes via the Auth0 API settings — see `auth0-tenant-setup.md`).  
For immediate revocation of an already-issued token, use the force-kill flow
(TASK-014J): delete the Auth0 session + revoke the refresh-token family via the
Management API.

---

## Failure Modes

### Management API unreachable during deactivation

If all retry attempts in `Auth0ManagementService._request` are exhausted,
`Auth0ManagementError` (HTTP 502) propagates up through `PersonService` and
**rolls back the DB transaction**. The Person row remains active in the DB,
and `app_metadata` is unchanged — the two sides stay consistent.

The API caller receives a `502 Bad Gateway`. The correct operator response is
to retry the deactivation request once Auth0 is reachable.

### `app_metadata.is_active` missing (new or migrated user)

The Action treats `missing`, `null`, and `false` identically: deny.  
New Auth0 users provisioned through TASK-014F/G have `is_active` explicitly
set to `true` in `app_metadata` during the invitation-acceptance webhook before
the first login is possible.

Legacy users (created before TASK-014C) will be locked out until a one-time
migration script populates their `app_metadata`. Run:

```bash
# backend/scripts/migrate_app_metadata.py  (TASK-014K — not yet written)
# Sets app_metadata.is_active = <Person.is_active> for every Person
# that has an auth_subject but lacks the claim.
```

### Post-Login Action itself crashes (unhandled exception)

Auth0's default behaviour when an Action throws an unhandled error is to
**block the login** (fail-closed). This is the desired behaviour. Errors are
visible in Auth0 Dashboard → Monitoring → Logs with `feacft` / `fepft` codes.

### Org-tagless login (direct API call, no organization context)

If `event.organization` is null, the Action skips `org_id` enrichment. The
backend middleware (`AuthMiddleware`) will then reject the token with
`403 missing_org_id` on any API call that requires an org context. The token
is issued but immediately unusable — this is by design (ADR-010 §2).

---

## Deployment Instructions

1. Auth0 Dashboard → **Actions → Library → Create Action → Post Login**.
2. Paste the contents of `auth0/post-login-action.js`.
3. Click **Deploy**.
4. Go to **Actions → Flows → Login**.
5. Drag the action into the flow between "Start" and "Complete".
6. Click **Apply**.

To update an existing deployed Action:
1. Open the Action in the Library.
2. Edit and click **Deploy** — this creates a new draft version.
3. The flow uses the latest deployed version automatically (no flow re-save needed
   once the action is in the flow).

---

## Testing the Action

Auth0 provides a built-in Action test panel (top-right "Test" button) where you
can simulate `event` payloads without triggering a real login. Use the following
cases:

| Scenario | event.user.email_verified | app_metadata.is_active | event.organization | Expected result |
|----------|--------------------------|----------------------|--------------------|-----------------|
| Happy path | `true` | `true` | `{id: "org_xxx"}` | Token issued with `org_id`, `is_active: true` |
| Unverified email | `false` | `true` | any | Denied — email not verified |
| Inactive person | `true` | `false` | any | Denied — account inactive |
| Missing is_active | `true` | _(absent)_ | any | Denied — treated as inactive |
| No org context | `true` | `true` | `null` | Token issued, no `org_id` claim |

---

## Related Tasks

| Task | Description |
|------|-------------|
| TASK-014 | JWT middleware — reads `is_active` + `org_id` from token |
| TASK-014B | Auth0 tenant setup — API token TTL, MFA policy |
| TASK-014D | Auth0 Management API client — powers the sync write path |
| TASK-014J | Force-kill: immediate session + refresh-token revocation |
| TASK-014K | One-time migration of `app_metadata` for legacy users |
