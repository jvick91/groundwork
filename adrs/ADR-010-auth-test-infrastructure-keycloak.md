# ADR-010 — Auth test infrastructure: containerized Keycloak

**Date:** 2026-05-19
**Author:** claude-code
**Status:** Proposed

## Context

SPEC-007 §13.4 (as shipped) chose **Pattern 1 — local in-process keypair** for
testing the auth middleware: `tests/fixtures/jwt_keys.py` generates an RSA
keypair per pytest process, mints tokens with the private key, and the
middleware is configured (via the
`settings.auth_jwt_static_public_key_pem` field) to validate against the
matching public key. No external dependency, no network calls, no
credentials in CI.

TASK-014's first implementation (this PR) followed that design. During
implementation two operational constraints surfaced from the project owner
that the original spec did not anticipate:

1. **No mocks in tests.** "Mock" here is read broadly — not just
   `unittest.mock` test doubles, but any test-only seam that lets test
   code substitute behavior for production code.
2. **No `monkeypatch` of `settings`.** Even direct attribute assignment
   to the global `Settings` instance is undesired, on the grounds that it
   couples the test suite to mutable global state and obscures the test
   shape.

Read together, these are stricter than SPEC-000 §5 ("no mocks"). The
in-process keypair design **does not** technically violate either: the
`JWKSResolver` has a real production-shipping static-PEM mode, the
keypair is real, the JWTs are real, and no code is replaced. But
*configuring* the test to use that mode requires either:

- runtime mutation of `settings.auth_jwt_static_public_key_pem` (a
  `monkeypatch`), or
- creating a parallel `Settings` instance for tests (filesystem coupling
  to `.env.test` + chicken-and-egg with the per-process keypair), or
- swapping the `JWKSResolver` via FastAPI dependency override (still a
  test-only seam).

All three feel mock-adjacent to the project owner. The cleaner path is
to run a **real OAuth/OIDC identity provider** as part of the test
infrastructure — so tests fetch real tokens from a real
`/oauth/token` endpoint, validated against a real `/.well-known/jwks.json`
served by a real signing service. No test-only configuration paths.

The remaining decision is *which* IdP. We surveyed four patterns:

| Pattern | IdP source | External dependency | Negative-path token minting |
|---|---|---|---|
| 1 — Local keypair (shipped spec) | In-process Python | None | Trivial (mint with custom claims) |
| 2 — Hybrid: keypair bulk + 1 live Auth0 smoke | Auth0 cloud | Yes (smoke only) | Trivial for the keypair half |
| 3 — Full Auth0 sandbox | Auth0 cloud | Yes (every test) | Hard (need second tenant for wrong-audience, real expiry for expired) |
| 4 — Containerized Keycloak | Self-hosted in docker-compose | None | Configurable per realm |

Pattern 1 is the FastAPI / `auth0-python-samples` convention. Pattern 3
is the most "live" but is also the most operationally fragile. Pattern 4
gives us a real OAuth/OIDC flow without external dependencies, without
secrets in CI, without rate limits, and with the negative-path
controllability that SPEC-002 §11 tests require.

## Decision

**Use Keycloak running as a docker-compose service for all auth tests.**

The test infrastructure shifts from "in-process JWT mint + static PEM
config" to "real OAuth flow against a real (containerized) IdP." The
backend's `JWKSResolver` validates tokens against Keycloak's
`/.well-known/jwks.json` exactly the same way it would validate against
Auth0 in production. Only the JWKS URL changes per environment.

### Test stack

`docker-compose.yml` gains a `keycloak` service:

```yaml
keycloak:
  image: quay.io/keycloak/keycloak:26.0
  command: ["start-dev", "--import-realm"]
  environment:
    KC_BOOTSTRAP_ADMIN_USERNAME: admin
    KC_BOOTSTRAP_ADMIN_PASSWORD: admin
    KC_HEALTH_ENABLED: "true"
  ports:
    - "8081:8080"
  volumes:
    - ./docker/keycloak/realm-groundwork-test.json:/opt/keycloak/data/import/realm-groundwork-test.json:ro
  healthcheck:
    test: ["CMD-SHELL", "exec 3<>/dev/tcp/localhost/8080 && echo OK"]
    interval: 5s
    timeout: 3s
    retries: 30
```

A realm import JSON (`docker/keycloak/realm-groundwork-test.json`) is
committed to the repo. It defines:

- One realm: `groundwork-test`
- One API resource: `https://api.groundwork.test/` (matches the existing
  `TEST_AUDIENCE` constant so SPEC-007 §3 issuer/audience semantics are
  preserved)
- One confidential client with client-credentials enabled (for
  service-to-service token minting in tests)
- A handful of pre-seeded test users with deterministic `sub` claims
  (e.g. `keycloak|alice`, `keycloak|bob`) so the `tests/factories/identity.py`
  factories can pre-create matching `Person.auth_subject` rows
