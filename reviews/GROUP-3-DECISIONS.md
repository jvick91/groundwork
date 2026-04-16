# Group 3 — Product Decision Chart

**Date:** 2026-03-26
**Status:** Awaiting decisions
**Remaining blockers:** 10 items (9 independent decisions, 1 dependency pair)
**How to use:** Pick one option per row. Once all 10 are decided, every spec is code-ready.

---

## Decision 1 of 10 — 000-03: DEA Number Placement

**Issue:** SPEC-000 lists `dea_number` for the Prescriber persona, but SPEC-001 provider seed attributes don't include it. An agent can't create the field.

| | Option A: Provider-Level Attribute | Option B: Prescriber-Specific Attribute | Option C: Drop from MVP |
|---|---|---|---|
| **What** | Add `dea_number` to the Provider EntityType seed attributes in SPEC-001 §3. All providers get the field; non-prescribers leave it blank. | Create a separate Prescriber EntityType (child of Provider) with its own seed attribute for `dea_number`. Only prescribers carry the field. | Remove `dea_number` from SPEC-000's Prescriber row. Defer to a future "Prescriber Licensing" spec. |
| **Pros** | Simple — one attribute, no new types. Agents already know how to seed provider attributes. Prescribers are just providers with extra fields filled in. | Cleaner data model — only prescribers carry prescriber fields. Aligns with how NPI and DEA are real-world regulatory distinctions. | Eliminates the inconsistency immediately. No implementation work. Keeps MVP scope smaller. |
| **Cons** | Every provider sees a `dea_number` field even if they'll never have one. Slightly noisy for therapists/supervisors. | Adds a new EntityType to the EAV system, a new bridge rule, and complicates role assignments. Significant spec and code surface increase for one field. | SPEC-000 still describes Prescriber as a persona — removing `dea_number` weakens that concept without replacing it. Prescribers lose their distinguishing attribute. |
| **Effort** | S — one row in SPEC-001 seed table | L — new EntityType, new seed attributes, updated SPEC-000 persona table, new bridge rules | S — one deletion in SPEC-000 |
| **Recommendation** | **Recommended** | | |

---

## Decision 2 of 10 — 000-04: HIPAA-Ready Acceptance Checklist

**Issue:** "HIPAA-ready" is stated as a goal in SPEC-000 §6 but has no pass/fail criteria. An agent can't verify compliance.

| | Option A: Concrete MVP Checklist | Option B: Reference External Standard | Option C: Defer to ADR |
|---|---|---|---|
| **What** | Add a 6-item acceptance checklist to SPEC-000 §6 covering MFA, soft deletes, audit logging, PHI log exclusion, S3 encryption, and seed consent types. | Add a reference to HHS Security Rule categories (Administrative, Physical, Technical safeguards) with a note that full mapping is out of MVP scope. | Create ADR-015 "HIPAA Compliance Mapping" and reference it from SPEC-000. Leave SPEC-000 unchanged until the ADR is finalized. |
| **Pros** | Gives agents 6 testable pass/fail gates. Clear MVP definition of "HIPAA-ready." All items are already implied by existing specs. | Acknowledges HIPAA complexity without oversimplifying. Doesn't create false confidence about actual compliance. | Keeps SPEC-000 clean. Allows a dedicated compliance review later. Doesn't risk promising what MVP can't deliver. |
| **Cons** | A 6-item checklist doesn't constitute HIPAA compliance. Could create false confidence if misread as "we're HIPAA compliant." | Not actionable — an agent can't test against a vague external reference. Adds no value for code generation. | Blocks nothing operationally, but leaves the term "HIPAA-ready" undefined indefinitely. Agents still can't verify. |
| **Effort** | S — one subsection in SPEC-000 | S — one paragraph in SPEC-000 | M — new ADR file + SPEC-000 cross-reference |
| **Recommendation** | **Recommended** | | |

---

## Decision 3 of 10 — 002-03: Missing `notes.delete` Permission

