# TASK-023: ClinicalNote Model & CRUD API

**Status:** Not started
**Spec sections:** SPEC-004 §2 (ClinicalNote), §3 (format content schemas), §5 (one-note-per-session, session prerequisite, author bridge rule, draft editability, soft delete rule), §7 (ClinicalNote management, cross-entity listing)
**ADRs:** ADR-001, ADR-002
**Depends on:** TASK-021, TASK-015

## Objective

Implement the ClinicalNote model and CRUD endpoints. Notes are addressed through their parent session (`/sessions/{session_id}/note`). Enforce one-note-per-session, session status prerequisite (in_progress or completed), format immutability, author bridge rule, and content format validation for SOAP/DAP/BIRP schemas.

## Acceptance Criteria

- [ ] ClinicalNote model with all SPEC-004 §2 fields: id, organization_id, session_id (unique), author_instance_id, note_format (NoteFormat enum — immutable after creation), status (NoteStatus enum, default DRAFT), content (JSONB), signed_at, signed_by_person_id, cosigned_at, cosigned_by_person_id, cosign_required, amendment_note, created_at, updated_at, deleted_at
- [ ] UNIQUE(session_id) including soft-deleted records per SPEC-004 §2
- [ ] `GET /api/v1/sessions/{session_id}/note` retrieves note with `notes.read`
- [ ] `POST /api/v1/sessions/{session_id}/note` creates draft note with `notes.write`
- [ ] `PATCH /api/v1/sessions/{session_id}/note` updates draft content with `notes.write`
- [ ] `DELETE /api/v1/sessions/{session_id}/note` soft-deletes draft only with `notes.write`
- [ ] `GET /api/v1/notes` cross-entity listing with pagination, filterable by status, author, client, date range per SPEC-004 §7
- [ ] Session prerequisite: only in_progress or completed sessions allow note creation per SPEC-004 §5
- [ ] One-note-per-session: second note on same session returns 409 per SPEC-004 §5
- [ ] Soft-deleted note still blocks creation of a new note per SPEC-004 §5
- [ ] note_format immutable after creation — PATCH attempt returns 422 per SPEC-004 §5
- [ ] `cosign_required` defaults to false at creation, is settable by the author via POST and PATCH while status = draft, and becomes immutable once signed per SPEC-004 §5 (automatic derivation from author role is post-MVP)
- [ ] Author bridge rule: author_instance_id must be provider-type EntityInstance per SPEC-004 §5
- [ ] Author org rule: author's instance must belong to same org as note per SPEC-004 §5
- [ ] Content validation: SOAP requires subjective, objective, assessment, plan; DAP requires data, assessment, plan; BIRP requires behavior, intervention, response, plan per SPEC-004 §3
- [ ] Empty strings not accepted as substitutes for null on required fields per SPEC-004 §3
- [ ] Only draft notes can be soft-deleted; signed/cosigned/amendment_pending return 409 per BR-05, SPEC-004 §5
- [ ] Row-level filtering: `own_notes` condition from SPEC-002 §6 applied on list endpoints
- [ ] Content field excluded from application logs per BR-08
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-004 §10: `test_create_second_note_same_session_returns_409`, `test_create_note_after_soft_deleted_note_returns_409`, `test_create_note_on_scheduled_session_returns_422`, `test_create_note_on_cancelled_session_returns_422`, `test_create_note_on_no_show_session_returns_422`, `test_create_note_on_in_progress_session_succeeds`, `test_create_note_on_completed_session_succeeds`, `test_create_note_author_not_provider_type_returns_422`, `test_create_note_author_different_org_returns_422`, `test_patch_note_format_after_creation_returns_422`, `test_soft_delete_draft_note_succeeds`, `test_soft_delete_signed_note_returns_409`, `test_soft_delete_cosigned_note_returns_409`, `test_soft_delete_amendment_pending_note_returns_409`, `test_soft_deleted_note_excluded_from_list`, `test_create_soap_note_missing_subjective_returns_422`, `test_create_dap_note_missing_data_returns_422`, `test_create_birp_note_missing_behavior_returns_422`, `test_create_note_empty_string_field_returns_422`, `test_list_notes_filters_by_org`

## Files

- `backend/app/models/models.py` (ClinicalNote model)
- `backend/app/schemas/notes.py` (ClinicalNote schemas, format content schemas)
- `backend/app/services/note_service.py` (note service)
- `backend/app/routers/notes.py` (note endpoints)
- `backend/tests/factories/notes.py` (ClinicalNote factory)
- `backend/tests/test_notes/test_note_crud.py`
- `backend/tests/test_notes/test_note_formats.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Sign, cosign, amend transitions (TASK-024)
- Content lock enforcement for non-draft notes (TASK-024)
