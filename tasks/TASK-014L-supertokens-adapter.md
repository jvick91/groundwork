# TASK-014L: SuperTokens Adapter

**Status:** Not started
**Spec sections:** SPEC-007 §3 (auth flow)
**ADRs:** ADR-009 (layering), ADR-013 (ports this adapter implements)
**Depends on:** TASK-014B, TASK-014C, TASK-014K

## Objective

Implement the SuperTokens subclasses of both ports using `supertokens-python` against the dockerized core from TASK-014K. The adapter maps the port contract onto SuperTokens primitives: tenant-scoped session verification → `TokenVerifier`, multi-tenancy/user-management SDK functions → `IdentityProviderAdmin`. Proof of correctness is the TASK-014C conformance suite passing under the `supertokens` marker — no adapter-specific test conventions.

## Acceptance Criteria

- [ ] `backend/app/services/identity_providers/supertokens.py` — `SuperTokensTokenVerifier(TokenVerifier)` and `SuperTokensProviderAdmin(IdentityProviderAdmin)`, class-per-aggregate per ADR-009; constructor injects config + SDK handles
- [ ] `verify()` performs full validation per the ADR-013 contract (signature with pinned algorithm, `iss`, `aud`, `exp`/`nbf`/`iat` with bounded leeway) and maps the SuperTokens tenant ID claim to `VerifiedIdentity.provider_org_ref`; missing tenant scope raises `OrgScopeMissingError`
- [ ] Port method mapping implemented: `create_user`, `create_org` (tenant), `add_org_member` (tenant association), `revoke_all_sessions`, `set_login_eligibility` (refresh-denial mechanism — session refresh for an ineligible subject is refused in-process; document the mechanism in the module docstring), `create_signup_ticket` / `revoke_signup_ticket` (tenant-scoped credential-setup URL with TTL and single-use semantics), `healthcheck` (core liveness)
- [ ] SDK/core errors map to the ADR-013 exception hierarchy; transient core failures retry with exponential backoff before raising `IdentityProviderError`
- [ ] Conformance suite (TASK-014C) passes under the `supertokens` marker in CI against the dockerized core
- [ ] No SuperTokens imports anywhere outside this module and the TASK-014B factory
- [ ] Capability-floor assertions from TASK-014K re-verified through the adapter: org-scoped session rejected against the wrong tenant, refresh-reuse triggers family revocation

## Files

- `backend/app/services/identity_providers/supertokens.py` (new)
- `backend/app/core/dependencies.py` (register in factory)
- `backend/pyproject.toml` (`supertokens-python` dependency)
- `backend/tests/conformance/conftest.py` (supertokens adapter fixture)

## Non-goals

- Core deployment/licensing (TASK-014K)
- Frontend SDK integration (frontend scope, separate track)
- Invitation email delivery (TASK-014D)
