"""
Centralized PHI exclusion list (SPEC-006 §7).

A single platform-wide constant defines which field names are considered
PHI for the purposes of:

  * AuditLog ``previous_state`` / ``next_state`` snapshot filtering
    (SPEC-006 §4 BR-08, applied by ``app.services.audit_service``).
  * Structured log event filtering (applied by ``app.core.logger``).

Both consumers import this set; SPEC-006 §7 mandates one source of truth so
new PHI-bearing field names do not have to be added in two places.

The list is conservative by design: a field is excluded by *name* at any
nesting depth regardless of which resource it came from. Over-exclusion is
always safer than under-exclusion when the destination is an immutable
audit row that cannot be amended after the fact.
"""

from __future__ import annotations


PHI_EXCLUDED_FIELDS: frozenset[str] = frozenset({
    # Clinical-note format keys (SPEC-006 §4 BR-08)
    "subjective",
    "objective",
    "assessment",
    "plan",
    "data",
    "intervention",
    "response",
    "behavior",
    # ClinicalNote container — the entire content JSONB carries PHI
    "content",
    "note_content",
    # Person demographics
    "date_of_birth",
    "dob",
    "ssn",
    "social_security",
    "emergency_contact_name",
    "emergency_contact_phone",
    # EAV — SPEC-001 §7 explicitly requires AttributeValue value exclusion
    "value",
    # ClientConsent / Document free-text
    "notes",
    "description",
    # Billing — diagnosis codes correlated to a specific client
    "diagnosis_codes",
    "icd_codes",
})
