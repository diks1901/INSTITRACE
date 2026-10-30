"""Alert evaluation service with an occurrence-based lifecycle.

Every alert is one OCCURRENCE of a recurring CONDITION. The condition is
identified by a stable `logical_key`; occurrences are numbered per key.

Lifecycle contract (FIX 1):
  * Condition present, an active (OPEN/ACKNOWLEDGED) alert already exists for
    the logical key  -> reuse it. Recomputation NEVER duplicates active alerts.
  * Condition present, no active alert, and the condition was ABSENT at the
    last evaluation (or was never seen) -> create occurrence N+1 as a NEW
    alert. A previously resolved condition can therefore recur and surface
    again, while the resolved rows remain intact as history.
  * Condition present, no active alert, condition was PRESENT at last
    evaluation -> a human resolved the current occurrence while the condition
    persisted; the resolution stands and recomputation does not respawn it.
  * Condition absent, active alert exists -> the system RESOLVES that alert
    (resolved_by="system (auto)") with an explanation. History is preserved.

Operational alert kinds managed here (POTENTIAL_SAME_INCIDENT informational
alerts are managed by the matching service and are not part of this loop):
  * CROSS_BUREAU_COORDINATION - >=2 active cases on one institution assigned
    to different bureaus. Institution-level signal only; it does NOT assert
    the cases concern the same incident.
  * APPROACHING_DEADLINE - active case whose expected disposal date is within
    the configured warning window (prototype default: 3 days).
  * OVERDUE - active case past its expected disposal date.
  * ESCALATION_REQUIRED - active case overdue by >= configured threshold.
  * PENDING_REMINDER - active case past its next-action due date.

DISPOSED cases never generate deadline/overdue alerts. All writes happen in
one transaction (the caller's session commits atomically).
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import now, today
from ..config import get_settings
from ..models import (
    ACTIVE_STATUSES,
    AlertConditionState,
    AlertStatus,
    AlertType,
    Bureau,
    ComplaintCase,
    CoordinationAlert,
    Institution,
)

OPERATIONAL_TYPES = {
    AlertType.CROSS_BUREAU_COORDINATION,
    AlertType.OVERDUE,
    AlertType.ESCALATION_REQUIRED,
    AlertType.APPROACHING_DEADLINE,
    AlertType.PENDING_REMINDER,
}


def _active_cases(db: Session) -> list[ComplaintCase]:
    return list(
        db.scalars(
            select(ComplaintCase).where(ComplaintCase.status.in_(ACTIVE_STATUSES))
        )
    )


def evaluate_alerts(db: Session) -> dict:
    """Recompute all operational alerts. Idempotent per active occurrence;
    recurrence-safe via occurrences; resolution history is preserved."""
    settings = get_settings()
    created = 0
    auto_resolved = 0
    now_dt = now()
    today_d = today()

    # logical_key -> (alert_type, institution_id, case_ids, title, description)
    desired: dict[str, tuple] = {}

    def track(alert_type, institution_id, case_ids, title, description, logical_key):
        desired.setdefault(
            logical_key, (alert_type, institution_id, case_ids, title, description)
        )

    cases = _active_cases(db)
    inst_map = {i.id: i for i in db.scalars(select(Institution))}
    bureau_map = {b.id: b for b in db.scalars(select(Bureau))}

    # ---------------- cross-bureau coordination -------------------------
    by_institution: dict[int, list[ComplaintCase]] = {}
    for c in cases:
        by_institution.setdefault(c.institution_id, []).append(c)
    for inst_id, inst_cases in sorted(by_institution.items()):
        bureaus = {c.bureau_id for c in inst_cases}
        if len(bureaus) < 2:
            continue
        inst = inst_map[inst_id]
        case_uids = sorted(c.case_id for c in inst_cases)
        bureau_codes = sorted(bureau_map[bi].code for bi in bureaus)
        key = f"XBUREAU:{inst_id}:{','.join(case_uids)}"
        track(
            AlertType.CROSS_BUREAU_COORDINATION,
            inst_id,
            case_uids,
            f"Potential Cross-Bureau Coordination Required - {inst.name}",
            "Active complaint cases associated with the same institution are "
            f"being handled by multiple Bureaus/Cells: {', '.join(bureau_codes)}. "
            f"Cases: {', '.join(case_uids)}. This alert does NOT assert the cases "
            "are duplicates or concern the same incident; it signals that "
            "coordination may be required.",
            key,
        )

    # ---------------- deadline / reminder alerts ------------------------
    warn = timedelta(days=settings.deadline_warning_days)
    for c in cases:
        inst = inst_map.get(c.institution_id)
        inst_name = inst.name if inst else str(c.institution_id)
        if c.expected_disposal_date is not None:
            exp = c.expected_disposal_date
            key = f"{c.case_id}:{exp.isoformat()}"
            overdue_days = (today_d - exp).days
            if overdue_days > 0:  # active + past expected disposal => OVERDUE
                track(
                    AlertType.OVERDUE, c.institution_id, [c.case_id],
                    f"Overdue case - {c.case_id}",
                    f"Case {c.case_id} ({inst_name}) passed its expected disposal "
                    f"date {exp.isoformat()} by {overdue_days} day(s) and is still "
                    f"{c.status.value}.",
                    f"OVERDUE:{key}",
                )
                if overdue_days >= settings.escalation_overdue_days:
                    track(
                        AlertType.ESCALATION_REQUIRED, c.institution_id, [c.case_id],
                        f"Escalation required - {c.case_id}",
                        f"Case {c.case_id} ({inst_name}) is overdue by "
                        f"{overdue_days} day(s), at or beyond the prototype "
                        f"escalation threshold of {settings.escalation_overdue_days} days.",
                        f"ESCALATION:{key}",
                    )
            elif timedelta(0) <= (exp - today_d) <= warn:
                track(
                    AlertType.APPROACHING_DEADLINE, c.institution_id, [c.case_id],
                    f"Deadline approaching - {c.case_id}",
                    f"Case {c.case_id} ({inst_name}) is expected to be disposed by "
                    f"{exp.isoformat()} - within the prototype warning window of "
                    f"{settings.deadline_warning_days} day(s). "
                    "This threshold is a demo configuration, not an official AICTE SLA.",
                    f"APPROACHING:{key}",
                )
        if c.next_action_due_date is not None and c.next_action_due_date < today_d:
            track(
                AlertType.PENDING_REMINDER, c.institution_id, [c.case_id],
                f"Pending reminder - {c.case_id}",
                f"Case {c.case_id} ({inst_name}) had a next action "
                f"({c.next_action or 'unspecified'}) due on "
                f"{c.next_action_due_date.isoformat()} which is past.",
                f"REMINDER:{c.case_id}:{c.next_action_due_date.isoformat()}",
            )

    # ---------------- lifecycle resolution ------------------------------
    states = {s.logical_key: s for s in db.scalars(select(AlertConditionState))}
    active_alerts: dict[str, CoordinationAlert] = {}
    for a in db.scalars(
        select(CoordinationAlert).where(
            CoordinationAlert.status != AlertStatus.RESOLVED,
            CoordinationAlert.alert_type.in_(OPERATIONAL_TYPES),
        )
    ):
        active_alerts.setdefault(a.logical_key, a)

    # Present conditions: reuse active occurrence, or open a new one only if
    # the condition had gone absent since the last evaluation.
    for key, (alert_type, institution_id, case_ids, title, description) in sorted(desired.items()):
        state = states.get(key)
        was_present = state.present if state else False
        if key in active_alerts:
            # active occurrence already open - never duplicate it
            pass
        elif state is None or not was_present:
            occurrence = (state.occurrences + 1) if state else 1
            db.add(
                CoordinationAlert(
                    alert_type=alert_type,
                    institution_id=institution_id,
                    case_ids=case_ids,
                    title=title,
                    description=description,
                    logical_key=key,
                    occurrence=occurrence,
                    # dedupe_key keeps its historical meaning: occurrence 1 is
                    # the bare logical key (legacy-compatible); later
                    # occurrences get an #occN suffix.
                    dedupe_key=key if occurrence == 1 else f"{key}#occ{occurrence}",
                    created_at=now_dt,
                )
            )
            created += 1
            if state is not None:
                state.occurrences = occurrence
        # else: human-resolved while the condition persisted -> stands.
        if state is None:
            db.add(
                AlertConditionState(
                    logical_key=key,
                    alert_type=alert_type.value,
                    present=True,
                    occurrences=1,
                    updated_at=now_dt,
                )
            )
        else:
            state.present = True
            state.updated_at = now_dt

    # Absent conditions: mark state and auto-resolve any still-active rows.
    for key, state in states.items():
        if key not in desired and state.present:
            state.present = False
            state.updated_at = now_dt
    for key, alert in active_alerts.items():
        if key not in desired and alert.status != AlertStatus.RESOLVED:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_by = "system (auto)"
            alert.resolved_at = now_dt
            alert.resolution_note = (
                "Condition no longer holds at latest alert evaluation "
                "(case disposed, transferred out, or deadline changed)."
            )
            auto_resolved += 1

    db.commit()
    return {"alerts_created": created, "alerts_auto_resolved": auto_resolved}


def list_alerts(db: Session, *, alert_type=None, status=None, institution_id=None,
                page: int = 1, page_size: int = 25):
    stmt = select(CoordinationAlert).order_by(CoordinationAlert.created_at.desc())
    if alert_type is not None:
        stmt = stmt.where(CoordinationAlert.alert_type == alert_type)
    if status is not None:
        stmt = stmt.where(CoordinationAlert.status == status)
    if institution_id is not None:
        stmt = stmt.where(CoordinationAlert.institution_id == institution_id)
    # database-side count (do not load the full table to measure it)
    from sqlalchemy import func

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return items, total
