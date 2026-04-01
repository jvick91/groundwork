# SPEC-004: Clinical Notes

**Status:** Draft
**Version:** 0.1.0
**Parent Spec:** [SPEC-000-platform-overview](./SPEC-000-platform-overview.md)
**Scope:** Clinical documentation authoring, note formats, signing, co-signing, and amendment lifecycle.

---

## 1. Domain Overview

This domain manages clinical documentation produced by providers after a session. A ClinicalNote is the formal record of what occurred during a session. It is PHI-bearing, audit-sensitive, and subject to strict write-once signing rules once finalized.

Notes are authored against a completed or in-progress session. They support three standard documentation formats used in mental health practice: SOAP, DAP, and BIRP. The format is determined at note creation time and cannot be changed afterward.

The signing lifecycle is the central constraint of this domain. A note transitions through draft, signed, and optionally co-signed states. Signing is irreversible. Co-signing is required for supervisees and optional for others based on practice configuration.

### Tables owned

- ClinicalNote: The documentation record for a session, including format, content, and signing state.

---

## 2. Data Model Detail

### ClinicalNote

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key. |
| organization_id | UUID | FK -> Organization, NOT NULL | Scopes note to a tenant. |
| session_id | UUID | FK -> Session, NOT NULL, UNIQUE | The session this note documents. One note per session. |
| author_instance_id | UUID | FK -> EntityInstance, NOT NULL | Provider profile instance who authored the note. Must reference an EntityInstance of type provider. |
| note_format | Enum | NOT NULL | One of: soap, dap, birp. Set at creation and immutable. |
| status | Enum | NOT NULL, default draft | One of: draft, signed, cosigned, amendment_pending. |
| content | JSONB | NOT NULL | Structured note body. Keys depend on note_format. See section 3. |
| signed_at | Timestamp | NULLABLE | When the note was signed by the author. Set once, immutable. |
| signed_by_person_id | UUID | FK -> Person, NULLABLE | Person who performed the sign action. |
| cosigned_at | Timestamp | NULLABLE | When the note was co-signed by a supervisor. |
| cosigned_by_person_id | UUID | FK -> Person, NULLABLE | Person who performed the co-sign action. Must hold notes.cosign permission. |
| cosign_required | Boolean | NOT NULL, default false | Whether co-signing is required before the note is considered finalized. |
| amendment_note | Text | NULLABLE | Explanation appended when an addendum is submitted post-signing. Not a replacement of signed content. |
| created_at | Timestamp | NOT NULL, default now | Record creation time in UTC. |
| updated_at | Timestamp | NOT NULL, default now | Last modification time in UTC. |
| deleted_at | Timestamp | NULLABLE | Soft delete marker. See BR-05 and ADR-006. |

**Unique constraint:** (session_id). Only one ClinicalNote may exist per session, including soft-deleted records. A session cannot have a second note created after its first is soft-deleted.

---

## 3. Note Format Content Schemas

The content field is a JSONB object. Its required keys depend on the note_format value. All fields are stored as text. Empty strings are not acceptable substitutes for null on required fields.

### SOAP format

| Key | Required | Description |
|---|---|---|
| subjective | true | Client's self-reported symptoms, complaints, and history in their own words. |
| objective | true | Clinician's observable, measurable findings. Behavioral observations, mental status. |
| assessment | true | Clinical interpretation and diagnostic impressions. |
| plan | true | Proposed treatment actions, goals, and follow-up. |

### DAP format

| Key | Required | Description |
|---|---|---|
| data | true | Combined subjective and objective observations from the session. |
| assessment | true | Clinical interpretation and diagnostic impressions. |
| plan | true | Proposed treatment actions, goals, and follow-up. |

### BIRP format

| Key | Required | Description |
|---|---|---|
| behavior | true | Client behavior and presentation during the session. |
| intervention | true | Clinician's therapeutic interventions applied during the session. |
| response | true | Client's response to interventions. |
| plan | true | Next steps and treatment plan updates. |

Content validation against the appropriate schema is performed at the application layer when a note is created or updated while in draft status.

---

## 4. Note Status Lifecycle

Notes move through statuses in one forward direction. The allowed transitions are:

| From | Allowed transitions | Who may act |
|---|---|---|
| draft | signed | Author (notes.sign permission) |
| signed | cosigned | Supervisor (notes.cosign permission), if cosign_required is true or voluntarily |
| signed | amendment_pending | Author or practice admin (notes.write permission) |
| cosigned | amendment_pending | Author or practice admin (notes.write permission) |
| amendment_pending | signed | Author (notes.sign permission) re-signs after amendment |
| amendment_pending | cosigned | Supervisor co-signs amended note |

Signing is always irreversible. The original signed content is never overwritten. When an amendment is submitted, the amendment_note field is appended and the note re-enters the signing cycle. The original content field is locked at first signing and must not change thereafter.

