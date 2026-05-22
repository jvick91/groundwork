# TASK-014A: Consolidated Auth0 Architecture ADR & Spec Edits

**Status:** Not started
**Spec sections:** SPEC-007 §3 (authentication and organization context)
**ADRs:** ADR-010 (the ADR this task ratifies), ADR-008 (superseded)
**Depends on:** (none — first link in the new auth chain)

## Objective

Ratify ADR-010 (consolidated Auth0 identity architecture) from Proposed to Accepted, mark ADR-008 as Superseded, and propagate the JWT-shape and binding-flow decisions into SPEC-007 §3 so every downstream task composes against a stable contract. This is a documentation-only task with no application code, but it is foundational — TASK-014 itself must not write any JWT-handling code until A is accepted, or the middleware will be built against an undecided contract.

## Acceptance Criteria

- [ ] ADR-010 status changes from `Proposed` to `Accepted`
- [ ] ADR-008 status changes to `Superseded by ADR-010`
- [ ] SPEC-007 §3.1 references Auth0 Organizations (`org_id` claim on every JWT) and the binding-by-nonce model
- [ ] SPEC-007 §3.2 reflects org-switch as a fresh login (not a mid-session `X-Organization-Id` header swap)
- [ ] SPEC-007 §3 cross-references ADR-010, ADR-011, and ADR-012 in the section header
- [ ] STATE.md updated to note ADR-010 ratification and the start of the TASK-014 chain decomposition
- [ ] No code changes — this task is doc-only

## Files

- `adrs/ADR-010-consolidated-auth-architecture.md` (status change)
- `adrs/ADR-008-request-context-and-auth-provider-org-boundary.md` (status change)
- `specs/SPEC-007-api-contract-and-testing.md` (§3 edits)
- `STATE.md` (bookkeeping)

## Non-goals

- Any Auth0 tenant configuration work (TASK-014B)
- Any middleware code (TASK-014)
- Any Auth0 Management API integration (TASK-014D)
