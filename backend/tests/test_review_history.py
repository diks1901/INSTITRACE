"""FIX 2 regression: append-only review history, and FIX 3 regression:
rule-engine version participates in the evidence fingerprint.

Every human decision (CONFIRMED / REJECTED / DEFERRED) is preserved forever in
`relationship_reviews` together with the exact evidence snapshot, hash and
rule-engine version it was made against. Re-reviews never erase earlier rows,
and a rule-engine VERSION change - even with byte-identical evidence output -
flags the preserved decision as requiring re-review.
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    AssessmentStatus,
    Bureau,
    CaseStatus,
    ComplaintCase,
    Institution,
    Priority,
    RelationshipAssessment,
    RelationshipReview,
    RelationshipType,
)
from app.services import matching_service
from app.services.matching_service import compute_evidence_hash


BASE_TEXT = (
    "Regarding incident INC-2099-0001 at the hostel block. Incident dated "
    "2026-01-10. The warden was informed and fee receipts were submitted for "
    "verification by the grievance cell."
)
CHANGED_TEXT = BASE_TEXT.replace("INC-2099-0001", "INC-2099-0002")


@pytest.fixture()
def psi_pair(db):
    inst = Institution(
        permanent_id="PERM-RH-PROBE", name="Review History Probe Institution",
        address="Synthetic", region="TEST", state="TEST", district="TEST",
        institution_type="Synthetic", is_demo=True,
    )
    db.add(inst)
    db.flush()
    rb = db.scalar(select(Bureau).where(Bureau.code == "RB"))
    a = ComplaintCase(
        case_id="LIFE-RH-1", institution_id=inst.id, bureau_id=rb.id,
        receipt_date=date(2026, 1, 15), category="Fee Refund",
        subject="Hostel fee issue regarding incident INC-2099-0001",
        description=BASE_TEXT, status=CaseStatus.UNDER_PROCESS, priority=Priority.MEDIUM,
    )
    b = ComplaintCase(
        case_id="LIFE-RH-2", institution_id=inst.id, bureau_id=rb.id,
        receipt_date=date(2026, 1, 16), category="Fee Refund",
        subject="Fee verification for incident INC-2099-0001",
        description=BASE_TEXT, status=CaseStatus.UNDER_PROCESS, priority=Priority.MEDIUM,
    )
    db.add_all([a, b])
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    row = db.scalar(
        select(RelationshipAssessment).where(
            RelationshipAssessment.pair_key == "LIFE-RH-1|LIFE-RH-2"
        )
    )
    assert row is not None
    yield a, b, row
    for extra in db.scalars(
        select(RelationshipReview).where(RelationshipReview.assessment_id == row.id)
    ).all():
        db.delete(extra)
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


def _history(db, assessment_id: int) -> list[RelationshipReview]:
    return db.scalars(
        select(RelationshipReview)
        .where(RelationshipReview.assessment_id == assessment_id)
        .order_by(RelationshipReview.reviewed_at, RelationshipReview.id)
    ).all()


def test_full_review_lifecycle_preserves_every_decision(db, psi_pair, client, tokens):
    _, b, row = psi_pair
    aid = row.id

    # 1. initial confirmation -> first history row
    matching_service.review_assessment(
        db, aid, decision=AssessmentStatus.CONFIRMED,
        rationale="confirmed after field verification", reviewer="reviewer",
    )
    history = _history(db, aid)
    assert len(history) == 1
    first = history[0]
    assert first.decision == AssessmentStatus.CONFIRMED
    assert first.reviewer_identity == "reviewer"
    assert first.reviewer_rationale == "confirmed after field verification"
    assert first.reviewed_at is not None
    assert first.evidence_hash
    assert first.rule_version == get_settings().rule_engine_version
    assert first.evidence_snapshot["relationship_type"] == "POTENTIAL_SAME_INCIDENT"
    first_hash = first.evidence_hash
    first_snapshot_type = first.evidence_snapshot["relationship_type"]

    # 2. evidence modification -> recompute flags the preserved decision
    b.subject = "Fee verification for incident INC-2099-0002"
    b.description = CHANGED_TEXT
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    db.refresh(row)
    assert row.requires_rereview is True

    # 3. re-review with a DIFFERENT decision -> second history row, first intact
    matching_service.review_assessment(
        db, aid, decision=AssessmentStatus.REJECTED,
        rationale="facts changed; not the same episode", reviewer="manager-as-reviewer",
    )
    db.refresh(row)
    assert row.status == AssessmentStatus.REJECTED
    assert row.requires_rereview is False

    history = _history(db, aid)
    assert len(history) == 2, "both decisions preserved - re-review never erases"
    second = history[1]
    assert second.decision == AssessmentStatus.REJECTED
    assert second.evidence_snapshot["relationship_type"] == row.relationship_type.value
    assert second.evidence_hash != first_hash, "each decision keeps ITS OWN evidence hash"

    # 4. both decisions remain accessible through the API, newest first
    resp = client.get(f"/api/v1/relationships/{aid}/reviews",
                      headers=tokens["admin"])
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 2
    assert payload[0]["decision"] == "REJECTED"     # newest first
    assert payload[1]["decision"] == "CONFIRMED"
    assert payload[0]["assessment_id"] == aid

    # 5. each history row retains its ORIGINAL snapshot + hash
    assert payload[1]["evidence_hash"] == first_hash
    assert payload[1]["evidence_snapshot"]["relationship_type"] == first_snapshot_type
    assert payload[0]["evidence_hash"] == row.reviewed_evidence_hash
    assert payload[0]["rule_version"] == get_settings().rule_engine_version

    # unknown assessment -> 404
    resp = client.get("/api/v1/relationships/999999/reviews", headers=tokens["admin"])
    assert resp.status_code == 404


def test_rule_version_change_with_identical_evidence_flags_rereview(db, psi_pair, monkeypatch):
    """FIX 3: bump the rule-engine version, keep the evidence output IDENTICAL,
    recompute -> the preserved decision must require re-review."""
    _, _, row = psi_pair
    matching_service.review_assessment(
        db, row.id, decision=AssessmentStatus.CONFIRMED, rationale="ok", reviewer="reviewer",
    )
    db.refresh(row)
    old_hash = row.reviewed_evidence_hash
    assert row.evidence_snapshot["rule_version"] == "1.1.0"

    # identical inputs but a different rule-engine version must hash differently
    h_old = compute_evidence_hash("T", [{"a": 1}], [], [], 2, rule_version="1.1.0")
    h_new = compute_evidence_hash("T", [{"a": 1}], [], [], 2, rule_version="9.9.9")
    assert h_old != h_new, "version must be part of the fingerprint"

    monkeypatch.setenv("INSTITRACE_RULE_ENGINE_VERSION", "9.9.9-regression-test")
    get_settings.cache_clear()
    try:
        matching_service.recompute_all(db, actor="pytest")
        db.refresh(row)
        assert row.rule_version == "9.9.9-regression-test"
        assert row.status == AssessmentStatus.CONFIRMED, "decision preserved"
        assert row.reviewer_identity == "reviewer"
        assert row.requires_rereview is True, "stale-version decision must be flagged"
        assert row.reviewed_evidence_hash == old_hash
        assert row.evidence_snapshot["rule_version"] == "1.1.0", "old snapshot kept"
    finally:
        get_settings.cache_clear()


def test_seed_decisions_exist_in_history(db):
    """The two seeded human decisions must also be visible in review history."""
    from .conftest import pair

    confirmed = pair(db, "DEMO-CASE-001", "DEMO-CASE-002")
    rejected = pair(db, "DEMO-CASE-003", "DEMO-CASE-004")
    for assessment, expected in (
        (confirmed, AssessmentStatus.CONFIRMED),
        (rejected, AssessmentStatus.REJECTED),
    ):
        history = _history(db, assessment.id)
        assert history, f"seeded {expected.value} decision missing from history"
        assert history[0].decision == expected
        assert history[0].evidence_snapshot is not None
        assert history[0].rule_version


def test_evidence_hash_includes_rule_version():
    """Unit-level guarantee for FIX 3 (isolated from evidence content)."""
    args = ("T", [{"a": 1}], [], [], 2)
    assert compute_evidence_hash(*args, rule_version="1.1.0") == compute_evidence_hash(
        *args, rule_version="1.1.0")
    assert compute_evidence_hash(*args, rule_version="1.1.0") != compute_evidence_hash(
        *args, rule_version="1.1.1")
