# TASK-014B: Auth0 Tenant Configuration & Environment Doc

**Status:** In progress
**Spec sections:** SPEC-007 §3.1 (JWT validation), §3.2 (org context)
**ADRs:** ADR-010 (decisions this task implements on the Auth0 side)
**Depends on:** TASK-014A

## Objective

Configure the Auth0 tenant per ADR-010: Organizations enabled, Universal Login with WebAuthn-first universal MFA, refresh token rotation with reuse/breach detection, single-connection-per-user (email/password + WebAuthn passkey), branded login pages, and per-environment callback/logout URLs. Produce an operational runbook plus a Terraform or CLI script that captures the configuration so dev/staging/prod tenants can be reproducibly provisioned. Routine login and logout become fully Auth0-handled by the end of this task — the backend has no role in routine logout flow.

## Acceptance Criteria

- [ ] Auth0 tenant has Organizations feature enabled
- [ ] Universal Login configured with WebAuthn-first MFA policy; TOTP and SMS available as fallback factors
- [ ] MFA enforcement is universal (no opt-out tier)
- [ ] Refresh token rotation enabled with reuse/breach detection per ADR-010
- [ ] Access token TTL set to 5–15 minutes per ADR-010
- [ ] Single email/password + WebAuthn passkey connection configured; no social/SAML connections enabled in MVP
- [ ] Per-environment callback URLs configured (dev, staging, prod)
- [ ] `backend/app/core/config.py` settings extended: `auth0_domain`, `auth0_audience`, `auth0_issuer` (existing); plus `auth0_management_client_id`, `auth0_management_client_secret`, `auth0_management_audience` for TASK-014D
- [ ] `.env.backend.example` updated with the new Auth0 env vars (no real secrets)
- [ ] Operational runbook in `docs/auth0-tenant-setup.md` documents the Auth0 dashboard steps and any Terraform/CLI invocations
- [ ] Test: `/health/ready` JWKS probe (already scaffolded in TASK-005) reports healthy against the configured tenant
- [ ] Doc clarifies that routine login and logout are entirely Auth0-handled; backend has no logout endpoint

## Files

- `docs/auth0-tenant-setup.md` (new — operational runbook)
- `backend/app/core/config.py` (extend settings)
- `.env.backend.example` (new env vars)
- (Optional) `infra/auth0/main.tf` if Terraform is chosen over manual dashboard config

## Non-goals

- Post-Login Action code (TASK-014C)
- Management API integration code (TASK-014D)
- Any JWT validation middleware (TASK-014 main)
