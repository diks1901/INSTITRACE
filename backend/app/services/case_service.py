"""Case workflow service. Every consequential mutation:
  * validates on the server (status transitions, references, dates),
  * runs inside a single transaction,
  * appends a CaseAction (business history) and an AuditEvent (system audit).
"""
from ..clock import now
from ..models import (
    ACTIVE_STATUSES,
    CaseAction,
    CaseStatus,
    ComplaintCase,
    Institution,
    TransferRecord,
    VALID_TRANSITIONS,
    Bureau,
)
from ..schemas import CaseCreate, CaseUpdate
from .audit import record_audit
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session


class WorkflowError(HTTPException):
    pass


def _get_case_or_404(db: Session, pk: int) -> ComplaintCase:
    case = db.get(ComplaintCase, pk)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def _snapshot(case: ComplaintCase) -> dict:
    return {
        "case_id": case.case_id,
        "status": case.status.value,
        "bureau_id": case.bureau_id,
        "officer_name": case.officer_name,
        "next_action": case.next_action,
        "expected_disposal_date": (
            case.expected_disposal_date.isoformat() if case.expected_disposal_date else None
        ),
    }


def _append_action(
    db, case: ComplaintCase, *, action_type: str, summary: str, actor: str,
    from_status: str | None = None, to_status: str | None = None,
) -> None:
    db.add(
        CaseAction(
            case_id=case.id,
            action_type=action_type,
            summary=summary,
            actor=actor,
            from_status=from_status,
            to_status=to_status,
            acted_at=now(),
        )
    )
    case.last_action_summary = summary
    case.last_action_at = now()
    case.updated_at = now()


def create_case(db: Session, payload: CaseCreate, actor: str) -> ComplaintCase:
    if db.scalar(select(ComplaintCase).where(ComplaintCase.case_id == payload.case_id)):
        raise HTTPException(status_code=409, detail=f"Case ID {payload.case_id} already exists")
    if db.get(Institution, payload.institution_id) is None:
        raise HTTPException(status_code=422, detail="institution_id does not reference an existing institution")
    if db.get(Bureau, payload.bureau_id) is None:
        raise HTTPException(status_code=422, detail="bureau_id does not reference an existing bureau")
    case = ComplaintCase(**payload.model_dump(), status=CaseStatus.PENDING)
    db.add(case)
    db.flush()
    _append_action(
        db, case,
        action_type="CREATED",
        summary=f"Case {case.case_id} registered and marked PENDING.",
        actor=actor,
        from_status=None,
        to_status=CaseStatus.PENDING.value,
    )
    record_audit(
        db, actor=actor, event_type="CASE_CREATED", entity_type="case",
        entity_id=case.case_id, summary=f"Case {case.case_id} created",
        after=_snapshot(case),
    )
    db.commit()
    db.refresh(case)
    return case


def update_case(db: Session, pk: int, payload: CaseUpdate, actor: str) -> ComplaintCase:
    case = _get_case_or_404(db, pk)
    before = _snapshot(case)
    data = payload.model_dump(exclude_unset=True)
    if "institution_id" in data and db.get(Institution, data["institution_id"]) is None:
        raise HTTPException(status_code=422, detail="institution_id does not reference an existing institution")
    if data.get("expected_disposal_date") and data["expected_disposal_date"] < case.receipt_date:
        raise HTTPException(status_code=422, detail="expected_disposal_date cannot be before receipt_date")
    changed_fields = sorted(data.keys())
    for field, value in data.items():
        setattr(case, field, value)
    case.updated_at = now()
    record_audit(
        db, actor=actor, event_type="CASE_UPDATED", entity_type="case",
        entity_id=case.case_id, summary=f"Case {case.case_id} updated fields: {changed_fields}",
        before=before, after=_snapshot(case), meta={"fields": changed_fields},
    )
    db.commit()
    db.refresh(case)
    return case


def change_status(
    db: Session, pk: int, *, to_status: CaseStatus, summary: str,
    rationale: str | None, actor: str, actual_disposal_date=None,
) -> ComplaintCase:
    case = _get_case_or_404(db, pk)
    if to_status == case.status:
        raise WorkflowError(status_code=422, detail=f"Case is already {to_status.value}")
    if to_status not in VALID_TRANSITIONS[case.status]:
        raise WorkflowError(
            status_code=422,
            detail=f"Invalid status transition {case.status.value} -> {to_status.value}. "
            f"Allowed: {sorted(s.value for s in VALID_TRANSITIONS[case.status]) or 'none (terminal)'}",
        )
    before = _snapshot(case)
    from_status = case.status
    case.status = to_status
    if to_status == CaseStatus.DISPOSED:
        case.actual_disposal_date = actual_disposal_date or now().date()
    elif case.actual_disposal_date is not None:
        case.actual_disposal_date = None
    _append_action(
        db, case, action_type="STATUS_CHANGE", summary=summary, actor=actor,
        from_status=from_status.value, to_status=to_status.value,
    )
    record_audit(
        db, actor=actor, event_type="CASE_STATUS_CHANGED", entity_type="case",
        entity_id=case.case_id, summary=f"{from_status.value} -> {to_status.value}: {summary}",
        rationale=rationale, before=before, after=_snapshot(case),
    )
    db.commit()
    db.refresh(case)
    return case


