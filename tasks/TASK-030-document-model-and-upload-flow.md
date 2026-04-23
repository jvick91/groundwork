# TASK-030: Document Model & S3 Upload Flow API

**Status:** Not started
**Spec sections:** SPEC-006 §2 (Document, file upload constraints), §4 (document rules), §6 (Document management), §7; SPEC-000 §6
**ADRs:** ADR-002 (FK-only), ADR-005 (file storage and encryption)
**Depends on:** TASK-004, TASK-012, TASK-021, TASK-023, TASK-027, TASK-029

## Objective

Implement the Document model and the two-step upload flow: metadata submission returns a presigned S3 upload URL, then the caller confirms upload completion. File access is mediated exclusively by presigned download URLs — the s3_key is never exposed in API responses.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `Document` ORM model at `backend/app/models/models.py:737` (with `SoftDeleteMixin`).
- Table `documents` created by initial migration `a68701f39fed_initial_schema.py`.
- Remaining work: two-step upload API, S3 integration (presigned URLs), Pydantic schemas (never expose `s3_key`), service, router, file-constraint validation, linked-resource validation, audit calls, tests.

## Acceptance Criteria

- [x] Document model with all SPEC-006 §2 fields: id, organization_id, document_type_id, uploaded_by_person_id, linked_resource_id (nullable), file_name, mime_type, size_bytes, s3_key, s3_bucket, is_encrypted (default true), created_at, deleted_at
- [ ] Two-step upload: `POST /api/v1/documents` validates metadata and returns presigned upload URL; `POST /api/v1/documents/{id}/confirm` activates the record per SPEC-006 §6
- [ ] `GET /api/v1/documents` lists documents with `documents.read`, filterable by linked resource
- [ ] List endpoint (GET `/api/v1/documents`) uses cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] `GET /api/v1/documents/{id}` returns metadata and a fresh presigned download URL per SPEC-006 §6
- [ ] `DELETE /api/v1/documents/{id}` soft deletes (S3 object not removed) with `documents.delete` per ADR-005
- [ ] s3_key never appears in any API response per SPEC-006 §4
- [ ] File constraints enforced server-side per SPEC-006 §2: max 25MB, allowed MIME types (application/pdf, image/jpeg, image/png, image/tiff, application/msword, docx), filename max 255 chars, sanitized (no path components, null bytes, control chars)
- [ ] S3 key structure: `{org_id}/{doc_type_slug}/{doc_id}/{sanitized_filename}` per ADR-005
- [ ] Presigned download URL expires after 15 minutes; upload URL after 60 minutes per SPEC-006 §7
- [ ] Linked resource validation: when linked_resource_id is set, referenced record must exist in linked_resource_table and belong to same org per SPEC-006 §4
- [ ] Both-or-neither rule: linkable type requires resource_id; unlinkable type requires null resource_id per SPEC-006 §4
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-006 §9: `test_create_document_with_valid_type_succeeds`, `test_create_document_linked_resource_not_found_returns_422`, `test_create_document_linked_resource_wrong_org_returns_422`, `test_create_document_linkable_type_without_resource_id_returns_422`, `test_create_document_unlinkable_type_with_resource_id_returns_422`, `test_document_api_response_excludes_s3_key`, `test_document_download_returns_presigned_url`, `test_upload_disallowed_mime_type_returns_422`, `test_upload_exceeding_max_size_returns_422`, `test_upload_filename_sanitized`, `test_soft_deleted_document_excluded_from_list`, `test_list_documents_filters_by_org`

## Files

- `backend/app/models/models.py` (Document model)
- `backend/app/schemas/compliance.py` (document schemas)
- `backend/app/services/document_service.py` (upload flow, presigned URLs, S3 integration)
- `backend/app/routers/compliance.py` (document endpoints)
- `backend/tests/factories/compliance.py` (Document factory)
- `backend/tests/test_compliance/test_documents.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- S3 bucket provisioning (infrastructure concern)
- Document content indexing or full-text search
