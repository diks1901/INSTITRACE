"""Matching engine unit tests + recomputation behavior tests.

Covers the mandated scenarios A-E and the critical safeguards on recomputation.
"""
from datetime import date, timedelta

from sqlalchemy import func, select

from app import clock
from app.matching import engine
from app.models import (
    AlertStatus,
    AlertType,
    AssessmentStatus,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
    RelationshipAssessment,
    RelationshipType,
)
from app.seed import seed_demo
from app.services import alert_service, matching_service

from .conftest import get_case_by_uid, pair


def test_scenario_a_shared_incident_ref_cross_bureau(db):
    """Same institution + shared incident reference across bureaus ->
    POTENTIAL_SAME_INCIDENT, and a cross-bureau coordination alert exists."""
    assessment = pair(db, "DEMO-CASE-001", "DEMO-CASE-002")
    assert assessment is not None
    assert assessment.relationship_type == RelationshipType.POTENTIAL_SAME_INCIDENT
    assert (assessment.score or 0) >= engine.SAME_INCIDENT_MIN_SUPPORT
    assert any("INC-2025-0042" in ev["detail"] for ev in assessment.supporting_evidence)
    assert "R1_SHARED_INCIDENT_REFERENCE" in assessment.rules_fired

    xb_alerts = db.scalars(
        select(CoordinationAlert).where(
            CoordinationAlert.alert_type == AlertType.CROSS_BUREAU_COORDINATION
        )
    ).all()
    alert = next(
        (a for a in xb_alerts if "DEMO-CASE-001" in (a.case_ids or [])), None
    )
    assert alert is not None
    assert "DEMO-CASE-002" in alert.case_ids
    # The alert must NOT claim the cases concern one incident.
    assert "does NOT assert" in alert.description


def test_scenario_b_distinct_refs_contradictory(db):
    """Same institution, distinct incident references, far-apart dates ->
    NO_RELATIONSHIP_ESTABLISHED with recorded conflicting evidence."""
    assessment = pair(db, "DEMO-CASE-003", "DEMO-CASE-004")
    assert assessment.relationship_type == RelationshipType.NO_RELATIONSHIP_ESTABLISHED
    assert "R6_DISTINCT_INCIDENT_REFERENCES" in assessment.rules_fired
    assert assessment.conflicting_evidence, "expected contradictory evidence recorded"


def test_scenario_c_insufficient_evidence(db):
    """Sparse records -> INSUFFICIENT_EVIDENCE with missing-evidence inventory.
    Missing evidence is not treated as negative evidence."""
    assessment = pair(db, "DEMO-CASE-005", "DEMO-CASE-006")
    assert assessment.relationship_type == RelationshipType.INSUFFICIENT_EVIDENCE
    assert assessment.missing_evidence
    assert assessment.score is None


def test_scenario_d_same_incident_same_bureau(db):
    """Credible shared evidence within one bureau -> POTENTIAL_SAME_INCIDENT
    and NO cross-bureau coordination alert for that institution alone."""
    assessment = pair(db, "DEMO-CASE-007", "DEMO-CASE-008")
    assert assessment.relationship_type == RelationshipType.POTENTIAL_SAME_INCIDENT

    case = get_case_by_uid(db, "DEMO-CASE-007")
    alerts = db.scalars(
        select(CoordinationAlert).where(
            CoordinationAlert.alert_type == AlertType.CROSS_BUREAU_COORDINATION,
            CoordinationAlert.institution_id == case.institution_id,
            CoordinationAlert.status != AlertStatus.RESOLVED,
        )
    ).all()
    assert alerts == [], "same bureau assignments must not raise cross-bureau alerts"


def test_scenario_e_different_institutions_not_assessed(db):
    """Similar wording across different institutions produces no assessment."""
    assert pair(db, "DEMO-CASE-009", "DEMO-CASE-010") is None


