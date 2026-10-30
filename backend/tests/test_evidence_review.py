"""FIX 3 regression: evidence-versioned human review.

Every review decision is pinned to the exact evidence snapshot + hash the
reviewer saw. If a later recomputation changes the material evidence, the
preserved decision is flagged OUTDATED (requires_rereview) - never silently
erased, and never displayed as if it covered the new evidence. Complaint
records themselves are never mutated by the engine; only the automated
recommendation is refreshed.
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.models import (
    AssessmentStatus,
    AuditEvent,
    Bureau,
    CaseStatus,
    ComplaintCase,
    Institution,
    Priority,
    RelationshipAssessment,
    RelationshipType,
)
from app.services import matching_service
from app.services.matching_service import compute_evidence_hash


BASE_TEXT = (
    "Regarding incident INC-2099-0001 at the hostel block. Incident dated "
    "2026-01-10. The warden was informed and fee receipts were submitted for "
    "verification by the grievance cell."
)
# Points the second case at a DIFFERENT incident reference, which the engine
# parses reliably; this flips R1 (shared incident ref) off and fires R6
# (distinct refs), materially changing the evidence. The ref appears in both
# the subject and the description, so both must change.
CHANGED_TEXT = BASE_TEXT.replace("INC-2099-0001", "INC-2099-0002")
CHANGED_SUBJECT = "Fee verification for incident INC-2099-0002"


def _change_evidence(db, b):
    b.subject = CHANGED_SUBJECT
    b.description = CHANGED_TEXT
    db.commit()


@pytest.fixture()
def psi_pair(db):
    """A same-institution pair that the engine links as POTENTIAL_SAME_INCIDENT.
    Rows are cleaned up afterwards so the seeded dataset stays pristine."""
    inst = Institution(
        permanent_id="PERM-EV-PROBE", name="Evidence Probe Institution",
        address="Synthetic", region="TEST", state="TEST", district="TEST",
        institution_type="Synthetic", is_demo=True,
    )
    db.add(inst)
    db.flush()
    rb = db.scalar(select(Bureau).where(Bureau.code == "RB"))
    a = ComplaintCase(
        case_id="LIFE-EV-1", institution_id=inst.id, bureau_id=rb.id,
        receipt_date=date(2026, 1, 15), category="Fee Refund",
        subject="Hostel fee issue regarding incident INC-2099-0001",
        description=BASE_TEXT, status=CaseStatus.UNDER_PROCESS,
        priority=Priority.MEDIUM,
    )
    b = ComplaintCase(
        case_id="LIFE-EV-2", institution_id=inst.id, bureau_id=rb.id,
        receipt_date=date(2026, 1, 16), category="Fee Refund",
        subject="Fee verification for incident INC-2099-0001",
        description=BASE_TEXT, status=CaseStatus.UNDER_PROCESS,
        priority=Priority.MEDIUM,
    )
    db.add_all([a, b])
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    row = db.scalar(
        select(RelationshipAssessment).where(
            RelationshipAssessment.pair_key == "LIFE-EV-1|LIFE-EV-2"
        )
    )
    assert row is not None
    yield a, b, row
    for extra in db.scalars(
        select(RelationshipAssessment).where(
            RelationshipAssessment.institution_id == inst.id
        )
    ).all():
        db.delete(extra)
    for alert in db.scalars(
        select(matching_service.CoordinationAlert).where(
            matching_service.CoordinationAlert.institution_id == inst.id
        )
    ).all():
        db.delete(alert)
    db.delete(a)
    db.delete(b)
    db.flush()
    db.delete(inst)
    db.commit()


def test_review_pins_evidence_snapshot_and_hash(db, psi_pair):
    a, b, row = psi_pair
    assert row.relationship_type == RelationshipType.POTENTIAL_SAME_INCIDENT
    matching_service.review_assessment(
        db, row.id, decision=AssessmentStatus.CONFIRMED,
        rationale="verified with both bureaus", reviewer="reviewer",
    )
    db.refresh(row)
    assert row.evidence_snapshot is not None
    assert row.evidence_snapshot["relationship_type"] == "POTENTIAL_SAME_INCIDENT"
    assert row.reviewed_evidence_hash == row.evidence_hash
    assert row.reviewer_identity == "reviewer"
    assert row.reviewer_rationale == "verified with both bureaus"
    assert row.requires_rereview is False

    # recompute with unchanged evidence -> decision untouched, no flag
    matching_service.recompute_all(db, actor="pytest")
    db.refresh(row)
    assert row.requires_rereview is False
    assert row.status == AssessmentStatus.CONFIRMED


def test_evidence_change_after_confirm_flags_rereview(db, psi_pair):
    a, b, row = psi_pair
    matching_service.review_assessment(
        db, row.id, decision=AssessmentStatus.CONFIRMED,
        rationale="checked", reviewer="reviewer",
    )
    old_hash = row.reviewed_evidence_hash
    old_snapshot_type = row.evidence_snapshot["relationship_type"]

    # an officer updates the underlying complaint narrative (case records are
    # owned by officers; the engine itself never mutates them)
    _change_evidence(db, b)
    matching_service.recompute_all(db, actor="pytest")
    db.refresh(row)

    assert row.status == AssessmentStatus.CONFIRMED, "decision must survive"
    assert row.requires_rereview is True, "changed evidence must flag re-review"
    assert row.evidence_hash != old_hash
    assert row.reviewed_evidence_hash == old_hash
    # the snapshot still shows exactly what the reviewer confirmed
    assert row.evidence_snapshot["relationship_type"] == old_snapshot_type
    # the current automated recommendation now differs from the snapshot
    assert row.relationship_type.value != old_snapshot_type

    # audit trail both for the recompute and the evidence change
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.entity_id == str(row.id))
    ).all()
    types = {e.event_type for e in events}
    assert "ASSESSMENT_EVIDENCE_CHANGED" in types
    assert "ASSESSMENT_RECOMPUTED" in types

    # re-review clears the flag and re-pins to the current evidence
    matching_service.review_assessment(
        db, row.id, decision=AssessmentStatus.DEFERRED,
        rationale="needs field visit", reviewer="reviewer",
    )
    db.refresh(row)
    assert row.requires_rereview is False
    assert row.reviewed_evidence_hash == row.evidence_hash
    assert row.evidence_snapshot["relationship_type"] == row.relationship_type.value


def test_evidence_change_after_reject_flags_rereview(db, psi_pair):
    _, b, row = psi_pair
    matching_service.review_assessment(
        db, row.id, decision=AssessmentStatus.REJECTED,
        rationale="different administrative matters", reviewer="reviewer",
    )
    _change_evidence(db, b)
    matching_service.recompute_all(db, actor="pytest")
    db.refresh(row)
    assert row.status == AssessmentStatus.REJECTED
    assert row.requires_rereview is True


def test_evidence_change_after_defer_flags_rereview(db, psi_pair):
    _, b, row = psi_pair
    matching_service.review_assessment(
        db, row.id, decision=AssessmentStatus.DEFERRED,
        rationale="awaiting documents", reviewer="reviewer",
    )
    _change_evidence(db, b)
    matching_service.recompute_all(db, actor="pytest")
    db.refresh(row)
    assert row.status == AssessmentStatus.DEFERRED
    assert row.requires_rereview is True


def test_evidence_hash_is_stable_and_content_based():
    h1 = compute_evidence_hash("T", [{"a": 1}], [], [], 2)
    h2 = compute_evidence_hash("T", [{"a": 1}], [], [], 2)
    h3 = compute_evidence_hash("T", [{"a": 2}], [], [], 2)
    assert h1 and h1 == h2
    assert h1 != h3
