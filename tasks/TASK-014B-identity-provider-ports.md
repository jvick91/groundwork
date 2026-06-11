# TASK-014B: Identity Provider Ports & Composition Root

**Status:** Not started
**Spec sections:** SPEC-007 §3 (auth flow), SPEC-002 §4 (auth subject rule)
**ADRs:** ADR-009 (layering), ADR-013 (identity provider ports — must be Accepted before this task starts)
**Depends on:** TASK-014A

## Objective

Define the provider-agnostic contracts everything else in the auth chain compiles against: the `TokenVerifier` and `IdentityProviderAdmin` abstract base classes, the `VerifiedIdentity` and `SignupTicket` value objects, the provider-neutral exception hierarchy, and the composition root that selects the live provider from settings. **No provider code in this task** — concrete adapters are TASK-014L (SuperTokens) and TASK-014N (Auth0); the fake is TASK-014C.

## Acceptance Criteria

- [ ] `backend/app/core/identity_ports.py` defines `TokenVerifier`, `IdentityProviderAdmin`, `VerifiedIdentity`, `SignupTicket` exactly per ADR-013 §Decision
- [ ] `TokenVerifier.verify` contract documented in the docstring: pinned signature algorithm, `iss`, `aud`, `exp`/`nbf`/`iat` with bounded leeway, org scope required — adapters that skip any of these fail conformance (TASK-014C)
- [ ] Provider-neutral exceptions added to `backend/app/core/exceptions.py`: `TokenInvalidError` (base, → 401), `TokenExpiredError`, `OrgScopeMissingError`, `IdentityProviderError` (cold path, → 502); all `GroundworkError` subclasses
- [ ] `settings.auth_provider: Literal["fake", "auth0", "supertokens"]` added to `backend/app/core/config.py`; no default in production — unset is a startup error
- [ ] Factory in `backend/app/core/dependencies.py` constructs both port implementations once at startup from `settings.auth_provider`; FastAPI dependencies expose `get_token_verifier` and `get_identity_provider_admin`
- [ ] Fail-closed guard: startup raises if `auth_provider == "fake"` and environment is not `development` or `test`
- [ ] No module-level mutable state (`adr-009-no-module-state`); the factory product lives on app state, not a module global
- [ ] Routers never import the ports or adapters directly (`adr-009-router-no-db-or-auth-args` extended: provider types appear only in `core/` and `services/identity_providers/`)
- [ ] Tests: `test_factory_selects_provider_from_settings`, `test_fake_provider_refused_outside_dev_test`, `test_unset_provider_fails_startup`

## Files

- `backend/app/core/identity_ports.py` (new)
- `backend/app/core/exceptions.py` (add provider-neutral exceptions)
- `backend/app/core/config.py` (`auth_provider` setting)
- `backend/app/core/dependencies.py` (factory + dependencies)
- `backend/tests/test_auth/test_provider_factory.py`

## Non-goals

- Any concrete adapter (TASK-014L, TASK-014N)
- The fake implementation and conformance suite (TASK-014C)
- The middleware that consumes `TokenVerifier` (TASK-014)
