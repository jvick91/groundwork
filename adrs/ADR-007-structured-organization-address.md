# ADR-007 — Structured address fields on Organization

**Date:** 2026-04-30
**Author:** claude-code
**Status:** Accepted (2026-05-01)

## Context

`Organization.address` is currently a single nullable `Text` column ([SPEC-001 §Organization](../specs/SPEC-001-eav-data-platform.md#L26-L39); [models.py:149](../backend/app/models/models.py#L149)). It was specified that way as the simplest representation of "where to mail things."

Several downstream domains in the existing roadmap need *components* of the address as discrete values, not the blob:

- **Billing (SPEC-005).** Claims submission via the X12 837P transaction requires `address_line1`, `city`, `state`, and `postal_code` as separate elements (loop 2010AA). A free-text blob cannot be reliably parsed into these fields under all the formatting variants the field accepts (suite numbers, multi-line entries, international formats, missing punctuation).
- **Tax jurisdiction.** Practice state determines licensing rules and sales-tax behavior. State must be queryable, not buried in prose.
- **Geocoding / location features.** Any future "find providers near me" or service-area logic needs structured input to a geocoder; sending a blob produces lower-quality matches and higher API cost.
- **Statements and document templates.** Address rendering on invoices and receipts benefits from per-line control rather than relying on the input formatting.

Addressing this once at the Organization layer is materially cheaper than parsing the blob in every downstream consumer.

## Decision

Replace the single `address: Text` column on `Organization` with structured fields:

| Field | Type | Constraints |
|---|---|---|
| `address_line1` | String(255) | NULLABLE |
| `address_line2` | String(255) | NULLABLE |
| `city` | String(100) | NULLABLE |
| `state` | String(2) | NULLABLE — US state code (ISO-3166-2:US subdivision code, 2 chars) |
| `postal_code` | String(20) | NULLABLE — accommodates US ZIP, ZIP+4, and international formats |
| `country` | String(2) | NOT NULL, default `"US"` — ISO-3166-1 alpha-2 |

All fields are nullable except `country`; the org may exist before its address is fully captured. The Pydantic schemas mirror this shape — no parsing, no derived `address` blob in responses.

The same shape is reused if/when other entities (Person, InsurancePayer) need addresses, so the convention is set once.

## Alternatives considered

**Keep `address` as a single `Text` column and parse on demand.**
Rejected. Parsing US addresses correctly is a known-hard problem (USPS publishes a 200+ page standard for it) and parsing fails silently — a bad parse produces a wrong claim, not an error. The cost is paid in every downstream domain instead of once here.

**Store both — keep `address` as `Text` and add structured fields alongside.**
Rejected. Two sources of truth for the same fact will diverge. Update one, forget the other, and downstream code does not know which to trust.

**Use a separate `addresses` table with a 1:N relationship (e.g., `mailing`, `billing`, `service_location`).**
Rejected for now (premature). The current spec scope has one address per organization. If later domains need multiple address kinds, that table can be introduced and `Organization.address_*` fields migrated into it without breaking the structured shape.

**Store the address as a JSONB document.**
Rejected. JSONB hides the schema from the database and from anyone reading the model. State lookups, indexing on postal_code, and constraint enforcement (e.g., 2-char state) all become application-layer code.

## Consequences

- (+) Downstream domains (billing, geocoding, tax) consume the address as discrete columns with no parsing layer.
- (+) State and country are indexable and queryable for jurisdiction-scoped reporting.
- (+) The shape is reusable for other addressed entities without rediscovering the design.
- (−) Migration is destructive: the existing `address` Text column is dropped. Any data already captured (none expected on this branch — TASK-009 just shipped) would need a one-shot migration. Downgrade path restores the Text column but cannot reconstruct the original formatting.
- (−) Six columns are wider than one. Index/storage cost is negligible at the cardinality of `organizations` (one row per tenant), so this is cosmetic.
- (−) International addresses are not perfectly modeled by this US-centric shape. `state` as 2-char and `postal_code` as String(20) cover most cases; truly multi-locale support (regions, prefectures, etc.) is a future concern and would re-open this ADR.

## References

- Code anchor: [backend/app/models/models.py:142-152](../backend/app/models/models.py#L142-L152) (current Organization model)
- Schema anchor: [backend/app/schemas/eav.py](../backend/app/schemas/eav.py) (current OrganizationCreate/Update/Response)
- Spec: [SPEC-001 §Organization](../specs/SPEC-001-eav-data-platform.md#L26-L39)
- Related: SPEC-005 (Billing — 837P consumer of structured address); ADR-002 (FK-only, applies if `addresses` table is introduced later)

## Amendment 2026-05-01 — API representation is nested

The original ADR specified the columns and noted "the same shape is reused if/when other entities need addresses, so the convention is set once" — but did not state how the address is exposed at the API. This amendment closes that gap.

**Decision.** The API representation of an address is a **nested object** under the parent schema (`address: { line1, line2, city, state, postal_code, country }`), not flat-at-root keys. The DB columns remain flat on the parent table; the service layer translates.

**Why.** Three reasons, in priority order:
1. **Reusability across entities.** Once Person and InsurancePayer need addresses (anticipated by the original ADR), a nested `Address` Pydantic model embeds in any parent schema with one line. Flat-at-root would require redefining six fields per parent and would not scale to multiple address kinds (mailing vs. billing vs. service location for 837P claims).
2. **Conceptual grouping matches reality.** Forms render addresses as a unit; the JSON shape should match.
3. **Snapshot/audit parity.** The audit log snapshot mirrors the API shape for free, making the audit trail and the response structurally identical.

**PATCH semantics — merge, not replace.** A `PATCH` body of `{"address": {"line2": "Apt 4B"}}` updates only `line2`; other address fields are preserved. This matches the parent-object `exclude_unset` behaviour and avoids the footgun of accidentally clearing the rest of the address by sending one field. Implemented via `model_dump(exclude_unset=True)` on the inner `AddressUpdate` schema.

**Scope of change.** Schema-only — no DB migration. The columns added in upgrade `485f37aa7554` are unchanged. `OrganizationCreate.address: Address`, `OrganizationUpdate.address: AddressUpdate | None`, `OrganizationResponse.address: Address` (built from flat ORM via a `mode='before'` model validator).

**Field name change inside the nested object.** API keys use `line1`/`line2` (the wrapper provides the `address` namespace, so the `address_` prefix would be redundant). DB columns keep `address_line1`/`address_line2` because they live flat on the parent table where the prefix disambiguates. The service-layer `_ADDRESS_FIELD_MAP` documents the translation.

**Consequence.** Future `Person`/`InsurancePayer` schemas embed the same `Address` model. If the eventual data model needs multiple address kinds per entity, the parent simply gets `mailing_address: Address | None`, `billing_address: Address | None`, etc. — no new field-name proliferation, no new translation logic.