---

## 5. Business Rules

- BR-04 (Sign lock): A ClinicalNote in signed or cosigned status cannot have its content field modified. Any PATCH that attempts to change content on a non-draft note must be rejected with a domain error.
- One note per session: A session may have at most one ClinicalNote. Attempts to create a second note for the same session_id must be rejected.
- Session prerequisite: A ClinicalNote can only be created against a session with status in_progress or completed. Notes cannot be authored against scheduled, confirmed, cancelled, or no_show sessions.
- Author bridge rule: author_instance_id must reference an EntityInstance whose EntityType slug is provider. Validated at write time.
- Author org rule: The author's provider instance must belong to the same organization as the note.
- Co-sign permission gate: Only a person with the notes.cosign permission may set cosigned_at. Attempts by users without this permission must be rejected.
- Draft editability: A note in draft status may be freely edited by its author. No fields in the content object are locked until signing occurs.
- Soft delete rule: Soft-deleted notes must not appear in list endpoints. Because of the one-note-per-session constraint, a new note cannot replace a soft-deleted one.
- PHI content: The entire content field is PHI. It must never appear in application logs. See BR-08.

---

## 6. Amendment Model

Post-signing changes follow an addendum pattern, not an overwrite pattern. This preserves the legal integrity of the signed record.

When an author or practice admin initiates an amendment:

1. Status transitions to amendment_pending.
2. The locked content field remains unchanged.
3. The author submits the amendment_note text describing what is being corrected or added.
4. The author re-signs the note, setting a new signed_at timestamp.
5. If cosign_required is true, the supervisor must co-sign again before the note is finalized.

At no point is the original content replaced. The amendment_note is always additive. Multiple amendment cycles are permitted. Each cycle appends to amendment_note rather than replacing it. The backend must enforce append-only semantics on amendment_note.

---

## 7. API Surface

All endpoints require Auth0 JWT. All endpoints scope to the authenticated user's organization.

### ClinicalNote management

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /sessions/{session_id}/note | Retrieve the note for a session | notes.read |
| POST | /sessions/{session_id}/note | Create a draft note for a session | notes.write |
| PATCH | /sessions/{session_id}/note | Update note content (draft only) | notes.write |
| DELETE | /sessions/{session_id}/note | Soft delete a draft note | notes.write |

Notes are addressed through their parent session rather than by their own ID to reinforce the one-to-one session relationship and prevent orphaned note lookups.

### Note lifecycle transitions

| Method | Path | Description | Permission |
|---|---|---|---|
| POST | /sessions/{session_id}/note/sign | Sign the note as author | notes.sign |
| POST | /sessions/{session_id}/note/cosign | Co-sign the note as supervisor | notes.cosign |
| POST | /sessions/{session_id}/note/amend | Submit an amendment and re-enter signing cycle | notes.write |

### Cross-entity note listing

| Method | Path | Description | Permission |
|---|---|---|---|
| GET | /notes | List notes (paginated, filterable by status, author, client, date range) | notes.read |

The flat list endpoint exists to support dashboard views and billing workflows that need to query notes across sessions without iterating session-by-session.

---

## 8. Implementation Constraints

- Content lock enforcement: The backend must check note status before applying any PATCH to content. This check must happen inside the update transaction, not as a prior guard that could be bypassed by concurrent requests.
- Amendment append-only: The amendment_note field must only accept append operations. Any request that replaces or truncates existing amendment_note content must be rejected.
- PHI-safe logging: The content field, all note format keys, and amendment_note must be excluded from all application log output per BR-08.
- Audit requirements: All state-changing calls (POST, PATCH, DELETE, and all transition endpoints) must write an AuditLog entry per BR-07. Sign and co-sign events must log the signing person ID and timestamp.
- Session status dependency: The session status check (in_progress or completed) must be enforced at the service layer, not assumed from routing context.

---

## 9. Relevant ADRs

| ADR | Title | Impact on this spec |
|---|---|---|
| ADR-001 | Core MVP data model | Establishes ClinicalNote as a concrete table scoped to a session. |
| ADR-006 | Soft delete strategy | Defines delete semantics for notes and interaction with the one-note-per-session constraint. |
| ADR-011 | Multi-tenancy isolation | Requires all note queries to filter by organization_id. |
| ADR-003 | Session FK semantics | Defines how the session-to-provider and session-to-client linkage is validated, which this domain depends on for author and session prerequisite checks. |
| ADR-009 | File storage and encryption | Relevant if note attachments or document exports are added in a future phase. Not blocking MVP. |

---

## 10. Spec Versioning

| Version | Changes |
|---|---|
| 0.1.0 | Initial draft. Full ClinicalNote model, three note format schemas, status lifecycle, BR-04 and supporting rules, amendment model, API surface, and ADR mapping. |