- A second realm `groundwork-test-wrong-aud` for the wrong-audience
  negative-path test
- A second client with `accessTokenLifespan: 1` (one second) for the
  expired-token negative-path test

### Test configuration

Backend test settings:

```bash
AUTH_STUB_ENABLED=false
AUTH0_DOMAIN=keycloak-test:8080/realms/groundwork-test
AUTH0_ISSUER=http://keycloak-test:8080/realms/groundwork-test
AUTH0_AUDIENCE=https://api.groundwork.test/
# AUTH_JWT_STATIC_PUBLIC_KEY_PEM left empty — JWKSResolver fetches from Keycloak
```

The `JWKSResolver` Auth0-mode path is exercised end-to-end. The
static-PEM mode survives in production code for any future deployment
that uses a different IdP, but it is no longer used by the test suite.

### Conftest fixtures

Replace the existing `auth_environment` / `auth_client` / `make_token`
fixtures with:

- `keycloak_token_factory` — session-scoped factory that talks to the
  Keycloak `/realms/groundwork-test/protocol/openid-connect/token`
  endpoint via `httpx`. Tokens are cached for their TTL minus 10 seconds.
- `keycloak_test_user_token(username)` — function-scoped fixture for
  per-user tokens via `password` grant.
- `auth_client` — the existing async test client, unchanged shape.
- `expired_token` — fetches from the short-lifespan realm + sleeps the
  required interval; cached per session.
- `wrong_audience_token` — fetches from the `groundwork-test-wrong-aud`
  realm.

`tests/fixtures/jwt_keys.py` is removed.

### Negative-path test strategy

| AC | Implementation under Keycloak |
|---|---|
| missing token | Send request without `Authorization` header |
| malformed token | Send a hand-crafted bogus string |
| invalid signature | Take a real Keycloak token and flip a byte in the signature segment |
| expired token | Use the short-lifespan realm/client; mint once, sleep, send |
| wrong audience | Use the second realm whose API resource is a different audience |
| wrong issuer | Use the second realm (different `iss`) |
| token without sub | Configure a client mapper that strips `sub` (Keycloak supports this) — or hand-craft a token signed by the real Keycloak key but with claims rewritten (separate from a tampered signature) |

The expired-token test has the only timing dependency. Keep it under one
session by using the short-lifespan client + a single sleep — not
per-test.

## Consequences

**For:**

- Tests exercise the **same code path** production will exercise:
  `JWKSResolver` fetches from a real JWKS endpoint, validates real
  Keycloak-signed JWTs, against a real OAuth issuer.
- No test-only configuration of `settings.auth_jwt_static_public_key_pem`.
  No `monkeypatch`. No FastAPI dependency override for the resolver.
- No secrets in CI. No external network egress required for tests. No
  rate limits.
- Negative-path tokens (expired, wrong-audience, wrong-issuer) become
  first-class — minted by real Keycloak realms with documented config.
  Far closer to "production-shape failure" than locally-fabricated
  invalid JWTs.
- The static-PEM mode in `JWKSResolver` remains as production code for
  future non-Auth0/Keycloak deployments, but it is no longer the test
  shape — so its risk profile is "unused in CI, documented" rather than
  "unused in CI, silently relied on."
- Future migration path is clean: production switches from Keycloak to
  Auth0 (or Clerk, or Cognito) by changing `AUTH0_DOMAIN`. The middleware
  code does not care.

**Against:**

- Adds a ~600 MB image and a ~15 second first-run startup to the dev
  docker stack. Subsequent runs are fast.
- Realm import JSON is a checked-in artifact teams must keep in sync
  with the conftest fixture contract (test users, client IDs, scopes).
  This is a real maintenance surface — a Keycloak version bump can
  invalidate realm exports.
- The test suite now requires the `keycloak` service to be healthy
  before any auth test runs. `docker_test.sh` must wait on Keycloak's
  health endpoint the same way it waits on `db-test`.
- The `tests/fixtures/jwt_keys.py` module is removed. Any other test
  that consumed `make_token` (currently the auth fixtures only) is
  updated to use the Keycloak token factory.
- Token-fetch from Keycloak is HTTP-over-localhost; ~10-30 ms per
  cached fetch, ~100 ms on cache miss. Aggregate test-suite slowdown is
  acceptable (Keycloak token issuance is much faster than Auth0 cloud)
  but not free.
- SPEC-007 §13.4 amendment required (recorded below).

## Alternatives considered

- **Pattern 1 (Local keypair).** The shipped spec. Rejected for the
  "no mock-adjacent test scaffolding" reason above. The original design
  is technically valid and is what most FastAPI codebases use, but it
  conflicts with the project owner's stated requirements.

