# TASK-014M: SuperTokens Core Deployment & Environment Doc

**Status:** Not started
**Spec sections:** SPEC-007 §3 (auth flow)
**ADRs:** ADR-013 (capability floor this deployment must satisfy)
**Depends on:** TASK-014A

## Objective

Stand up the self-hosted SuperTokens core as infrastructure: docker-compose service for local dev and CI, database schema (SuperTokens runs against its own Postgres database, separate from the application schema), license-key handling for the paid features (multi-tenancy, MFA), and an operational runbook. This is the SuperTokens counterpart of TASK-014B (Auth0 tenant configuration) — pure provider-side setup, no application code beyond config plumbing.

**Pre-task gate (from `supertokens-evaluation.md`):** before implementation starts, the three open items must be resolved — multi-tenancy add-on pricing (contact sales), license/telemetry behavior in a self-hosted HIPAA deployment, and passkeys-as-MFA production-readiness in the Python SDK. If any of these fails, this task and TASK-014N are dropped and the Auth0 adapter (TASK-014O) remains primary.

## Acceptance Criteria

- [ ] `docker-compose` service for the SuperTokens core added to the dev stack; core connects to a dedicated `supertokens` Postgres database (never the application database)
- [ ] CI compose profile brings up the core for the conformance suite's `supertokens` marker (TASK-014L)
- [ ] Multi-tenancy and MFA features enabled via license key; key supplied through env (`SUPERTOKENS_LICENSE_KEY`), never committed
- [ ] Capability floor verified against the running core and documented: tenant-scoped sessions, refresh rotation with theft detection, WebAuthn-capable MFA, 5–15 min access-token TTL (ADR-013 §Capability floor)
- [ ] `backend/app/core/config.py` settings added: `supertokens_connection_uri`, `supertokens_api_key`; `.env.backend.example` updated (no real secrets)
- [ ] `/health/ready` readiness probe for the core wired through the provider `healthcheck()` port method when `auth_provider=supertokens`
- [ ] Operational runbook `docs/supertokens-setup.md`: compose usage, license provisioning, tenant creation, upgrade procedure, backup expectations, telemetry/phone-home findings from the pre-task gate
- [ ] Doc states the ops tradeoff accepted in `supertokens-evaluation.md`: we own patching, availability, and breach response for the core

## Files

- `docker-compose.yml` (supertokens core service + dedicated database)
- `backend/app/core/config.py` (settings)
- `.env.backend.example`
- `docs/supertokens-setup.md` (new — runbook)

## Non-goals

- The adapter code consuming this deployment (TASK-014N)
- Auth0 tenant configuration (TASK-014B — unchanged, scoped to the Auth0 adapter)
- Production hosting topology (MVP targets dev/CI; prod deployment is an infra follow-up)