def test_text_similarity_alone_insufficient():
    """Guard: wording overlap can never, by itself, reach MIN_SUPPORT."""
    from app.models import ComplaintCase as CC
    from app.models import CaseStatus as CS, Priority

    kw = dict(institution_id=1, receipt_date=date(2025, 1, 1), category="Fees & Refund",
              bureau_id=1, priority=Priority.MEDIUM, status=CS.UNDER_PROCESS)
    a = CC(id=1, case_id="X-1", subject="Hostel fee refund not processed after admission " 
           "withdrawal requested by student", description="Student withdrew admission and "
           "requests hostel fee refund. No incident reference given.", **kw)
    b = CC(id=2, case_id="X-2", subject="Hostel fee refund not processed after admission "
           "withdrawal requested by student", description="Student withdrew admission before "
           "classes and requests hostel fee refund. No incident reference.", **kw)
    result = engine.evaluate_pair(a, b, "1.0.0")
    assert result is not None
    assert result.relationship_type != RelationshipType.POTENTIAL_SAME_INCIDENT


def test_repeat_recompute_creates_no_duplicates(db):
    before_a = db.scalar(select(func.count(RelationshipAssessment.id)))
    before_al = db.scalar(select(func.count(CoordinationAlert.id)))
    r1 = matching_service.recompute_all(db, actor="pytest")
    alert_service.evaluate_alerts(db)
    after_a = db.scalar(select(func.count(RelationshipAssessment.id)))
    after_al = db.scalar(select(func.count(CoordinationAlert.id)))
    assert before_a == after_a, "recompute must not create duplicate assessments"
    # Alert semantics (FIX 1): a condition that disappears and returns opens a
    # NEW occurrence, so global alert-row counts may legitimately grow when an
    # earlier test pinned the clock and changed conditions. The real invariant
    # is: at a steady state, re-evaluating creates nothing and there is at
    # most one ACTIVE alert per condition key.
    steady = alert_service.evaluate_alerts(db)
    again = alert_service.evaluate_alerts(db)  # unchanged conditions -> no work
    assert again["alerts_created"] == 0
    assert again["alerts_auto_resolved"] == 0
    _ = steady
    assert r1.assessments_created == 0
    assert r1.alerts_created == 0
    # at most one ACTIVE alert per condition key across the whole table
    active_keys = [
        a.logical_key
        for a in db.scalars(
            select(CoordinationAlert).where(CoordinationAlert.status != AlertStatus.RESOLVED)
        ).all()
        if a.logical_key
    ]
    assert len(active_keys) == len(set(active_keys)), "duplicate active alert for same condition"


def test_human_decision_preserved_across_recompute(db):
    """CONFIRMED/REJECTED decisions survive recomputation; automated fields
    may refresh but reviewer/rationale/decision must persist."""
    target = pair(db, "DEMO-CASE-001", "DEMO-CASE-002")
    assert target.status == AssessmentStatus.CONFIRMED
    reviewer_before = target.reviewer_identity
    rationale_before = target.reviewer_rationale

    matching_service.recompute_all(db, actor="pytest")
    db.refresh(target)
    assert target.status == AssessmentStatus.CONFIRMED
    assert target.reviewer_identity == reviewer_before
    assert target.reviewer_rationale == rationale_before
    assert target.last_recomputed_at is not None


def test_rule_version_stamped_and_refresh(db):
    from app.config import get_settings

    assessment = pair(db, "DEMO-CASE-001", "DEMO-CASE-002")
    assert assessment.rule_version == get_settings().rule_engine_version
    # each supporting evidence item carries its rule name, version and type
    for ev in assessment.supporting_evidence:
        assert ev["rule"].startswith("R")
        assert ev["rule_version"]
        assert ev["type"] in {
            "INCIDENT_REFERENCE", "PROCEEDING_REFERENCE", "DATE_COMPATIBILITY",
            "TEXT_CORROBORATION", "SOURCE_RECORD_PROVENANCE", "CASE_CROSS_REFERENCE",
        }


def test_engine_rejects_self_pair(db):
    import pytest

    case = get_case_by_uid(db, "DEMO-CASE-001")
    with pytest.raises(ValueError):
        engine.evaluate_pair(case, case, "1.0.0")


# ------------------------------------------------------------- FIX 2 ----------
# source_record_ref (provenance) is NOT an incident reference. It must never
# confirm, or contribute support toward, POTENTIAL_SAME_INCIDENT.

