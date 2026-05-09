# TASK-024: Note Lifecycle — Sign, Cosign, Amend & Content Lock

**Status:** Not started
**Spec sections:** SPEC-004 §4 (status lifecycle), §5 (BR-04 sign lock, co-sign permission gate), §6 (amendment model), §7 (lifecycle transition endpoints, amend request body), §8
**ADRs:** ADR-009
**Depends on:** TASK-023

## Objective

Implement the clinical note lifecycle transitions: signing, co-signing, amendment submission, and re-signing. Enforce content immutability after signing (BR-04) and append-only semantics on the amendment_note field.

## Acceptance Criteria

- [ ] `POST /api/v1/sessions/{session_id}/note/sign` transitions draft→signed or amendment_pending→signed with `notes.sign` permission per SPEC-004 §7
- [ ] `POST /api/v1/sessions/{session_id}/note/cosign` transitions signed→cosigned with `notes.cosign` permission per SPEC-004 §7
- [ ] `POST /api/v1/sessions/{session_id}/note/amend` transitions signed→amendment_pending or cosigned→amendment_pending with `notes.write` permission per SPEC-004 §7
- [ ] Amend request body: `{amendment_text: str}` (min 1, max 10,000 chars) per SPEC-004 §7
- [ ] Backend appends amendment_text in format: `[AMENDMENT {ISO 8601 UTC} by {first_name last_name}]\n{amendment_text}\n` per SPEC-004 §7
- [ ] Direct amendment_note field in request body returns 422 per SPEC-004 §7
- [ ] BR-04: content field immutable after signing — PATCH on non-draft returns 409 `resource_locked` per SPEC-004 §5
- [ ] Content lock check inside update transaction to prevent concurrent bypass per SPEC-004 §8
- [ ] Amendment is append-only — any replace/truncation of existing amendment_note rejected per SPEC-004 §6
- [ ] Multiple amendment cycles permitted, each appends per SPEC-004 §6
- [ ] Amended note must be re-signed before co-sign: amendment_pending→signed→cosigned per SPEC-004 §4
- [ ] Co-sign permission gate: any person with notes.cosign can co-sign (not limited to assigned supervisor) per SPEC-004 §5
- [ ] signed_at set once on first signing, immutable per SPEC-004 §5
- [ ] Invalid transitions return 409 `state_transition_denied` (e.g., cosigned→signed, draft→cosigned)
- [ ] All transition operations write AuditLog entries with signer person ID per BR-07
- [ ] Tests from SPEC-004 §10: `test_patch_content_when_status_signed_returns_409`, `test_patch_content_when_status_cosigned_returns_409`, `test_patch_content_when_status_amendment_pending_returns_409`, `test_patch_content_when_status_draft_succeeds`, `test_cosign_without_cosign_permission_returns_403`, `test_cosign_by_non_supervisor_with_permission_succeeds`, `test_sign_without_sign_permission_returns_403`, `test_sign_sets_signed_at_immutable`, `test_sign_draft_transitions_to_signed`, `test_cosign_signed_transitions_to_cosigned`, `test_amend_signed_transitions_to_amendment_pending`, `test_amend_cosigned_transitions_to_amendment_pending`, `test_resign_amendment_pending_transitions_to_signed`, `test_sign_cosigned_note_returns_409`, `test_cosign_draft_returns_409`, `test_amend_appends_to_existing_amendment_note`, `test_amend_replace_existing_amendment_note_returns_422`, `test_sign_writes_audit_log_entry`, `test_cosign_writes_audit_log_entry`, `test_amend_writes_audit_log_entry`, `test_note_content_excluded_from_application_logs`

## Files

- `backend/app/services/note_service.py` (lifecycle transitions, content lock, amendment logic)
- `backend/app/routers/notes.py` (transition endpoints)
- `backend/tests/test_notes/test_note_lifecycle.py`
- `backend/tests/test_notes/test_amendments.py`

## Non-goals

- Draft CRUD (TASK-023)
- Format validation (TASK-023)
