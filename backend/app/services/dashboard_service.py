"""Dashboard metrics. Every figure is computed from the live database and has
a documented definition (returned alongside the values).

Definitions
  total_cases              : all complaint cases in the registry.
  pending / under_process /
  disposed / transferred /
  escalated                : cases whose current status equals the value.
  overdue_active           : cases in an ACTIVE status (PENDING,
                             UNDER_PROCESS, ESCALATED, TRANSFERRED) whose
                             expected disposal date is before today.
  approaching_deadline     : ACTIVE cases with expected disposal date within
                             [today, today + deadline_warning_days].
  open_coordination_alerts : CROSS_BUREAU_COORDINATION alerts not RESOLVED
                             (OPEN or ACKNOWLEDGED).
  pending_incident_reviews : relationship assessments of type
                             POTENTIAL_SAME_INCIDENT or PROCEDURAL_LINK with
                             status PENDING_REVIEW.
"""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..clock import today
from ..config import get_settings
from ..models import (
    ACTIVE_STATUSES,
    AlertStatus,
    AlertType,
    AssessmentStatus,
    Bureau,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
    RelationshipAssessment,
    RelationshipType,
)


def summary(db: Session) -> dict:
    status_counts = dict(
        db.execute(
            select(ComplaintCase.status, func.count()).group_by(ComplaintCase.status)
        ).all()
    )
    get = lambda s: status_counts.get(s, 0)  # noqa: E731
    today_d = today()
    setts = get_settings()

    overdue_active = db.scalar(
        select(func.count(ComplaintCase.id)).where(
            ComplaintCase.status.in_(ACTIVE_STATUSES),
            ComplaintCase.expected_disposal_date.is_not(None),
            ComplaintCase.expected_disposal_date < today_d,
        )
    )
    approaching = db.scalar(
        select(func.count(ComplaintCase.id)).where(
            ComplaintCase.status.in_(ACTIVE_STATUSES),
            ComplaintCase.expected_disposal_date.is_not(None),
            ComplaintCase.expected_disposal_date >= today_d,
            ComplaintCase.expected_disposal_date <= today_d + timedelta(days=setts.deadline_warning_days),
        )
    )
    open_coord = db.scalar(
        select(func.count(CoordinationAlert.id)).where(
            CoordinationAlert.alert_type == AlertType.CROSS_BUREAU_COORDINATION,
            CoordinationAlert.status != AlertStatus.RESOLVED,
        )
    )
    pending_reviews = db.scalar(
        select(func.count(RelationshipAssessment.id)).where(
            RelationshipAssessment.status == AssessmentStatus.PENDING_REVIEW,
            RelationshipAssessment.relationship_type.in_(
                [RelationshipType.POTENTIAL_SAME_INCIDENT, RelationshipType.PROCEDURAL_LINK]
            ),
        )
    )
    total = sum(status_counts.values())
    return {
        "total_cases": total,
        "pending": get(CaseStatus.PENDING),
        "under_process": get(CaseStatus.UNDER_PROCESS),
        "disposed": get(CaseStatus.DISPOSED),
        "transferred": get(CaseStatus.TRANSFERRED),
        "escalated": get(CaseStatus.ESCALATED),
        "overdue_active": overdue_active or 0,
        "approaching_deadline": approaching or 0,
        "open_coordination_alerts": open_coord or 0,
        "pending_incident_reviews": pending_reviews or 0,
        "deadline_warning_days": setts.deadline_warning_days,
        "definitions": {
            "overdue_active": "Active-status cases whose expected disposal date is before today.",
            "approaching_deadline": f"Active cases with expected disposal within {setts.deadline_warning_days} days (prototype threshold).",
            "open_coordination_alerts": "Cross-bureau coordination alerts that are not RESOLVED.",
            "pending_incident_reviews": "Same-incident/procedural-link assessments awaiting human review.",
        },
    }


def bureau_workload(db: Session) -> list[dict]:
    rows = db.execute(
        select(
            Bureau.id, Bureau.code, Bureau.name,
            func.count(ComplaintCase.id).label("total"),
            func.count(ComplaintCase.id).filter(
                ComplaintCase.status.in_(ACTIVE_STATUSES)
            ).label("active"),
        )
        .select_from(Bureau)
        .outerjoin(ComplaintCase, ComplaintCase.bureau_id == Bureau.id)
        .group_by(Bureau.id, Bureau.code, Bureau.name)
        .order_by(Bureau.code)
    ).all()
    return [
        {
            "bureau_id": r.id, "code": r.code, "name": r.name,
            "total_cases": int(r.total or 0), "active_cases": int(r.active or 0),
        }
        for r in rows
    ]


def trends(db: Session, months: int = 12) -> dict:
    """Monthly receipts and disposals for the last `months` calendar months.
    Portable approach: aggregate by Python month buckets over indexed dates."""
    today_d = today()
    first = today_d.replace(day=1)
    buckets: list[str] = []
    y, m = first.year, first.month
    for _ in range(months):
        buckets = [f"{y:04d}-{m:02d}"] + buckets
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    cutoff = date_from_bucket(buckets[0])

    receipts = db.scalars(
        select(ComplaintCase.receipt_date).where(ComplaintCase.receipt_date >= cutoff)
    ).all()
    disposals = db.scalars(
        select(ComplaintCase.actual_disposal_date).where(
            ComplaintCase.actual_disposal_date.is_not(None),
            ComplaintCase.actual_disposal_date >= cutoff,
        )
    ).all()

    data = {b: {"month": b, "receipts": 0, "disposals": 0} for b in buckets}
    for d in receipts:
        key = f"{d.year:04d}-{d.month:02d}"
        if key in data:
            data[key]["receipts"] += 1
    for d in disposals:
        key = f"{d.year:04d}-{d.month:02d}"
        if key in data:
            data[key]["disposals"] += 1
    return {"monthly": list(data.values())}


def date_from_bucket(bucket: str):
    from datetime import date

    y, m = (int(p) for p in bucket.split("-"))
    return date(y, m, 1)