**Issue:** Every other domain uses a `.delete` permission for soft deletes. Notes use `notes.write` for draft deletion with no stated rationale. An agent may invent its own permission.

| | Option A: Add Design Note (Keep Bundled) | Option B: Add `notes.delete` Permission | Option C: Add `notes.delete` But Alias to `notes.write` |
|---|---|---|---|
| **What** | Add a design note to SPEC-002 §3 explaining that `notes.delete` is intentionally omitted because draft deletion is semantically "discarding an unfinished edit," not destroying a clinical record. | Add `notes.delete` as a new seed permission. Grant it to all roles that currently have `notes.write`. Update SPEC-004 to require `notes.delete` for `DELETE /sessions/{id}/note`. | Add `notes.delete` to the permission table for consistency, but define it as always co-granted with `notes.write` in the seed matrix. Future decoupling possible. |
| **Pros** | No schema change. No migration. Makes the intent explicit for agents. Matches the clinical reality that only drafts are deletable. | Fully consistent with other domains. Enables future fine-grained control where a user can write notes but not delete them. | Consistency now, flexibility later. No behavioral change from bundling, but the permission slug exists for future use. |
| **Cons** | Breaks the convention set by every other domain. An agent might flag this as an oversight even with the note. | Over-engineers MVP — the only delete path is author-deletes-own-draft. A separate permission adds no practical access control value today. | Adds a permission that does nothing independently. Increases the seed matrix without functional benefit. Muddies the permission model. |
| **Effort** | S — one design note in SPEC-002 | M — new permission row, seed matrix update, SPEC-004 endpoint update | M — new permission row, seed matrix update, co-grant rule |
| **Recommendation** | **Recommended** | | |

---

## Decision 4 of 10 — 002-04 + 007-04: CPT/ICD Code Management

**Issue:** CPT/ICD tables exist with `is_active` flags and org-scoping, but no write permissions, no write endpoints, and no way for an agent to populate them. 007-04 (missing endpoints in SPEC-007) is blocked by this decision.

| | Option A: Full API Management | Option B: Seed-Only (Read-Only API) | Option C: Admin-Only Endpoints |
|---|---|---|---|
| **What** | Add `codes.write` and `codes.delete` permissions to SPEC-002. Add POST/PATCH/DELETE endpoints for `/cpt-codes` and `/icd-codes` in SPEC-005 and SPEC-007. Grant to `admin` and `biller`. | CPT/ICD codes are seeded at org creation from a platform-maintained master list. No write endpoints. `is_active` is toggled via a platform admin tool (out of MVP scope). | Add write endpoints but restrict to `admin` role only. Billers get read-only. Reduces risk of billing staff corrupting code tables. |
| **Pros** | Practices can customize their code lists immediately. Billers can add new codes as insurance requirements change. Fully self-service. | Simpler MVP — fewer endpoints, fewer permissions, no risk of practices creating invalid CPT codes. Standard code sets don't change often. | Balances flexibility with safety. Admins are trusted organizational gatekeepers. Keeps biller role focused on billing operations. |
| **Cons** | Practices could create invalid or duplicate CPT codes. No validation against official code registries in MVP. More endpoints to build and test. | Practices can't add specialty codes or disable irrelevant ones. The "platform admin tool" is undefined and punts work to post-MVP. | Adds operational friction — billers need to ask admins for code changes. More complex permission model for marginal safety gain. |
| **Effort** | L — 2 new permissions, 6 new endpoints across SPEC-002/005/007 | S — one design note in SPEC-005 explaining seed-only strategy | M — 2 new permissions, 6 new endpoints, more restrictive grants |
| **Recommendation** | **Recommended** | | |

---

## Decision 5 of 10 — 002-05: `entity_types.read` for Providers

**Issue:** `entity_types.read` is only granted to `admin`. Providers can't discover available EntityType slugs, which they need for EAV routing and UI dropdowns.