def _probe_case(id_, uid, source_ref=None, description="No incident reference given."):
    from app.models import ComplaintCase as CC
    from app.models import CaseStatus as CS, Priority

    return CC(
        id=id_, case_id=uid, institution_id=1,
        receipt_date=date(2026, 1, 10), category="Fee Refund",
        subject=f"Synthetic provenance probe {uid}",
        description=description,
        status=CS.UNDER_PROCESS, bureau_id=1, priority=Priority.MEDIUM,
        source_record_ref=source_ref,
    )


def test_shared_source_record_ref_is_procedural_never_psi():
    """Identical source_record_ref -> PROCEDURAL_LINK with SOURce-record
    provenance evidence; it must NOT produce POTENTIAL_SAME_INCIDENT."""
    a = _probe_case(1, "P-1", source_ref="AICTE/2025/R-44881")
    b = _probe_case(2, "P-2", source_ref="AICTE/2025/R-44881")
    result = engine.evaluate_pair(a, b, "1.1.0")
    assert result is not None
    assert result.relationship_type == RelationshipType.PROCEDURAL_LINK
    assert (result.score or 0) < engine.SAME_INCIDENT_MIN_SUPPORT
    prov = [ev for ev in result.supporting_evidence if ev.get("type") == "SOURCE_RECORD_PROVENANCE"]
    assert prov, "shared source record must be recorded as provenance evidence"
    assert "AICTE/2025/R-44881" in prov[0]["detail"]


def test_shared_source_ref_plus_similar_text_still_not_psi():
    """Even with highly similar narratives, a shared source_record_ref alone
    can never reach the PSI support threshold (provenance weight is 0)."""
    text = ("Student withdrew admission and requests hostel fee refund. "
            "Refund pending since January at the north block hostel office.")
    a = _probe_case(1, "P-3", source_ref="AICTE/2025/R-44881", description=text)
    b = _probe_case(2, "P-4", source_ref="AICTE/2025/R-44881", description=text)
    result = engine.evaluate_pair(a, b, "1.1.0")
    assert result is not None
    assert result.relationship_type != RelationshipType.POTENTIAL_SAME_INCIDENT
    assert (result.score or 0) < engine.SAME_INCIDENT_MIN_SUPPORT


def test_different_source_record_refs_not_procedural():
    """Non-matching source refs prove nothing: no procedural link, no PSI."""
    a = _probe_case(1, "P-5", source_ref="AICTE/2025/R-10001")
    b = _probe_case(2, "P-6", source_ref="AICTE/2025/R-20002")
    result = engine.evaluate_pair(a, b, "1.1.0")
    assert result.relationship_type != RelationshipType.PROCEDURAL_LINK
    assert result.relationship_type != RelationshipType.POTENTIAL_SAME_INCIDENT
    assert not any(ev.get("type") == "SOURCE_RECORD_PROVENANCE"
                   for ev in result.supporting_evidence)


def test_shared_incident_reference_still_psi():
    """Explicit shared incident reference in the narrative remains a strong
    automatic signal (R1) even when source_record_refs differ."""
    text_a = ("Regarding incident INC-2030-0777 at the examination hall. "
              "Incident dated 2030-02-10, reported to the grievance cell the same day.")
    text_b = ("Follow-up on incident INC-2030-0777 at the examination hall. "
              "Incident dated 2030-02-10, reported to the grievance cell the same day.")
    a = _probe_case(1, "P-7", source_ref="AICTE/2030/R-1", description=text_a)
    b = _probe_case(2, "P-8", source_ref="AICTE/2030/R-2", description=text_b)
    result = engine.evaluate_pair(a, b, "1.1.0")
    assert result.relationship_type == RelationshipType.POTENTIAL_SAME_INCIDENT
    assert (result.score or 0) >= engine.SAME_INCIDENT_MIN_SUPPORT
    inc = [ev for ev in result.supporting_evidence if ev.get("type") == "INCIDENT_REFERENCE"]
    assert inc and "INC-2030-0777" in inc[0]["detail"]


def test_institution_identity_alone_never_assesses_psi(db):
    """Belonging to the same institution is never, by itself, evidence of a
    shared incident: sparse same-institution cases yield INSUFFICIENT_EVIDENCE."""
    assessment = pair(db, "DEMO-CASE-005", "DEMO-CASE-006")
    assert assessment.relationship_type == RelationshipType.INSUFFICIENT_EVIDENCE
    assert assessment.score is None
