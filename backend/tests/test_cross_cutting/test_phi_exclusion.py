"""
PHI exclusion tests for structured logging (SPEC-006 §4 BR-08).

The two named tests below are required by:
  - SPEC-004 §10: test_note_content_excluded_from_application_logs
  - SPEC-005 §8:  test_icd_codes_excluded_from_application_logs

The phi_filter processor is wired into the structlog chain by setup_logging()
(see app.core.logger). These tests call the filter directly so they cover
exactly what gets emitted to log output, without depending on logger setup
side effects from other tests.
"""

from app.core.logger import phi_filter
from app.core.phi import PHI_EXCLUDED_FIELDS


def test_note_content_excluded_from_application_logs() -> None:
    """SPEC-004 §10 — clinical-note content keys must never reach log output.

    Asserts every BR-08 clinical-note format key (subjective, objective,
    assessment, plan, data, intervention, response, behavior) plus the
    JSONB container fields (content, note_content) are stripped, while
    non-PHI metadata around them is preserved.
    """
    event = {
        "event": "note_saved",
        "note_id": "00000000-0000-0000-0000-000000000001",
        "actor_id": "00000000-0000-0000-0000-000000000002",
        # All eight BR-08 format keys
        "subjective": "Client reports increased anxiety this week.",
        "objective": "Affect constricted; speech pressured.",
        "assessment": "Generalized anxiety disorder, recurrent.",
        "plan": "Continue weekly CBT; review medication next session.",
        "data": "Reviewed thought log entries.",
        "intervention": "Practiced 4-7-8 breathing.",
        "response": "Reported reduced acute anxiety.",
        "behavior": "Maintained eye contact, appropriate engagement.",
        # JSONB container fields
        "content": {"subjective": "...", "objective": "..."},
        "note_content": "Free-text clinical narrative.",
    }

    filtered = phi_filter(None, "info", event)

    for phi_field in (
        "subjective",
        "objective",
        "assessment",
        "plan",
        "data",
        "intervention",
        "response",
        "behavior",
        "content",
        "note_content",
    ):
        assert phi_field not in filtered, f"{phi_field} leaked into log event"

    # Non-PHI metadata must survive — log records still need to be useful.
    assert filtered["event"] == "note_saved"
    assert filtered["note_id"] == "00000000-0000-0000-0000-000000000001"
    assert filtered["actor_id"] == "00000000-0000-0000-0000-000000000002"


def test_icd_codes_excluded_from_application_logs() -> None:
    """SPEC-005 §8 — diagnosis codes correlated to a person are PHI per BR-08.

    Both spellings used in InvoiceLineItem context (icd_codes, diagnosis_codes)
    are stripped, while the surrounding billing identifiers are preserved.
    """
    event = {
        "event": "invoice_line_item_created",
        "invoice_id": "00000000-0000-0000-0000-000000000010",
        "line_item_id": "00000000-0000-0000-0000-000000000011",
        "cpt_code": "90837",
        "amount_cents": 18000,
        # Both PHI spellings — one or the other tends to show up depending on caller
        "icd_codes": ["F33.1", "F41.1"],
        "diagnosis_codes": ["F33.1"],
    }

    filtered = phi_filter(None, "info", event)

    assert "icd_codes" not in filtered, "icd_codes leaked into log event"
    assert "diagnosis_codes" not in filtered, "diagnosis_codes leaked into log event"

    # Non-PHI billing identifiers must survive.
    assert filtered["event"] == "invoice_line_item_created"
    assert filtered["invoice_id"] == "00000000-0000-0000-0000-000000000010"
    assert filtered["cpt_code"] == "90837"
    assert filtered["amount_cents"] == 18000


def test_phi_filter_centralized_list_is_authoritative() -> None:
    """Belt-and-braces: every name in PHI_EXCLUDED_FIELDS is stripped.

    Guards against silent drift if a field is added to the centralized
    list but the filter implementation regresses.
    """
    event: dict[str, object] = {"event": "test"}
    event.update({field: "leak" for field in PHI_EXCLUDED_FIELDS})

    filtered = phi_filter(None, "info", event)

    for field in PHI_EXCLUDED_FIELDS:
        assert field not in filtered, f"{field} listed in PHI_EXCLUDED_FIELDS but not stripped"
    assert filtered["event"] == "test"
