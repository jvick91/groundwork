# TASK-022: Session Lifecycle Transitions & Overlap Detection

**Status:** Not started
**Spec sections:** SPEC-003 §3 (status lifecycle), §4 (BR-03 overlap, cancellation reason, consent gate), §6 (transition endpoints), §7 (overlap in transaction, consent gate)
**ADRs:** —
**Depends on:** TASK-006, TASK-021

## Objective

Implement session status transitions via explicit endpoints and the provider overlap detection from BR-03. The consent gate for session completion depends on TASK-033 (ClientConsent) — until that task is done, the gate should be stubbed to always pass and marked with a TODO.

## Acceptance Criteria

- [ ] Transition endpoints per SPEC-003 §6: `POST /sessions/{id}/confirm`, `/start`, `/complete`, `/cancel`, `/no-show`
- [ ] Lifecycle enforced per SPEC-003 §3: scheduled→confirmed, confirmed→in_progress, in_progress→completed, any-non-terminal→cancelled, scheduled/confirmed→no_show
- [ ] Terminal statuses (completed, cancelled, no_show) cannot be transitioned out of — returns 409 `state_transition_denied`
- [ ] Cancellation reason required for cancel and no_show — missing returns 422 per SPEC-003 §4
- [ ] `cancelled_at` and `cancelled_by_person_id` set on cancellation
- [ ] BR-03 overlap detection: provider cannot have two non-cancelled sessions with overlapping time ranges per SPEC-003 §4
- [ ] Overlap defined as: existing.start_time < new.end_time AND existing.end_time > new.start_time per SPEC-003 §4
- [ ] Only scheduled, confirmed, in_progress sessions count toward overlap; cancelled, no_show, soft-deleted excluded per SPEC-003 §4
- [ ] Overlap check runs inside a database transaction to prevent race conditions per SPEC-003 §7
- [ ] Consent gate stub: session completion checks for active signed treatment consent (full implementation in TASK-033)
- [ ] All transition operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-003 §9: `test_create_overlapping_session_returns_409`, `test_create_session_adjacent_no_overlap_succeeds`, `test_cancelled_session_not_counted_in_overlap`, `test_no_show_session_not_counted_in_overlap`, `test_overlap_check_concurrent_booking_uses_transaction`, `test_confirm_scheduled_succeeds`, `test_start_confirmed_succeeds`, `test_complete_in_progress_succeeds`, `test_cancel_with_reason_succeeds`, `test_cancel_without_reason_returns_422`, `test_no_show_with_reason_succeeds`, `test_no_show_without_reason_returns_422`, `test_transition_out_of_completed_returns_409`, `test_transition_out_of_cancelled_returns_409`, `test_transition_out_of_no_show_returns_409`, `test_soft_deleted_session_excluded_from_overlap`, `test_cancel_session_writes_audit_log`

## Files

- `backend/app/services/session_service.py` (transitions, overlap logic)
- `backend/app/routers/sessions.py` (transition endpoints)
- `backend/tests/test_sessions/test_session_lifecycle.py`
- `backend/tests/test_sessions/test_overlap_detection.py`

## Non-goals

- Automatic ClinicalNote creation on completion (explicitly NOT per SPEC-003 §7)
- Automatic Invoice creation on completion (explicitly NOT per SPEC-003 §7)
