"""FIX 2 regression: evidence-version-aware lifecycle for informational
POTENTIAL_SAME_INCIDENT alerts.

Alert lifecycle:
  create when a new assessment qualifies; create when an EXISTING assessment
  newly qualifies (INSUFFICIENT/NO_RELATIONSHIP -> PSI); reuse on repeated
  recomputation; auto-resolve when the pair stops qualifying; reopen as the
  NEXT occurrence when the qualifying evidence returns; preserve all alert
  occurrences and human-review history at every step.
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.models import (
    AlertConditionState,
    AlertStatus,
    AlertType,
    AssessmentStatus,
    Bureau,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
    Institution,
    Priority,
    RelationshipAssessment,
    RelationshipReview,
    RelationshipType,
)
from app.services import matching_service

SPARSE = ("Lodged by caller." )  # thin, pair-wise disjoint text -> INSUFFICIENT_EVIDENCE
RICH_A = (
    "Regarding incident INC-2077-0001 at the hostel block. Incident dated "
    "2026-02-10. The warden was informed and fee receipts were submitted for "
    "verification by the grievance cell."
)
RICH_B = (
    "Follow-up on incident INC-2077-0001 at the hostel block. Incident dated "
    "2026-02-10. The warden was informed and fee receipts were submitted for "
    "verification by the grievance cell."
)
# different incident reference -> R6 conflict -> no longer PSI
RICH_B_OTHER = RICH_B.replace("INC-2077-0001", "INC-2077-0002")
# still PSI, but materially changed text -> evidence-hash changes
RICH_B_V2 = RICH_B + (
    " Complainant additionally filed an annex memo with photographs for "
    "review by the cell officer."
)


def _psi_alerts(db):
    return db.scalars(
        select(CoordinationAlert).where(
            CoordinationAlert.alert_type == AlertType.POTENTIAL_SAME_INCIDENT,
            CoordinationAlert.logical_key == "PSI:LIFE-PSI-1|LIFE-PSI-2",
        ).order_by(CoordinationAlert.occurrence)
    ).all()


def _active(db):
    return [a for a in _psi_alerts(db) if a.status != AlertStatus.RESOLVED]


@pytest.fixture()
def probe_pair(db):
    inst = Institution(
        permanent_id="PERM-PSI-PROBE", name="PSI Lifecycle Probe Institution",
        address="Synthetic", region="TEST", state="TEST", district="TEST",
        institution_type="Synthetic", is_demo=True,
    )
    db.add(inst)
    db.flush()
    rb = db.scalar(select(Bureau).where(Bureau.code == "RB"))
    pgrc = db.scalar(select(Bureau).where(Bureau.code == "PGRC"))
    a = ComplaintCase(
        case_id="LIFE-PSI-1", institution_id=inst.id, bureau_id=rb.id,
        receipt_date=date(2026, 2, 20), category="Fee Refund",
        subject="Sparse probe one", description="Lodged by caller.",
        status=CaseStatus.UNDER_PROCESS, priority=Priority.MEDIUM,
    )
    b = ComplaintCase(
        case_id="LIFE-PSI-2", institution_id=inst.id, bureau_id=pgrc.id,
        receipt_date=date(2026, 2, 21), category="Fee Refund",
        subject="Grievance counter filing", description="Fee receipt pending.",
        status=CaseStatus.UNDER_PROCESS, priority=Priority.MEDIUM,
    )
    db.add_all([a, b])
    db.commit()
    yield inst, a, b
    # cleanup: reviews -> alerts -> states -> assessments -> cases -> institution
    for row in db.scalars(select(RelationshipAssessment).where(
            RelationshipAssessment.institution_id == inst.id)).all():
        for rv in db.scalars(select(RelationshipReview).where(
                RelationshipReview.assessment_id == row.id)).all():
            db.delete(rv)
    for al in db.scalars(select(CoordinationAlert).where(
            CoordinationAlert.institution_id == inst.id)).all():
        db.delete(al)
    for st in db.scalars(select(AlertConditionState)).all():
        if st.logical_key.startswith("PSI:LIFE-PSI"):
            db.delete(st)
    db.flush()
    for row in db.scalars(select(RelationshipAssessment).where(
            RelationshipAssessment.institution_id == inst.id)).all():
        db.delete(row)
    db.delete(a)
    db.delete(b)
    db.flush()
    db.delete(inst)
    db.commit()


def _assessment(db):
    return db.scalar(select(RelationshipAssessment).where(
        RelationshipAssessment.pair_key == "LIFE-PSI-1|LIFE-PSI-2"))


# 1. insufficient evidence -> newly qualifies -> informational alert created
def test_insufficient_pair_newly_qualifying_opens_alert(db, probe_pair):
    inst, a, b = probe_pair
    r0 = matching_service.recompute_all(db, actor="pytest")
    row = _assessment(db)
    assert row.relationship_type == RelationshipType.INSUFFICIENT_EVIDENCE
    assert _active(db) == [], "no informational alert while evidence is insufficient"

    # officer enriches both narratives with the same incident reference
    a.description, a.subject = RICH_A, "Incident INC-2077-0001 at hostel block"
    b.description, b.subject = RICH_B, "Same incident INC-2077-0001 follow-up"
    db.commit()
    r1 = matching_service.recompute_all(db, actor="pytest")
    db.refresh(row)
    assert row.relationship_type == RelationshipType.POTENTIAL_SAME_INCIDENT
    assert r1.alerts_created == 1
    alerts = _active(db)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.occurrence == 1
    assert alert.assessment_id == row.id, "alert links the assessment"
    assert alert.evidence_hash == row.evidence_hash, "alert links the evidence version"
    assert "automated recommendation" in alert.description
    state = db.get(AlertConditionState, "PSI:LIFE-PSI-1|LIFE-PSI-2")
    assert state.present is True and state.occurrences == 1


# 2. losing supporting evidence -> stale active alert auto-resolves, history kept
def test_qualifying_pair_losing_evidence_resolves_alert(db, probe_pair):
    inst, a, b = probe_pair
    a.description, a.subject = RICH_A, "Incident INC-2077-0001 at hostel block"
    b.description, b.subject = RICH_B, "Same incident INC-2077-0001 follow-up"
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    assert len(_active(db)) == 1

    b.description, b.subject = RICH_B_OTHER, "Different incident INC-2077-0002"
    db.commit()
    r = matching_service.recompute_all(db, actor="pytest")
    row = _assessment(db)
    assert row.relationship_type == RelationshipType.NO_RELATIONSHIP_ESTABLISHED
    alerts = _psi_alerts(db)
    assert len(alerts) == 1, "historical occurrence preserved"
    assert alerts[0].status == AlertStatus.RESOLVED
    assert alerts[0].resolved_by == "system (auto)"
    assert "NO_RELATIONSHIP_ESTABLISHED" in (alerts[0].resolution_note or "")
    assert _active(db) == []
    state = db.get(AlertConditionState, "PSI:LIFE-PSI-1|LIFE-PSI-2")
    assert state.present is False


# 3. repeated recomputation must reuse the active alert and create nothing
def test_repeated_recompute_no_duplicate_informational_alerts(db, probe_pair):
    inst, a, b = probe_pair
    a.description, a.subject = RICH_A, "Incident INC-2077-0001 at hostel block"
    b.description, b.subject = RICH_B, "Same incident INC-2077-0001 follow-up"
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    n = len(_psi_alerts(db))
    first = _active(db)[0]
    for _ in range(3):
        r = matching_service.recompute_all(db, actor="pytest")
        assert r.alerts_created == 0
    assert len(_psi_alerts(db)) == n == 1
    assert len(_active(db)) == 1
    assert _active(db)[0].id == first.id, "same alert row reused"


# 4. qualifying evidence returns later -> NEXT occurrence, history intact
def test_returning_qualifying_evidence_opens_next_occurrence(db, probe_pair):
    inst, a, b = probe_pair
    a.description, a.subject = RICH_A, "Incident INC-2077-0001 at hostel block"
    b.description, b.subject = RICH_B, "Same incident INC-2077-0001 follow-up"
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    b.description, b.subject = RICH_B_OTHER, "Different incident INC-2077-0002"
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    assert _active(db) == []
    # evidence returns
    b.description, b.subject = RICH_B, "Same incident INC-2077-0001 follow-up"
    db.commit()
    r = matching_service.recompute_all(db, actor="pytest")
    assert r.alerts_created == 1
    alerts = _psi_alerts(db)
    assert [x.occurrence for x in alerts] == [1, 2]
    assert alerts[0].status == AlertStatus.RESOLVED      # occurrence 1 history intact
    assert alerts[1].status == AlertStatus.OPEN          # new occurrence active
    assert alerts[1].assessment_id == alerts[0].assessment_id
    state = db.get(AlertConditionState, "PSI:LIFE-PSI-1|LIFE-PSI-2")
    assert state.present is True and state.occurrences == 2


# 5. human review + review history survive the full alert lifecycle
def test_review_history_and_decisions_survive_alert_lifecycle(db, probe_pair):
    inst, a, b = probe_pair
    a.description, a.subject = RICH_A, "Incident INC-2077-0001 at hostel block"
    b.description, b.subject = RICH_B, "Same incident INC-2077-0001 follow-up"
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    row = _assessment(db)
    matching_service.review_assessment(
        db, row.id, decision=AssessmentStatus.CONFIRMED,
        rationale="checked with both bureaus", reviewer="reviewer",
    )
    # still-qualifying evidence change: same incident, date +1 day
    b.description = RICH_B_V2
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    db.refresh(row)
    assert row.relationship_type == RelationshipType.POTENTIAL_SAME_INCIDENT
    assert row.status == AssessmentStatus.CONFIRMED
    assert row.requires_rereview is True, "evidence changed under human decision"
    active = _active(db)
    assert len(active) == 1, "qualifying pair keeps ONE active alert"
    assert active[0].evidence_hash == row.evidence_hash, "active alert tracks fresh evidence"

    # re-review, then the evidence disappears and returns
    matching_service.review_assessment(
        db, row.id, decision=AssessmentStatus.DEFERRED,
        rationale="re-checked; awaiting originals", reviewer="reviewer",
    )
    b.description, b.subject = RICH_B_OTHER, "Different incident INC-2077-0002"
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    assert _active(db) == []
    b.description, b.subject = RICH_B, "Same incident INC-2077-0001 follow-up"
    db.commit()
    matching_service.recompute_all(db, actor="pytest")
    db.refresh(row)

    assert row.status == AssessmentStatus.DEFERRED, "decision preserved end-to-end"
    reviews = db.scalars(select(RelationshipReview).where(
        RelationshipReview.assessment_id == row.id).order_by(RelationshipReview.reviewed_at)).all()
    assert [r.decision.value for r in reviews] == ["CONFIRMED", "DEFERRED"]
    assert {r.evidence_hash for r in reviews} == {
        reviews[0].evidence_hash, reviews[1].evidence_hash}, "history rows keep own hashes"
    assert reviews[0].evidence_snapshot is not None and reviews[1].evidence_snapshot is not None
    alerts = _psi_alerts(db)
    assert [x.occurrence for x in alerts] == [1, 2]
    assert [x.id for x in alerts] == sorted(x.id for x in alerts)
    # informational alerts stay distinct from cross-bureau coordination alerts
    xb = db.scalars(select(CoordinationAlert).where(
        CoordinationAlert.institution_id == inst.id,
        CoordinationAlert.alert_type == AlertType.CROSS_BUREAU_COORDINATION)).all()
    assert all(a.logical_key.startswith("XBUREAU:") for a in xb)