- **Pattern 2 (Hybrid — keypair + Auth0 smoke).** Adds one or two
  `@pytest.mark.live_auth0` tests against a real Auth0 dev tenant; rest
  of the suite uses the local keypair. Rejected for the same reason as
  Pattern 1: the bulk of tests still depend on the static-PEM mode.

- **Pattern 3 (Full Auth0 dev tenant).** Every test fetches from a real
  Auth0 sandbox. Rejected for: (a) rate limits on Auth0 free tier hit
  fast on a 100+ test suite, (b) negative-path tests require a second
  tenant for cross-audience and real expiry, (c) requires Auth0 client
  secret in CI env, (d) Auth0 outage = CI down, (e) ties test
  infrastructure to a specific commercial vendor.

- **Other self-hosted IdPs.** Considered Ory Hydra/Kratos
  (more complex, two services to operate), Authelia (lighter but less
  full-featured OIDC), Dex (good but lower adoption). Keycloak wins on
  community size, documentation, and realm-export-as-config maturity.
  The Keycloak realm-import format is the most stable
  configuration-as-code path of the self-hosted options.

## Migration plan

1. **This ADR lands.** Reviewers confirm the direction. SPEC-007 §13.4
   amendment lands with it.

2. **TASK-014 ACs amended** to replace local-keypair language with
   Keycloak language. Specifically:
   - The AC about `TASK-008's key fixture (via env vars or a fixed
     tests/fixtures/jwt_keys/ path)` becomes "validates against the
     containerized Keycloak realm's JWKS endpoint."
   - The AC about `008A auth stubs flipped off` is unchanged.

3. **docker-compose.yml gains the `keycloak` service.** The realm
   import JSON is committed under `docker/keycloak/`.

4. **`docker_test.sh` waits on Keycloak's `/health/ready`** alongside
   the existing `db-test` wait.

5. **TASK-008's `tests/fixtures/jwt_keys.py` is removed.**
   `backend/tests/conftest.py` replaces `make_token` / `auth_header`
   with Keycloak-token fixtures. (TASK-008 itself is already complete;
   this is a follow-up under TASK-014.)

6. **TASK-014 test files (`test_jwt_validation.py`,
   `test_org_context.py`)** are rewritten against the new fixtures.
   The test names and assertions stay; only the token source changes.

7. **`settings.auth_jwt_static_public_key_pem`** remains in
   `app/core/config.py` as production-only config for hypothetical
   future deployments that need a static-PEM fallback. It is no longer
   used by tests. A startup assertion is added to `lifespan.py`:
   `AUTH_STUB_ENABLED=False AND AUTH_JWT_STATIC_PUBLIC_KEY_PEM=""` is
   the required production shape; any other combination logs a warning.

8. **`settings.auth0_*` fields** are reused as-is. The IdP-vendor name
   is loose — these fields actually mean "OIDC issuer / audience" and
   work for Keycloak unchanged. A future cosmetic rename
   (`auth0_*` -> `oidc_*`) is **not** part of this ADR.

## SPEC amendments

This ADR amends **SPEC-007 §13.4** as follows:

**Before (current spec):**

> Tests do not call Auth0. A test fixture generates valid JWTs signed
> with a test-only RSA key. The auth middleware is configured to
> validate against the test key in the test environment. This provides
> real JWT validation without an external dependency.

**After (this ADR):**

> Tests use a containerized Keycloak instance (running as a
> `docker-compose` service alongside `db-test`) as the IdP. Token-
> issuance and JWKS endpoints are real. The auth middleware validates
> against Keycloak's `/.well-known/jwks.json` the same way it would
> validate against Auth0 in production. Negative-path tokens (expired,
> wrong-audience, wrong-issuer) are minted by dedicated Keycloak realms
> with the appropriate configuration. No test-only configuration
> overrides are required; tests exercise the production code path
> unchanged.
>
> The `JWKSResolver`'s static-PEM mode remains in production code as a
> fallback for deployments that prefer a different IdP, but it is no
> longer the test shape. See ADR-010.

## References

- ADR-008 (Proposed) — request-context and auth-provider-org boundary.
  Compatible with this ADR: ADR-008 says auth-provider org IDs are
  external identity IDs mapped via a nullable FK column. Keycloak as
  test IdP doesn't change that contract.
- ADR-009 — class-per-aggregate Service + Model-as-Entity. Compatible:
  the auth middleware lives in `app/middleware/` per the 2026-05-19
  ADR-009 amendment.
- SPEC-007 §13 — test infrastructure. Amended by this ADR.
- SPEC-002 §11 — test table. Test names unchanged; only the token
  source changes.
- TASK-014 — auth middleware. ACs to be amended in lockstep.
- Keycloak documentation:
  https://www.keycloak.org/docs/latest/server_admin/#realm-export-and-import