def change_assignment(db: Session, pk: int, *, officer_name: str, summary: str, actor: str) -> ComplaintCase:
    case = _get_case_or_404(db, pk)
    before = _snapshot(case)
    old = case.officer_name
    case.officer_name = officer_name
    case.updated_at = now()
    _append_action(
        db, case, action_type="ASSIGNMENT_CHANGE",
        summary=f"{summary} (officer: {old} -> {officer_name})", actor=actor,
    )
    record_audit(
        db, actor=actor, event_type="CASE_ASSIGNMENT_CHANGED", entity_type="case",
        entity_id=case.case_id, summary=f"Officer changed from {old} to {officer_name}",
        before=before, after=_snapshot(case),
    )
    db.commit()
    db.refresh(case)
    return case


def transfer_case(db: Session, pk: int, *, to_bureau_id: int, to_officer_name: str,
                  reason: str, actor: str) -> ComplaintCase:
    """Transfer preserves full history, never disposes the case."""
    case = _get_case_or_404(db, pk)
    to_bureau = db.get(Bureau, to_bureau_id)
    if to_bureau is None:
        raise WorkflowError(status_code=422, detail="to_bureau_id does not reference an existing bureau")
    if to_bureau.id == case.bureau_id:
        raise WorkflowError(status_code=422, detail="Case is already assigned to that bureau")
    if case.status == CaseStatus.DISPOSED:
        raise WorkflowError(status_code=422, detail="A DISPOSED case cannot be transferred")

    before = _snapshot(case)
    from_bureau_id = case.bureau_id
    from_officer = case.officer_name
    from_status = case.status

    db.add(
        TransferRecord(
            case_id=case.id, from_bureau_id=from_bureau_id, to_bureau_id=to_bureau.id,
            from_officer=from_officer, to_officer=to_officer_name, reason=reason,
            actor=actor, transferred_at=now(),
        )
    )
    case.bureau_id = to_bureau.id
    case.officer_name = to_officer_name
    case.status = CaseStatus.TRANSFERRED  # still active; receiving bureau re-accepts
    _append_action(
        db, case, action_type="TRANSFER",
        summary=f"Transferred to {to_bureau.name} ({reason})", actor=actor,
        from_status=from_status.value, to_status=CaseStatus.TRANSFERRED.value,
    )
    record_audit(
        db, actor=actor, event_type="CASE_TRANSFERRED", entity_type="case",
        entity_id=case.case_id,
        summary=f"Transferred from bureau {from_bureau_id} to {to_bureau.id}: {reason}",
        rationale=reason, before=before, after=_snapshot(case),
    )
    db.commit()
    db.refresh(case)
    return case


def escalate_case(db: Session, pk: int, *, reason: str, actor: str) -> ComplaintCase:
    case = _get_case_or_404(db, pk)
    return change_status(
        db, pk, to_status=CaseStatus.ESCALATED,
        summary=f"Escalated: {reason}", rationale=reason, actor=actor,
    )


def add_action(db: Session, pk: int, *, summary: str, action_type: str, actor: str) -> ComplaintCase:
    case = _get_case_or_404(db, pk)
    _append_action(db, case, action_type=action_type, summary=summary, actor=actor)
    record_audit(
        db, actor=actor, event_type="CASE_ACTION_ADDED", entity_type="case",
        entity_id=case.case_id, summary=summary,
        before=None, after=_snapshot(case),
    )
    db.commit()
    db.refresh(case)
    return case


def update_next_action(db: Session, pk: int, *, next_action: str,
                       next_action_due_date, expected_disposal_date, actor: str) -> ComplaintCase:
    case = _get_case_or_404(db, pk)
    if expected_disposal_date and expected_disposal_date < case.receipt_date:
        raise HTTPException(status_code=422, detail="expected_disposal_date cannot be before receipt_date")
    before = _snapshot(case)
    case.next_action = next_action
    if next_action_due_date is not None:
        case.next_action_due_date = next_action_due_date
    if expected_disposal_date is not None:
        case.expected_disposal_date = expected_disposal_date
    case.updated_at = now()
    _append_action(
        db, case, action_type="NEXT_ACTION_SET",
        summary=f"Next action: {next_action}", actor=actor,
    )
    record_audit(
        db, actor=actor, event_type="CASE_NEXT_ACTION_UPDATED", entity_type="case",
        entity_id=case.case_id, summary=f"Next action set: {next_action}",
        before=before, after=_snapshot(case),
    )
    db.commit()
    db.refresh(case)
    return case


def is_active(case: ComplaintCase) -> bool:
    return case.status in ACTIVE_STATUSES
