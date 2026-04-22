# ADR-006 — Consent expiry runs as an admin endpoint, not an in-process scheduler

**Date:** 2026-04-21
**Author:** claude-code
**Status:** Accepted

## Context

SPEC-006 §3 specifies that expired `ClientConsent` rows are transitioned to `expired` status in two ways:

1. **Lazily at read time** — when a consent is queried and found to be past its `expiration_date`, the service layer transitions it and writes a system-attributed AuditLog entry.
2. **Authoritatively in batch** — a periodic job transitions all overdue records so the stored `status` field matches reality for reporting, metrics, and audit export.

The lazy path keeps correctness intact — no consent read returns `signed` when it should be `expired`. The batch path is a janitorial consistency pass; business logic does not depend on its cadence.

Celery and Redis were removed from the stack (see the `65c1933 remove Celery and Redis` commit and the ADR cleanup in PR #12). That removed both MVP options for an in-process scheduler without replacing them. Candidates considered:

- **APScheduler in-process.** Couples a scheduler to every backend worker. Requires leader election (otherwise every worker fires the sweep simultaneously) and complicates horizontal scaling for a single janitorial task.
- **Dedicated worker process.** Adds a second process type, deploy target, and log pipeline for one job.
- **External scheduler hitting an admin endpoint.** Platform-level cron (Render cron job, GitHub Actions scheduled workflow, Kubernetes CronJob, manual curl) calls an authenticated endpoint. The backend stays single-purpose.

## Decision

**Consent expiry batch transitions run via an admin HTTP endpoint, not an in-process scheduler.**

- The endpoint is `POST /api/v1/admin/consents/sweep-expired`.
- It requires the `system.configure` permission.
- Each overdue record is transitioned in its own database transaction; a failure on one record does not stop the sweep.
- Audit entries for sweep-originated transitions have `actor_person_id = NULL`.
- The invocation mechanism (Render cron job, GitHub Actions, operator `curl`, whatever the hosting platform provides) is an infrastructure/operator concern. The backend code owns no scheduler.

Because the lazy read-time path already guarantees correctness, the sweep can run on any cadence the operator chooses — daily, hourly, or even manually — without violating any business rule in SPEC-006.

## Consequences

- (+) No new process type, no new dependency, no leader election logic.
- (+) The sweep is trivially testable — it is a normal FastAPI route exercised with the usual test client.
- (+) Platform-portable: the endpoint runs the same in Render, Fly, Kubernetes, or a local dev machine. Scheduling is whichever platform primitive fits.
- (+) Manual invocation is always available during incident response without touching a scheduler config.
- (−) Requires configuring an external trigger per environment (dev, staging, prod). Documented in the deployment runbook, not in backend code.
- (−) If no external trigger is configured, expired consents accumulate in their pre-transition state — but the lazy path still prevents incorrect authorization decisions, so the impact is limited to reporting freshness.
- (−) The endpoint must be protected by permission + network scoping so it is not reachable as a denial-of-service lever. `system.configure` + standard auth middleware handles this at the application layer; network-level lockdown (bastion-only, VPC-internal) is an infrastructure concern.

## Follow-ups

- Deployment runbook must document the sweep cadence and the configured trigger per environment before production launch.
- If post-MVP workflows introduce additional recurring jobs (re-indexing, materialized view refresh, digest emails, etc.), revisit this ADR rather than bolting on a scheduler ad hoc.