| | Option A: Grant Broadly | Option B: Implicit Access Only | Option C: New `entity_types.list` Permission |
|---|---|---|---|
| **What** | Add `entity_types.read` as a direct grant to `provider` (inherited by therapist, supervisor, prescriber) and `receptionist` in the SPEC-002 seed matrix. | Don't grant the permission. Instead, add a design note that EAV endpoints implicitly resolve type slugs from the URL path — providers don't need to list all types, they just use `/entities/client/{id}`. | Create a lighter `entity_types.list` permission (list only, no detail) and grant it broadly. Keep `entity_types.read` (includes attribute definitions) admin-only. |
| **Pros** | Simple. One seed matrix change. Providers and receptionists can see the full type catalog. Enables dropdown UIs. | No permission change. Minimizes exposure. Providers already know they work with "client" and "provider" types through their daily workflows. | Least-privilege approach. Providers see slugs and labels but not attribute schemas. Admins retain control over structural metadata. |
| **Cons** | Providers can see all EntityType definitions including attribute schemas. May expose internal data model details beyond what's needed. | Breaks if the UI ever needs a type picker. Doesn't work for custom types that practices create — providers would have no way to discover new type slugs. | Adds a new permission that splits a simple resource into two access levels. More complexity for minimal security gain on non-sensitive data. |
| **Effort** | S — seed matrix row additions in SPEC-002 | S — one design note in SPEC-002 | M — new permission, seed matrix update, SPEC-001 endpoint split |
| **Recommendation** | **Recommended** | | |

---

## Decision 6 of 10 — 004-05: Practice Admin Notes Access

**Issue:** `practice_admin` has no `notes.write` or `notes.sign`. Whether they can participate in amendment workflows (e.g., requesting corrections) is unstated.

| | Option A: Design Note (Exclude from Clinical) | Option B: Grant `notes.write` (Limited) | Option C: New `notes.request_amendment` Permission |
|---|---|---|---|
| **What** | Add a design note to SPEC-002 §3 stating that practice admins intentionally cannot create, sign, or amend notes. They have `notes.read` via admin inheritance. Amendment requests happen out-of-band. | Grant `notes.write` to `practice_admin` but not `notes.sign`. They can create and amend draft notes but cannot sign or co-sign. | Create a `notes.request_amendment` permission for practice admins. This triggers a notification to the provider but doesn't modify the note. |
| **Pros** | Clean separation — clinical documentation stays with clinicians. No ambiguity. Matches industry norms where admin staff don't author clinical records. | Practice admins can draft notes on behalf of busy providers. Useful in high-volume practices where admin staff handle documentation prep. | Formally models the "request amendment" workflow. Creates an audit trail for compliance. No clinical content created by non-clinicians. |
| **Cons** | If a practice admin spots an error in a note, the only recourse is a phone call or email — no in-platform mechanism. | Regulatory risk — non-clinicians authoring clinical notes is a compliance concern in many jurisdictions. Blurs accountability. | Adds a permission and a notification system for a workflow that MVP may not need. Over-engineers the problem. |
| **Effort** | S — one design note in SPEC-002 | S — seed matrix change in SPEC-002 | L — new permission, notification mechanism, SPEC-004 endpoint |
| **Recommendation** | **Recommended** | | |

---

## Decision 7 of 10 — 005-05: Missing `payments.void` Permission

**Issue:** Voiding a payment uses `payments.record` with no separate permission. An agent can't distinguish "can record payments" from "can void payments."

