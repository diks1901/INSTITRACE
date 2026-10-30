"""Runs the rule-based matching engine across same-institution case pairs and
persists explainable assessments. Human review decisions (CONFIRMED /
REJECTED / DEFERRED, plus reviewer and rationale) are ALWAYS preserved across
recomputation - only the automated recommendation fields are refreshed.
"""
from itertools import combinations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..clock import now
from ..config import get_settings
from ..matching import engine
from ..models import (
    AlertStatus,
    AlertType,
    AssessmentStatus,
    ComplaintCase,
    CoordinationAlert,
    RelationshipAssessment,
    RelationshipReview,
    RelationshipType,
)
from ..schemas import RecomputeResult
from .audit import record_audit

import hashlib
import json


def compute_evidence_hash(relationship_type, supporting, conflicting, missing, score,
                          rule_version: str = "") -> str:
    """Deterministic fingerprint of the material evidence behind an assessment.

    Used to pin human decisions to the exact evidence the reviewer saw. The
    rule-engine version is part of the fingerprint (FIX 3): a decision made
    under one version of the rule semantics must NOT tacitly cover evidence
    produced under a different version, even when the serialized evidence
    looks identical.
    """
    payload = json.dumps(
        {
            "relationship_type": str(relationship_type.value if hasattr(relationship_type, "value") else relationship_type),
            "supporting": supporting,
            "conflicting": conflicting,
            "missing": missing,
            "score": score,
            "rule_version": rule_version,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def recompute_all(db: Session, actor: str = "system") -> RecomputeResult:
    settings = get_settings()
    version = settings.rule_engine_version
    now_dt = now()

    cases = list(db.scalars(select(ComplaintCase)))
    existing: dict[str, RelationshipAssessment] = {
        a.pair_key: a for a in db.scalars(select(RelationshipAssessment))
    }
    created = updated = preserved = 0
    alerts_created = 0

    by_institution: dict[int, list[ComplaintCase]] = {}
    for c in cases:
        by_institution.setdefault(c.institution_id, []).append(c)

    for _inst_id, inst_cases in sorted(by_institution.items()):
        for case_a, case_b in combinations(sorted(inst_cases, key=lambda c: c.case_id), 2):
            result = engine.evaluate_pair(case_a, case_b, version)
            if result is None:  # different institutions - never assessed
                continue
            key = engine.pair_key(case_a.case_id, case_b.case_id)
            new_hash = compute_evidence_hash(
                result.relationship_type, result.supporting_evidence,
                result.conflicting_evidence, result.missing_evidence, result.score,
                rule_version=version,
            )
            row = existing.get(key)
            if row is None:
                row = RelationshipAssessment(
                    pair_key=key,
                    source_case_id=case_a.id,
                    candidate_case_id=case_b.id,
                    institution_id=case_a.institution_id,
                    relationship_type=result.relationship_type,
                    supporting_evidence=result.supporting_evidence,
                    conflicting_evidence=result.conflicting_evidence,
                    missing_evidence=result.missing_evidence,
                    rules_fired=result.rules_fired,
                    score=result.score,
                    rule_version=version,
                    evidence_hash=new_hash,
                    status=AssessmentStatus.PENDING_REVIEW,
                    created_at=now_dt,
                    last_recomputed_at=now_dt,
                )
                db.add(row)
                db.flush()
                created += 1
                record_audit(
                    db, actor=actor, event_type="ASSESSMENT_CREATED",
                    entity_type="relationship_assessment", entity_id=str(row.id),
                    summary=f"Assessment {row.relationship_type.value} for {key}",
                    after={"type": row.relationship_type.value, "rule_version": version},
                )
                # A potential same-incident assessment ALSO raises an
                # informational alert (dedupe prevents duplicates).
                if result.relationship_type == RelationshipType.POTENTIAL_SAME_INCIDENT:
                    dedupe = f"PSI:{key}"
                    if not db.scalar(
                        select(CoordinationAlert).where(CoordinationAlert.dedupe_key == dedupe)
                    ):
                        db.add(
                            CoordinationAlert(
                                alert_type=AlertType.POTENTIAL_SAME_INCIDENT,
                                institution_id=case_a.institution_id,
                                case_ids=[case_a.case_id, case_b.case_id],
                                title=f"Potential same-incident relationship suggested - {key}",
                                description=(
                                    "The rule engine found supporting evidence that cases "
                                    f"{case_a.case_id} and {case_b.case_id} may concern the same "
                                    "incident. This is an automated recommendation requiring "
                                    "human review - no records are merged or changed."
                                ),
                                dedupe_key=dedupe,
                                logical_key=dedupe,
                                occurrence=1,
                                created_at=now_dt,
                            )
                        )
                        alerts_created += 1
            else:
                was_reviewed = row.status in (
                    AssessmentStatus.CONFIRMED,
                    AssessmentStatus.REJECTED,
                    AssessmentStatus.DEFERRED,
                )
                if was_reviewed:
                    preserved += 1
                # refresh automated recommendation fields only
                changed = (
                    row.relationship_type != result.relationship_type
                    or row.supporting_evidence != result.supporting_evidence
                    or row.conflicting_evidence != result.conflicting_evidence
                    or row.missing_evidence != result.missing_evidence
                    or row.rules_fired != result.rules_fired
                    or row.score != result.score
                    or row.rule_version != version
                )
                if changed:
                    before = {"type": row.relationship_type.value, "rule_version": row.rule_version}
                    # Evidence-version pinning (FIX 3): if a human already
                    # decided and the material evidence changed since their
                    # review, keep the decision visible but flag it OUTDATED -
                    # never display an old decision as if it covers new evidence.
                    evidence_changed = (
                        was_reviewed
                        and row.reviewed_evidence_hash is not None
                        and new_hash != row.reviewed_evidence_hash
                    )
                    row.relationship_type = result.relationship_type
                    row.supporting_evidence = result.supporting_evidence
                    row.conflicting_evidence = result.conflicting_evidence
                    row.missing_evidence = result.missing_evidence
                    row.rules_fired = result.rules_fired
                    row.score = result.score
                    row.rule_version = version
                    row.evidence_hash = new_hash
                    updated += 1
                    if was_reviewed:
                        record_audit(
                            db, actor=actor, event_type="ASSESSMENT_RECOMPUTED",
                            entity_type="relationship_assessment", entity_id=str(row.id),
                            summary="Automated recommendation refreshed; human decision preserved",
                            before=before,
                            after={"type": row.relationship_type.value, "rule_version": version},
                        )
                        if evidence_changed:
                            row.requires_rereview = True
                            record_audit(
                                db, actor=actor, event_type="ASSESSMENT_EVIDENCE_CHANGED",
                                entity_type="relationship_assessment", entity_id=str(row.id),
                                summary="Evidence changed after human decision; re-review required",
                                meta={"reviewed_evidence_hash": row.reviewed_evidence_hash,
                                      "current_evidence_hash": new_hash,
                                      "preserved_decision": row.status.value},
                            )
                row.last_recomputed_at = now_dt

    db.commit()
    return RecomputeResult(
        assessments_created=created,
        assessments_updated=updated,
        alerts_created=alerts_created,
        human_decisions_preserved=preserved,
    )


def review_assessment(db: Session, assessment_id: int, *, decision: AssessmentStatus,
                      rationale: str, reviewer: str) -> RelationshipAssessment:
    row = db.get(RelationshipAssessment, assessment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if decision not in (
        AssessmentStatus.CONFIRMED,
        AssessmentStatus.REJECTED,
        AssessmentStatus.DEFERRED,
    ):
        raise HTTPException(
            status_code=422,
            detail="Review decision must be CONFIRMED, REJECTED or DEFERRED",
        )
    before = {
        "status": row.status.value,
        "reviewer": row.reviewer_identity,
        "rationale": row.reviewer_rationale,
    }
    row.status = decision
    row.reviewer_identity = reviewer
    row.reviewer_rationale = rationale
    row.reviewed_at = now()
    # Pin the decision to the exact evidence the reviewer saw (FIX 3).
    row.evidence_snapshot = {
        "relationship_type": row.relationship_type.value,
        "supporting_evidence": row.supporting_evidence,
        "conflicting_evidence": row.conflicting_evidence,
        "missing_evidence": row.missing_evidence,
        "score": row.score,
        "rule_version": row.rule_version,
        "reviewed_at": row.reviewed_at.isoformat(),
    }
    row.reviewed_evidence_hash = row.evidence_hash or compute_evidence_hash(
        row.relationship_type, row.supporting_evidence, row.conflicting_evidence,
        row.missing_evidence, row.score, rule_version=row.rule_version,
    )
    row.requires_rereview = False
    # Append-only review history (FIX 2): every decision - including every
    # RE-review - is preserved with the evidence snapshot/hash and rule-engine
    # version it was made against. The assessment row keeps only the latest
    # state; the full history lives in relationship_reviews and is never erased.
    db.add(
        RelationshipReview(
            assessment_id=row.id,
            decision=decision,
            reviewer_identity=reviewer,
            reviewer_rationale=rationale,
            reviewed_at=row.reviewed_at,
            evidence_snapshot=dict(row.evidence_snapshot),
            evidence_hash=row.reviewed_evidence_hash,
            rule_version=row.rule_version,
        )
    )
    record_audit(
        db, actor=reviewer, event_type="ASSESSMENT_REVIEWED",
        entity_type="relationship_assessment", entity_id=str(row.id),
        summary=f"Review decision: {decision.value}", rationale=rationale,
        before=before,
        after={"status": decision.value, "reviewer": reviewer, "rationale": rationale},
        meta={"pair_key": row.pair_key},
    )
    db.commit()
    db.refresh(row)
    return row


def count_open(db: Session) -> int:
    return db.scalar(
        select(func.count(CoordinationAlert.id)).where(
            CoordinationAlert.status != AlertStatus.RESOLVED
        )
    ) or 0
