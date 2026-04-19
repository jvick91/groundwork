# ADR-005 — File storage: single S3 bucket with SSE-S3 encryption

**Date:** 2026-04-19
**Author:** claude-code
**Status:** Accepted

## Context

SPEC-006 defines a Document table with S3-backed file storage. The spec provides defaults for presigned URL lifetimes and file constraints but defers three decisions:

1. Bucket layout: one bucket per org, one per environment, or one global?
2. Encryption: SSE-S3 (Amazon-managed keys) or SSE-KMS (customer-managed keys)?
3. Object key structure: how are files organized in S3?

## Decision

### Bucket layout: single bucket per environment

One S3 bucket per deployment environment (dev, staging, production). Organization isolation is enforced by the object key prefix, not by bucket boundaries.

- `groundwork-documents-dev`
- `groundwork-documents-staging`
- `groundwork-documents-prod`

Why not per-org buckets: bucket creation requires IAM permissions and adds operational overhead for tenant onboarding. Key-prefix isolation is standard practice and sufficient when combined with application-layer access control.

### Encryption: SSE-S3

Server-side encryption with Amazon S3-managed keys (SSE-S3). Every object is encrypted at rest automatically via the bucket default encryption policy.

Why not SSE-KMS: KMS adds per-request costs ($0.03/10k requests), key rotation management, and IAM policy complexity. For MVP, SSE-S3 meets the HIPAA encryption-at-rest requirement. Migration to SSE-KMS is non-breaking — new objects use the new key, existing objects can be re-encrypted in place via S3 copy.

### Object key structure

```
{organization_id}/{document_type_slug}/{document_id}/{sanitized_filename}
```

Example: `a1b2c3d4-.../consent_form/e5f6g7h8-.../signed_treatment_consent.pdf`

- Organization prefix enables per-org lifecycle policies and access auditing.
- Document type slug groups related files for browsing (not used by the app, but useful for ops).
- Document ID ensures uniqueness even if two files share a name.
- Sanitized filename preserves the original name for human readability in S3 console.

### Presigned URL lifetimes

Per SPEC-006 §7 defaults:
- **Download:** 15 minutes
- **Upload:** 60 minutes

### Bucket policy

- Block all public access (S3 Block Public Access enabled on all four settings).
- Bucket policy denies any request without SSL (`aws:SecureTransport`).
- No CORS on the bucket — presigned URLs are direct S3 calls from the client browser, not cross-origin API requests. S3 presigned PUT/GET work without CORS when the client uses the presigned URL directly.

**Correction:** CORS _is_ required on the bucket for browser-based uploads via presigned URLs. The bucket CORS configuration must allow the frontend origin with PUT and GET methods.

## Consequences

- (+) Simple setup — one bucket, one encryption setting, no key management.
- (+) Org isolation via key prefix is operationally transparent and auditable.
- (+) SSE-S3 meets HIPAA encryption-at-rest with zero configuration beyond the bucket default.
- (+) Migration path to SSE-KMS is non-breaking if compliance requirements tighten.
- (-) Single bucket means a misconfigured IAM policy could expose cross-org data. Mitigated by application-layer access control (presigned URLs are generated per-request with org validation).
- (-) SSE-S3 keys are Amazon-managed — no customer control over key rotation schedule. Acceptable for MVP.