| | Option A: Design Note (Keep Bundled) | Option B: Add `payments.void` Permission | Option C: Add `payments.void` but Co-Grant |
|---|---|---|---|
| **What** | Add a design note to SPEC-002 §3 explaining that voiding is bundled with recording because void-and-rerecord is one logical operation. Audit trail captures all voids regardless. | Add `payments.void` as a new seed permission. Grant to `admin` and `biller`. Update SPEC-005 void endpoint to require this permission. | Add `payments.void` to the permission table, always co-granted with `payments.record` in MVP. Can be decoupled later. |
| **Pros** | No schema change. Matches the clinical billing reality — the person recording payments is the same person who voids mistakes. Simpler permission model. | Fine-grained access control. A practice could allow billing staff to record but not void (requiring supervisor approval for voids). | Future flexibility with zero behavioral change now. Permission slug exists for audit tooling to filter on. |
| **Cons** | Can't restrict void access independently. In practices with junior billing staff, you might want void approval from a senior biller. | Over-engineers MVP. Adds a permission for an edge case. Most small/mid practices have 1–2 billers who handle everything. | Adds complexity without immediate value. Co-granted permissions are confusing — "why does this permission exist if it's always identical to another?" |
| **Effort** | S — one design note in SPEC-002 | M — new permission, seed matrix, SPEC-005 endpoint update | M — new permission, seed matrix, co-grant rule |
| **Recommendation** | **Recommended** | | |

---

## Decision 8 of 10 — 006-01: Consent `pending → revoked` Semantics

**Issue:** "Revoked" covers both declined-before-signing and withdrawn-after-signing. Audit reports can't distinguish the two without guidance.

| | Option A: Design Note (Keep `revoked`, Disambiguate by Data) | Option B: Add `declined` Status | Option C: Add `revocation_type` Field |
|---|---|---|---|
| **What** | Add a design note after the lifecycle table: if `signed_at IS NULL` and `status = revoked`, it was declined. If `signed_at IS NOT NULL`, it was withdrawn. Reports use this field-level distinction. | Add `declined` as a fifth consent status. Transition: `pending → declined` (terminal). `revoked` only applies to `signed → revoked`. | Keep `revoked` as the only terminal status but add a `revocation_type` enum field (`declined`, `withdrawn`) to `ClientConsent`. |
| **Pros** | Zero schema change. The data already encodes the distinction — just needs documentation. No migration. Agents can implement immediately. | Semantically precise. Reports and UI can show "Declined" vs "Revoked" without checking `signed_at`. Cleaner domain language. | Keeps lifecycle simple (4 states) while adding explicit categorization. More flexible than a binary status split. |
| **Cons** | Requires report builders to know the `signed_at` trick. Not self-documenting in the status field itself. | Adds a fifth status to the lifecycle. Every consent query that checks for "not active" must now include both `declined` and `revoked`. More test cases. Migration needed if data already exists. | Adds a column for a distinction that's already inferrable. Over-models the problem. The field is only meaningful when `status = revoked`. |
| **Effort** | S — one design note in SPEC-006 | M — new status, lifecycle table update, test cases, SPEC-006 + SPEC-007 updates | M — new column on ClientConsent, validation rule, SPEC-006 update |
| **Recommendation** | **Recommended** | | |

---

## Decision 9 of 10 — 007-02: Implementation Details in Spec

**Issue:** SPEC-007 prescribes `cachetools.TTLCache`, a directory layout, and test factory patterns. These are implementation-level, which violates the "no code in specs" convention.

| | Option A: Mark as Non-Normative | Option B: Remove Entirely | Option C: Move to a Separate Implementation Guide |
|---|---|---|---|
| **What** | Add a note to SPEC-007 §12 and §13.5–13.6: "These sections are reference implementations, not normative requirements. Agents may deviate provided they satisfy the behavioral contracts in all other sections." Replace `cachetools.TTLCache` in §3.3 with behavioral requirements. | Delete the directory layout, factory patterns, and library references from SPEC-007. Leave only behavioral requirements. | Create a new `IMPL-001-reference-architecture.md` file. Move all implementation guidance there. SPEC-007 links to it as optional reference material. |
| **Pros** | Preserves useful guidance for agents while clarifying it's optional. Low risk — agents get a starting point but aren't locked in. Minimal spec disruption. | Purest adherence to the "no code in specs" convention. Specs describe *what*, never *how*. Eliminates any ambiguity about whether library choices are required. | Best of both worlds — guidance exists but lives in the right place. Specs stay clean. Agents can choose to follow the guide or not. |
| **Cons** | "Non-normative" sections in a spec create ambiguity — is this section normative or not? Agents may still treat it as a requirement. | Loses genuinely helpful guidance. An agent starting fresh has no reference architecture. Could lead to inconsistent implementations across agents. | Adds another file to maintain. The implementation guide will drift from specs unless actively synced. More work for marginal organizational benefit. |
| **Effort** | S — two notes + one sentence rewrite in SPEC-007 | M — multiple section deletions and rewrites in SPEC-007 | L — new file, content migration, cross-references |
| **Recommendation** | **Recommended** | | |

