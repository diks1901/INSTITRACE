"""Alert evaluation service.

Alert rules (all deduplicated via a stable dedupe_key - rerunning evaluation
never creates a duplicate alert for the SAME active condition instance;
human resolutions are preserved):
  * CROSS_BUREAU_COORDINATION - >=2 active cases on one institution assigned
    to different bureaus. Institution-level signal only; it does NOT assert
    the cases concern the same incident.
  * APPROACHING_DEADLINE - active case whose expected disposal date is within
    the configured warning window (prototype default: 3 days).
  * OVERDUE - active case past its expected disposal date.
  * ESCALATION_REQUIRED - active case overdue by >= configured threshold.
  * PENDING_REMINDER - active case past its next-action due date.

DISPOSED cases never generate deadline/overdue alerts.
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import now, today
from ..config import get_settings
from ..models import (
    ACTIVE_STATUSES,
    AlertStatus,
    AlertType,
    Bureau,
    ComplaintCase,
    CoordinationAlert,
    Institution,
)


def _active_cases(db: Session) -> list[ComplaintCase]:
    return list(
        db.scalars(
            select(ComplaintCase).where(ComplaintCase.status.in_(ACTIVE_STATUSES))
        )
    )


def evaluate_alerts(db: Session) -> dict:
    """Recompute all operational alerts. Idempotent per condition-instance."""
    settings = get_settings()
    created = 0
    auto_resolved = 0
    now_dt = now()
    today_d = today()

    desired_keys: set[str] = set()

    def upsert(alert_type, institution_id, case_ids, title, description, dedupe_key):
        nonlocal created
        desired_keys.add(dedupe_key)
        existing = db.scalar(
            select(CoordinationAlert).where(CoordinationAlert.dedupe_key == dedupe_key)
        )
        if existing is not None:
            return existing  # OPEN / ACKNOWLEDGED / RESOLVED rows are all preserved
        db.add(
            CoordinationAlert(
                alert_type=alert_type,
                institution_id=institution_id,
                case_ids=case_ids,
                title=title,
                description=description,
                dedupe_key=dedupe_key,
                created_at=now_dt,
            )
        )
        created += 1
        return None

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
        upsert(
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
                upsert(
                    AlertType.OVERDUE, c.institution_id, [c.case_id],
                    f"Overdue case - {c.case_id}",
                    f"Case {c.case_id} ({inst_name}) passed its expected disposal "
                    f"date {exp.isoformat()} by {overdue_days} day(s) and is still "
                    f"{c.status.value}.",
                    f"OVERDUE:{key}",
                )
                if overdue_days >= settings.escalation_overdue_days:
                    upsert(
                        AlertType.ESCALATION_REQUIRED, c.institution_id, [c.case_id],
                        f"Escalation required - {c.case_id}",
                        f"Case {c.case_id} ({inst_name}) is overdue by "
                        f"{overdue_days} day(s), at or beyond the prototype "
                        f"escalation threshold of {settings.escalation_overdue_days} days.",
                        f"ESCALATION:{key}",
                    )
            elif timedelta(0) <= (exp - today_d) <= warn:
                upsert(
                    AlertType.APPROACHING_DEADLINE, c.institution_id, [c.case_id],
                    f"Deadline approaching - {c.case_id}",
                    f"Case {c.case_id} ({inst_name}) is expected to be disposed by "
                    f"{exp.isoformat()} - within the prototype warning window of "
                    f"{settings.deadline_warning_days} day(s). "
                    "This threshold is a demo configuration, not an official AICTE SLA.",
                    f"APPROACHING:{key}",
                )
        if c.next_action_due_date is not None and c.next_action_due_date < today_d:
            upsert(
                AlertType.PENDING_REMINDER, c.institution_id, [c.case_id],
                f"Pending reminder - {c.case_id}",
                f"Case {c.case_id} ({inst_name}) had a next action "
                f"({c.next_action or 'unspecified'}) due on "
                f"{c.next_action_due_date.isoformat()} which is past.",
                f"REMINDER:{c.case_id}:{c.next_action_due_date.isoformat()}",
            )

    # ---------------- auto-resolve stale operational alerts -------------
    # Open/acknowledged alerts whose condition instance no longer holds are
    # closed by the system so the board reflects reality. Human-resolved
    # alerts are never reopened or duplicated (dedupe key already covered).
    operational = (
        AlertType.CROSS_BUREAU_COORDINATION,
        AlertType.OVERDUE,
        AlertType.ESCALATION_REQUIRED,
        AlertType.APPROACHING_DEADLINE,
        AlertType.PENDING_REMINDER,
    )
    for alert in db.scalars(select(CoordinationAlert)):
        if alert.alert_type in operational and alert.status != AlertStatus.RESOLVED:
            if alert.dedupe_key not in desired_keys:
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
