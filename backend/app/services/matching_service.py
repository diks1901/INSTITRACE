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
    AlertConditionState,
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


def _psi_alert_lifecycle(
    db: Session, *, qualifies: bool, key: str, row: RelationshipAssessment,
    case_a: ComplaintCase, case_b: ComplaintCase, evidence_hash: str,
    now_dt, actor: str,
) -> bool:
    """Evidence-version-aware lifecycle for informational same-incident alerts.

    - qualifying pair, no active alert -> NEW occurrence created (links the
      assessment and the exact evidence hash that triggered it)
    - qualifying pair, active alert  -> reused; its evidence link is refreshed
      if the evidence changed while the pair still qualifies
    - non-qualifying pair, active alert -> resolved 'system (auto)' as stale;
      the alert history row is preserved
    - non-qualifying pair, no active alert -> nothing to do; condition state
      is recorded absent so a later return opens the NEXT occurrence
    Never confirms relationships, never merges cases, never erases review
    history. Returns True when a new alert occurrence was created.
    """
    logical_key = f"PSI:{key}"
    actives = db.scalars(
        select(CoordinationAlert)
        .where(
            CoordinationAlert.alert_type == AlertType.POTENTIAL_SAME_INCIDENT,
            CoordinationAlert.logical_key == logical_key,
            CoordinationAlert.status != AlertStatus.RESOLVED,
        )
        .order_by(CoordinationAlert.occurrence.desc())
    ).all()
    active = actives[0] if actives else None
    # belt-and-braces: keep at most one active informational alert per pair
    for stale in actives[1:]:
        stale.status = AlertStatus.RESOLVED
        stale.resolved_at = now_dt
        stale.resolved_by = "system (auto)"
        stale.resolution_note = "Superseded duplicate of the same informational condition."

    state = db.get(AlertConditionState, logical_key)
    if qualifies:
        if active is not None:
            # Reuse the active alert; keep the evidence link current.
            if active.assessment_id != row.id or (active.evidence_hash or "") != evidence_hash:
                active.assessment_id = row.id
                active.evidence_hash = evidence_hash
                record_audit(
                    db, actor=actor, event_type="PSI_ALERT_EVIDENCE_UPDATED",
                    entity_type="coordination_alert", entity_id=str(active.id),
                    summary="Same-incident informational alert evidence link refreshed",
                    meta={"pair_key": key, "assessment_id": row.id,
                          "evidence_hash": evidence_hash},
                )
            created = False
        else:
            all_occ = [
                a.occurrence
                for a in db.scalars(
                    select(CoordinationAlert).where(
                        CoordinationAlert.logical_key == logical_key,
                        CoordinationAlert.alert_type == AlertType.POTENTIAL_SAME_INCIDENT,
                    )
                ).all()
            ]
            occurrence = (max(all_occ) + 1) if all_occ else 1
            if state is not None and state.occurrences >= occurrence:
                occurrence = state.occurrences + 1
            db.add(
                CoordinationAlert(
                    alert_type=AlertType.POTENTIAL_SAME_INCIDENT,
                    institution_id=row.institution_id,
                    case_ids=[case_a.case_id, case_b.case_id],
                    title=f"Potential same-incident relationship suggested - {key}",
                    description=(
                        "The rule engine found supporting evidence that the two cases "
                        f"in pair {key} may concern the same incident. This is an "
                        "automated recommendation requiring human review - no records "
                        f"are merged or changed. (assessment #{row.id}, evidence "
                        f"fingerprint {evidence_hash[:12]})"
                    ),
                    dedupe_key=logical_key if occurrence == 1 else f"{logical_key}#occ{occurrence}",
                    logical_key=logical_key,
                    occurrence=occurrence,
                    assessment_id=row.id,
                    evidence_hash=evidence_hash,
                    created_at=now_dt,
                )
            )
            created = True
            record_audit(
                db, actor=actor, event_type="PSI_ALERT_CREATED",
                entity_type="relationship_assessment", entity_id=str(row.id),
                summary=f"Informational same-incident alert opened (occurrence {occurrence})",
                meta={"pair_key": key, "assessment_id": row.id,
                      "occurrence": occurrence, "evidence_hash": evidence_hash},
            )
        if state is None:
            # state row may be missing for legacy rows created before condition
            # tracking existed; reconstruct from observed history.
            hist_max = max(
                [a.occurrence for a in db.scalars(
                    select(CoordinationAlert).where(
                        CoordinationAlert.logical_key == logical_key,
                        CoordinationAlert.alert_type == AlertType.POTENTIAL_SAME_INCIDENT,
                    )
                ).all()] + [occurrence if created else 0]
            )
            db.add(
                AlertConditionState(
                    logical_key=logical_key,
                    alert_type="POTENTIAL_SAME_INCIDENT",
                    present=True,
                    occurrences=hist_max,
                    updated_at=now_dt,
                )
            )
        else:
            state.present = True
            if created:
                state.occurrences = max(state.occurrences, occurrence)
            state.updated_at = now_dt
        return created

    # not qualifying: stale alert auto-resolves; condition recorded absent
    if active is not None:
        active.status = AlertStatus.RESOLVED
        active.resolved_at = now_dt
        active.resolved_by = "system (auto)"
        active.resolution_note = (
            f"Recommendation no longer POTENTIAL_SAME_INCIDENT (now "
            f"{row.relationship_type.value}); closed automatically, history retained."
        )
        record_audit(
            db, actor=actor, event_type="PSI_ALERT_STALE_RESOLVED",
            entity_type="coordination_alert", entity_id=str(active.id),
            summary="Same-incident informational alert auto-resolved: evidence no longer qualifies",
            meta={"pair_key": key, "assessment_id": row.id,
                  "new_relationship_type": row.relationship_type.value},
        )
    if state is None:
        db.add(
            AlertConditionState(
                logical_key=logical_key,
                alert_type="POTENTIAL_SAME_INCIDENT",
                present=False,
                occurrences=0,
                updated_at=now_dt,
            )
        )
    elif state.present:
        state.present = False
        state.updated_at = now_dt
    return False


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
            # Informational same-incident alert lifecycle (runs for BOTH the
            # create and update paths, so transitions trigger it):
            # newly-qualifying pairs open an alert; evidence changes refresh
            # the link; no-longer-qualifying pairs get their stale alert
            # auto-resolved while all occurrences and history are preserved.
            qualifies = result.relationship_type == RelationshipType.POTENTIAL_SAME_INCIDENT
            if _psi_alert_lifecycle(
                db, qualifies=qualifies, key=key, row=row,
                case_a=case_a, case_b=case_b, evidence_hash=new_hash,
                now_dt=now_dt, actor=actor,
            ):
                alerts_created += 1

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