---

## Decision 10 of 10 — 007-06: `settings.write` Overloaded for AppointmentType

**Issue:** `settings.write` covers both general org settings and AppointmentType CRUD. No rationale for bundling is stated. An agent can't determine if this is intentional.

| | Option A: Design Note (Keep Bundled) | Option B: Add `appointment_types.write` Permission | Option C: Add `scheduling.admin` Permission |
|---|---|---|---|
| **What** | Add a design note to SPEC-003 §6 explaining that AppointmentType management uses `settings.write` because appointment types are organizational configuration, not clinical data. | Add `appointment_types.write` (and optionally `.read`) as new seed permissions. Update SPEC-003 and SPEC-007 endpoints. Grant to `admin` only. | Create a broader `scheduling.admin` permission covering AppointmentType management, availability rules, and future scheduling configuration. |
| **Pros** | No schema change. Makes the rationale explicit. Matches the mental model that appointment types are "practice settings." | Clean permission model — each resource has its own permission. Future-proof if different roles need different access to appointment types vs other settings. | Groups related scheduling admin functions under one permission. Cleaner than one-off `appointment_types.write` but more flexible than `settings.write`. |
| **Cons** | If a practice wants to let a receptionist manage appointment types without full org settings access, they can't. Bundling limits future flexibility. | Adds a permission for a resource that only admins manage. Increases seed matrix size for minimal access control benefit. | Speculative — no other "scheduling admin" functions exist yet. Designing a permission around future features is premature. |
| **Effort** | S — one design note in SPEC-003 | M — new permissions, seed matrix, SPEC-003 + SPEC-007 endpoint updates | M — new permission, seed matrix, endpoint updates |
| **Recommendation** | **Recommended** | | |

---

## Summary Matrix

| # | Issue ID | Spec(s) | Severity | Decision | Option A | Option B | Option C |
|---|---|---|---|---|---|---|---|
| 1 | 000-03 | 000/001 | Major | DEA number placement | Provider-level attribute | Prescriber-specific EntityType | Drop from MVP |
| 2 | 000-04 | 000 | Minor | HIPAA-ready criteria | Concrete MVP checklist | Reference external standard | Defer to ADR |
| 3 | 002-03 | 002/004 | Minor | `notes.delete` permission | Design note (keep bundled) | Add `notes.delete` | Add but alias |
| 4 | 002-04 + 007-04 | 002/005/007 | Major | CPT/ICD code management | Full API management | Seed-only (read-only) | Admin-only endpoints |
| 5 | 002-05 | 002 | Major | `entity_types.read` grants | Grant broadly | Implicit access only | Split into `.list` / `.read` |
| 6 | 004-05 | 002/004 | Minor | Practice admin notes | Design note (exclude) | Grant `notes.write` | New `request_amendment` perm |
| 7 | 005-05 | 002/005 | Minor | `payments.void` permission | Design note (keep bundled) | Add `payments.void` | Add but co-grant |
| 8 | 006-01 | 006 | Minor | Consent decline semantics | Design note (disambiguate by data) | Add `declined` status | Add `revocation_type` field |
| 9 | 007-02 | 007 | Minor | Impl details in spec | Mark as non-normative | Remove entirely | Move to IMPL-001 |
| 10 | 007-06 | 003/007 | Minor | `settings.write` overload | Design note (keep bundled) | Add `appointment_types.write` | Add `scheduling.admin` |
