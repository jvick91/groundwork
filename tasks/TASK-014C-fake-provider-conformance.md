# TASK-014C: Fake Identity Provider & Adapter Conformance Suite

**Status:** Not started
**Spec sections:** SPEC-007 §13 (test philosophy — §13.4 amended by this task)
**ADRs:** ADR-013 §Testing
**Depends on:** TASK-014B

## Objective

Ship `FakeIdentityProvider` — a real, complete in-memory implementation of both ports, not an HTTP mock — and the parametrized conformance suite that every adapter (fake, SuperTokens, Auth0) must pass. The fake is what lets all application-layer auth tasks (014, 014E, 014F, 014G, 014J) build and test before any concrete provider exists. The conformance suite is what keeps the port honest: if a real provider cannot implement a behavior the fake exhibits, the port is wrong and this surfaces immediately.

Testing policy per ADR-013: application tests run against the fake; conformance runs against the fake always, against a SuperTokens core in Docker in CI (TASK-014K), and against the live Auth0 test tenant on-demand (marked). **No provider HTTP mocks anywhere.**

## Acceptance Criteria

- [ ] `backend/app/services/identity_providers/fake.py` implements `TokenVerifier` and `IdentityProviderAdmin` fully in-memory: signed test tokens (local RSA keypair, full claim validation — the fake must *reject* expired/`nbf`-violating/wrong-`aud` tokens, not skip the checks), users, orgs, memberships, signup tickets with TTL and single-use semantics, session revocation, login eligibility
- [ ] Fake provides test helpers to mint valid/expired/claim-stripped tokens for any (subject, org) pair — replaces TASK-008's standalone JWT key fixture as the canonical test-token source
- [ ] Conformance suite `backend/tests/conformance/test_identity_provider_conformance.py` parametrized over adapter fixtures; covers per port method: happy path, idempotency/conflict semantics, TTL expiry, single-use ticket enforcement, revocation visibility, error mapping to the ADR-013 exception hierarchy
- [ ] Conformance markers: fake (default, always), `supertokens` (CI, requires dockerized core), `auth0_live` (on-demand, requires tenant credentials); unmarked runs never touch the network
- [ ] SPEC-007 §13.4 amended: "no real Auth0 calls in tests" → "no provider mocks; application tests use the fake port, adapter correctness is proven by the conformance suite against real providers"
- [ ] Tests: the conformance suite itself passing against the fake is this task's proof; plus `test_fake_minted_token_verifies`, `test_fake_expired_token_rejected`, `test_fake_ticket_single_use`

## Files

- `backend/app/services/identity_providers/__init__.py` (new package)
- `backend/app/services/identity_providers/fake.py` (new)
- `backend/tests/conformance/__init__.py`
- `backend/tests/conformance/test_identity_provider_conformance.py` (new)
- `backend/tests/conftest.py` (adapter fixtures + markers)
- `specs/SPEC-007-api-contract-and-testing.md` (§13.4 amendment)

## Non-goals

- SuperTokens and Auth0 adapter fixtures' underlying implementations (TASK-014L, TASK-014N — they plug into this suite)
- CI wiring for the dockerized SuperTokens core (TASK-014K)
