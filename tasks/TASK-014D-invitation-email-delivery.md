# TASK-014D: Invitation Email Delivery

**Status:** Not started
**Spec sections:** SPEC-007 §8 (endpoint inventory — no new endpoints; service-layer only), SPEC-006 (PHI handling — email content constraints)
**ADRs:** ADR-009 (layering), ADR-011 (invitation lifecycle), ADR-013 §Invitation lifecycle (application owns the email)
**Depends on:** TASK-014B

## Objective

Backend-owned delivery of invitation emails. Under ADR-013 the provider no longer sends anything — the invitation email contains our accept URL (carrying the ADR-011 nonce) and the provider's credential-setup URL (`SignupTicket.url`). This task ships the small email-sending service and templates that TASK-014F calls on send and resend. Transport-agnostic: one `EmailSender` interface with an SMTP implementation for MVP (works with SES/Postmark/Mailgun SMTP endpoints), so the vendor choice is config, consistent with the provider-ports philosophy.

## Acceptance Criteria

- [ ] `backend/app/services/email_service.py` — `EmailSender` ABC with `send(to, subject, html_body, text_body)`; `SmtpEmailSender` implementation; class-per-aggregate per ADR-009
- [ ] Settings in `backend/app/core/config.py`: `smtp_host`, `smtp_port`, `smtp_username`, `smtp_password`, `email_from_address`; `.env.backend.example` updated (no real secrets)
- [ ] Invitation email template (HTML + plaintext): practice/org display name, inviter-free wording (no inviter PII), the accept URL with nonce, the credential-setup URL, expiry date
- [ ] **No PHI in email bodies or subjects** beyond the invitee's own name; no role details that imply clinical relationships (SPEC-006/BR-08 discipline applies to email as an egress channel — and `spec-006-phi-not-in-logs`: email addresses and send failures are logged without message content)
- [ ] Transient SMTP failures retry with exponential backoff; permanent failure raises a `GroundworkError` subclass (`EmailDeliveryError`) so the invitation send transaction rolls back rather than leaving a pending Invitation the invitee never received
- [ ] Dev/test transport: a `CapturingEmailSender` (in-memory outbox) selected via settings, used by application tests to assert send/resend behavior without a network
- [ ] Tests: `test_invitation_email_contains_accept_and_ticket_urls`, `test_send_failure_raises_email_delivery_error`, `test_resend_uses_rotated_nonce_url`, `test_no_phi_in_subject_or_body`

## Files

- `backend/app/services/email_service.py` (new)
- `backend/app/templates/emails/invitation.html` / `.txt` (new)
- `backend/app/core/config.py` (SMTP settings)
- `backend/app/core/exceptions.py` (`EmailDeliveryError`)
- `.env.backend.example`
- `backend/tests/test_services/test_email_service.py`

## Non-goals

- Any email beyond invitations (password-reset, notifications — provider- or future-task-owned)
- Vendor-specific API integrations (SMTP covers MVP; a SES/Postmark API sender is a drop-in later)
- Email content for the bootstrap flow (TASK-014E delivers its credential URL out-of-band to the operator)
