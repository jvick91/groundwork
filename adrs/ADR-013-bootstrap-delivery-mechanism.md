# ADR-013: Bootstrap Delivery Mechanism — Script vs HTTP Endpoint

## Status

Accepted

## Problem

The bootstrap operation provisions the very first Organization + Person(system_admin)
across both the application DB and Auth0. It is a one-shot, operator-only operation
that needs access to both systems atomically.

We need to decide how the operator triggers this operation:

1. A dedicated HTTP endpoint (`POST /api/v1/system/bootstrap`)
2. A CLI script (`backend/scripts/bootstrap.py`) run directly inside the container

The initial implementation (TASK-014E) used an HTTP endpoint. During review the
question was raised whether the added HTTP surface was justified.

## Options

### Option A: HTTP endpoint

The operator writes a token to a file on disk, then sends `POST /api/v1/system/bootstrap`
with the token in an `X-Bootstrap-Token` header. The endpoint validates the token,
runs the saga, and deletes the file on success.

**Pros:**
- No shell access to the container required; `curl` from the deploy pipeline is
  sufficient.
- The service's existing FastAPI dependency injection (DB session, management
  service, exception handlers) is available for free.
- Fits a "you can only access the app over HTTP" operational model (e.g., some
  Kubernetes setups where exec is locked down).

**Cons:**
- Adds a permanent unauthenticated HTTP surface, even when gated by a token file.
  The surface must be exempted from `AuthMiddleware` and requires its own
  token-validation logic (constant-time comparison, 404/410 semantics).
- `_AUTH_SKIP_PREFIXES` must be widened to include `/api/v1/system`, which is
  a blanket exemption that future system endpoints must be explicitly aware of.
- The token-file gate is more complex to reason about than "can you exec into the
  container?" — the file must be pre-placed, path must be configured, etc.
- Operationally, a script run via `docker exec` / `kubectl exec` is equally easy
  in all real deployment scenarios for this project.

### Option B: CLI script (chosen)

A `backend/scripts/bootstrap.py` script is run directly inside the container via
`docker exec` or `kubectl exec`. It instantiates `BootstrapService` directly and
calls `asyncio.run()`.

**Pros:**
- No HTTP surface at all — the attack surface is reduced to shell access to the
  container, which is already a high-trust operation.
- No `AuthMiddleware` exemption needed; the blanket `/api/v1/system` skip is
  removed, tightening the auth perimeter.
- Simpler operational model: if you can exec into the container you can bootstrap;
  if you cannot exec in, you cannot bootstrap (natural capability gate).
- Easy to run locally during development and in CI integration tests.
- The `BootstrapService` class is reused unchanged — only the delivery layer differs.

**Cons:**
- Requires shell access to the container. In a strictly HTTP-only access model
  this would be a blocker — but that is not this project's constraint.
- Script has its own credential-loading concern (reads env vars / `.env.backend`).
  Mitigated: the script runs inside the container where these are already present.

## Chosen Approach

**Option B: CLI script.**

For this project's deployment model (`docker compose` for dev, standard
Kubernetes for production), `docker exec` / `kubectl exec` is always available to
operators who need to bootstrap a fresh tenant. The reduction in HTTP attack surface
and the removal of the `AuthMiddleware` exemption outweigh the marginal convenience
of an HTTP endpoint.

The `BootstrapService` class (the saga logic) is unchanged. The HTTP router
(`routers/system.py`) and the `/api/v1/system` middleware exemption are removed.

## Phased Plan

- [x] Write `BootstrapService` with two-phase saga + compensating calls (TASK-014E)
- [x] Write `backend/scripts/bootstrap.py` CLI wrapper (TASK-014E)
- [x] Remove `routers/system.py` and `/api/v1/system` middleware exemption (TASK-014E)
- [x] Update `TASK-014E` acceptance criteria to reflect script delivery

## Deviation Notes

The original TASK-014E spec described an HTTP endpoint. This ADR documents the
decision to replace it with a script after initial implementation. The
`BootstrapService` saga logic, token-file gate, and all acceptance criteria are
otherwise unchanged.
