# ADR-013 — Provider-agnostic identity ports

**Date:** 2026-06-11
**Author:** claude-code
**Status:** Proposed

## Context

The auth chain designed in ADR-010/011/012 and decomposed into TASK-014A–J is architecturally sound but mechanically coupled to Auth0: task acceptance criteria name Auth0 JWKS endpoints, Auth0 Management API operations, Auth0 Organizations invitations, and Auth0 Post-Login Actions. We now intend to trial SuperTokens (self-hosted) as the primary provider, with Auth0 retained as a proven fallback. Swapping providers must not touch application code.

The coupling is narrower than it appears. Auth0 holds **zero authorization data** — all RBAC lives in application tables per SPEC-002. Tokens carry only identity (`sub`, org reference, an `is_active` hint). The actual seams are:

1. **Token verification** (hot path — every request)
2. **User provisioning** (cold path — bootstrap, invitations)
3. **Session/refresh revocation** (cold path — force-revoke)
4. **Org provisioning and membership** (cold path — bootstrap, cross-org invites)
5. **Login eligibility propagation** (`Person.is_active` → provider)
6. **Invitation delivery** (who sends the email)

Steps 4–7 of the TASK-014 middleware sequence (Person resolution, PersonRole check, `SET LOCAL app.org_id`, context attach) are already provider-agnostic. Only steps 1–3 (signature, claims, eligibility hint) touch the provider.

ADR-010 mixes two layers that this ADR separates: **policy** (org-scoped tokens, universal WebAuthn MFA, short TTL + refresh rotation with breach detection, nonce-only binding) — binding on any provider — and **mechanism** (Auth0 Organizations, Post-Login Actions, Management API, `app_metadata` mirror) — implementation detail of one adapter.

## Decision

### Two abstract base classes, one value object

Application code depends exclusively on two ports defined in `backend/app/core/identity_ports.py`. One concrete subclass per provider, plus a fake.

```python
class VerifiedIdentity(NamedTuple):
    subject: str               # maps to Person.auth_subject
    provider_org_ref: str      # maps to organizations.auth_provider_org_id
    active_hint: bool | None   # fast-path only; the DB check is authoritative

class TokenVerifier(ABC):
    """Hot path. Called by the auth middleware on every request."""
    @abstractmethod
    async def verify(self, token: str) -> VerifiedIdentity:
        """Full verification: signature (pinned algorithm), iss, aud,
        exp/nbf/iat with bounded leeway, org scope present.
        Raises TokenInvalidError subclasses; never returns partial identity."""

class SignupTicket(NamedTuple):
    url: str                   # embedded in OUR invitation email
    external_ref: str          # provider-side ref, for revocation cleanup

class IdentityProviderAdmin(ABC):
    """Cold path. Called by bootstrap, invitation, and force-revoke services."""
    @abstractmethod
    async def create_user(self, email: str, display_name: str) -> str: ...
    @abstractmethod
    async def set_login_eligibility(self, subject: str, active: bool) -> None: ...
    @abstractmethod
    async def revoke_all_sessions(self, subject: str) -> None: ...
    @abstractmethod
    async def create_org(self, name: str) -> str: ...
    @abstractmethod
    async def add_org_member(self, org_ref: str, subject: str) -> None: ...
    @abstractmethod
    async def create_signup_ticket(self, org_ref: str, email: str, ttl_seconds: int) -> SignupTicket: ...
    @abstractmethod
    async def revoke_signup_ticket(self, external_ref: str) -> None: ...
    @abstractmethod
    async def healthcheck(self) -> bool: ...
```

The split is deliberate: the hot path must stay dependency-light (an HTTP client and a key cache), while the cold path may carry SDK weight, M2M token caches, and retry machinery. A single mega-interface would drag cold-path dependencies into every request.

### Composition root

Provider selection happens in exactly one place. `settings.auth_provider: Literal["fake", "auth0", "supertokens"]` drives a factory in `backend/app/core/dependencies.py` that constructs both port implementations at startup. Routers and services never see a concrete provider type — ADR-009's layering rules (`adr-009-router-no-db-or-auth-args`) already forbid routers from receiving auth objects directly.

Fail-closed guard: the application refuses to start with `auth_provider="fake"` unless the environment is `development` or `test`.

### Capability floor (ADR-010 policy, restated as provider requirements)

Any candidate provider must natively support, or the adapter must refuse to ship:

- **Org-scoped tokens** — the token names the tenant; tokens are not fungible across orgs (Auth0 Organizations / SuperTokens multi-tenancy).
- **Refresh rotation with reuse/breach detection** — no backend revocation list.
- **Universal WebAuthn-capable MFA** — enforced at the provider, fail-closed.
- **5–15 minute access-token TTL.**

A provider that cannot meet the floor is not made to "work" by weakening the floor in the adapter.

### Invitation lifecycle is fully application-owned

ADR-010 chose Auth0's native organization-invitation emails; its rejected alternative (backend-driven invitations) is the only design that generalizes — SuperTokens has no invitation primitive at all. Amended position:

- The backend owns the `Invitation` row, the nonce, the state machine (ADR-011 unchanged), **and the email** (TASK-014D provides delivery).
- The provider's only invitation role is `create_signup_ticket` → a URL the invitee uses to establish credentials, embedded in our email. The Auth0 adapter implements this with Management API invitation tickets (provider email suppressed); the SuperTokens adapter with a tenant-scoped signup URL.
- ADR-011's `auth0_invitation_id` column is renamed `external_invitation_id` and stores `SignupTicket.external_ref`.

### Login eligibility propagation

`identity_service` calls `set_login_eligibility(subject, active)` on every Person activation/deactivation/soft-delete, in the same transaction discipline the former Post-Login Actions task specified (rollback on permanent provider failure). How the adapter honors it is mechanism: Auth0 mirrors to `app_metadata.is_active` read by a Post-Login Action; SuperTokens denies session refresh in-process. Either way the DB remains authoritative on every request (middleware step 4).

### Testing: three tiers, no provider mocks

The standing rule "auth-chain tests hit a real provider, never a mock" is preserved and generalized:

1. **Application tests** run against `FakeIdentityProvider` — a real, complete port implementation (in-memory), not a mock of HTTP calls.
2. **Conformance suite** (TASK-014C): one parametrized test suite asserting port semantics, run against the fake, against a real SuperTokens core in Docker (CI), and against the live Auth0 test tenant (marked, on-demand). An adapter that cannot pass conformance does not ship.
3. **E2E smoke** against the deployed provider per environment.

SPEC-007 §13.4 ("no real Auth0 calls in tests") is superseded by this section and must be amended.

## Consequences

**For:**

- Provider swap is a config change. The SuperTokens-vs-Auth0 decision stops blocking application work: middleware, bootstrap, invitations, and force-revoke build and test against the ports + fake.
- The `TokenVerifier` extraction is the same refactor as the open security fixes (missing `exp`/`nbf`/`iat` validation, missing `iss`/`aud` on the accept path, no algorithm pinning) — one move closes both.
- Two real adapters + the conformance suite keep the interface honest; an abstraction validated against one implementation is a guess.
- HIPAA surface shrinks under self-hosted SuperTokens (identity data stays in our Postgres); the Auth0 adapter remains the escape hatch.

**Against:**

- More moving parts: two ports, three implementations, a conformance suite, an email-delivery dependency that Auth0 used to provide for free.
- Leak risk at the invitation seam: signup-ticket semantics differ per provider (TTL behavior, single-use guarantees). The conformance suite must pin these explicitly.
- The capability floor means we cannot adopt a cheaper provider that lacks, e.g., breach detection, without revisiting ADR-010 policy — that is intentional friction.
- Maintaining the Auth0 adapter alongside SuperTokens is ongoing cost; if the SuperTokens trial succeeds, a follow-up decision may demote Auth0 to unmaintained-reference status.

## Alternatives considered

**Status quo (direct Auth0 SDK/HTTP throughout).** Rejected: provider swap becomes a rewrite of middleware, bootstrap, invitations, and force-revoke; testing requires a cloud tenant forever.

**Single combined interface.** One `IdentityProvider` ABC with all methods. Rejected: hot path inherits cold-path dependency weight; adapters that only need verification (e.g., a future read-only service) implement dead methods.

**Per-route provider selection (wrapper chosen in routers).** Rejected: violates `adr-009-router-no-db-or-auth-args`, scatters the swap decision across the codebase, and makes "which provider is live" ambiguous per request.

**Keep provider-native invitations behind a port method (`send_invitation`).** Rejected: SuperTokens cannot implement it; the port would have a method only one adapter supports — the definition of a leaky abstraction. Email ownership moves to the application instead.

**HTTP-level fake (mock server emulating Auth0 endpoints).** Rejected: emulates one provider's wire format rather than the port contract; breaks on every Auth0 API change and proves nothing about SuperTokens.

## Phased plan

- [ ] Epic 1: TASK-014B implements the ports, exceptions, settings, and composition root.
- [ ] Epic 2: TASK-014C implements `FakeIdentityProvider` and the conformance suite; amends SPEC-007 §13.4.
- [ ] Epic 3: TASK-014 (middleware), 014E, 014F, 014G, 014J build against the ports; the former Post-Login Actions and Management API tasks are absorbed into the Auth0 adapter (014N), with the port contract they implement defined in 014B.
- [ ] Epic 4: TASK-014K deploys the SuperTokens core (docker-compose); TASK-014L implements the SuperTokens adapter; TASK-014N reshapes the existing Auth0 client into the Auth0 adapter.
- [ ] Epic 5: TASK-014D implements invitation email delivery.
- [ ] Epic 6: SPEC-007 §3 and §13.4 amended to provider-neutral language.

## References

- ADR-009 — layering rules that keep routers provider-blind.
- ADR-010 — auth policy (capability floor source); its mechanism sections become adapter detail per this ADR.
- ADR-011 — invitation lifecycle (state machine unchanged; email ownership and `external_invitation_id` amended here).
- ADR-012 — permission cache invalidation (fully provider-agnostic; untouched).
- SPEC-002 — RBAC is application-owned; the provider holds zero authorization data.
- SPEC-007 §3, §13.4 — auth flow and test philosophy (both to be amended).
- `auth-abstraction-review.md`, `supertokens-evaluation.md` — analysis behind this ADR.
