# SPEC-004 Review: Issues vs SPEC-000

## TLDR Issue List

1. **BR-04 contradiction** — SPEC-000 says "signed notes cannot be edited." SPEC-004 allows amendments via an addendum model. These directly conflict. Fix SPEC-000 BR-04 wording.

2. **`cosigned` status missing from SPEC-000** — SPEC-000 only mentions `signed` as a terminal state. The `cosigned` status and `cosign_required` flag are absent from the platform overview.

3. **`amendment_pending` status missing from SPEC-000** — SPEC-004 introduces a fourth status with a full re-signing lifecycle. Not reflected in SPEC-000 at all.

4. **Session status values undeclared** — SPEC-004 depends on six session statuses (`in_progress`, `completed`, `scheduled`, `confirmed`, `cancelled`, `no_show`) but doesn't cite SPEC-003 as the source. Cross-spec dependency is implicit.

5. **Delete scope stricter than SPEC-000 implies** — SPEC-004 only allows soft-deleting draft notes. SPEC-000 BR-05 is generic ("soft-deleted records don't appear in lists") and doesn't address whether signed/cosigned notes can be deleted.

6. **Co-signer identity ambiguity** — SPEC-004 requires `notes.cosign` permission but doesn't specify whether the co-signer must be the author's assigned supervisor or any user with the permission.

7. **No test table** — SPEC-000 §5 requires every business rule to map to at least one test. SPEC-004 has no test table mapping rules to test cases.
