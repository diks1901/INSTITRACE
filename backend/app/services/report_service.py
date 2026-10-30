"""Report computations and CSV export.

CSV safeguards: fields beginning with =, +, - or @ are prefixed with a single
quote to block spreadsheet formula injection; the standard library csv writer
handles quoting/escaping. Each export carries metadata (report, generated-at,
applied filters) as `#`-prefixed header rows.
"""
import csv
import io
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..clock import now, today
from ..models import (
    ACTIVE_STATUSES,
    Bureau,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
    Institution,
    RelationshipAssessment,
)

AGE_BUCKETS = [(0, 30), (31, 60), (61, 90), (91, 180), (181, None)]


def _age_days(case, ref=None) -> int:
    end = ref or (case.actual_disposal_date if case.status == CaseStatus.DISPOSED else None) or today()
    return (end - case.receipt_date).days


def report_institutions(db: Session, region: str | None = None, state: str | None = None) -> dict:
    stmt = select(Institution).options(selectinload(Institution.cases))
    if region:
        stmt = stmt.where(Institution.region == region)
    if state:
        stmt = stmt.where(Institution.state == state)
    rows = []
    for inst in db.scalars(stmt.order_by(Institution.name)):
        cases = inst.cases
        active = [c for c in cases if c.status in ACTIVE_STATUSES]
        disposed = [c for c in cases if c.status == CaseStatus.DISPOSED]
        overdue = [
            c for c in active
            if c.expected_disposal_date and c.expected_disposal_date < today()
        ]
        rows.append({
            "permanent_id": inst.permanent_id,
            "institution": inst.name,
            "region": inst.region,
            "state": inst.state,
            "total_cases": len(cases),
            "active_cases": len(active),
            "disposed_cases": len(disposed),
            "overdue_active_cases": len(overdue),
        })
    return {
        "title": "Institution-wise case report",
        "definition": "One row per institution. Active = status in PENDING/UNDER_PROCESS/"
        "ESCALATED/TRANSFERRED. Overdue = active and expected disposal date before today.",
        "columns": ["permanent_id", "institution", "region", "state", "total_cases",
                    "active_cases", "disposed_cases", "overdue_active_cases"],
        "rows": rows,
    }


def report_bureaus(db: Session) -> dict:
    rows = []
    for bureau in db.scalars(
        select(Bureau).options(selectinload(Bureau.cases)).order_by(Bureau.code)
    ):
        cases = bureau.cases
        total = len(cases)
        disposed = [c for c in cases if c.status == CaseStatus.DISPOSED]
        active = [c for c in cases if c.status in ACTIVE_STATUSES]
        overdue = [c for c in active if c.expected_disposal_date and c.expected_disposal_date < today()]
        avg_days = (
            round(sum(_age_days(c) for c in disposed) / len(disposed), 1) if disposed else None
        )
        rows.append({
            "bureau_code": bureau.code,
            "bureau_name": bureau.name,
            "total_cases": total,
            "active_cases": len(active),
            "disposed_cases": len(disposed),
            "disposal_rate_pct": round(100 * len(disposed) / total, 1) if total else None,
            "avg_days_to_dispose": avg_days,
            "overdue_active_cases": len(overdue),
        })
    return {
        "title": "Bureau-wise workload report",
        "definition": "Disposal rate = DISPOSED / total cases handled by the bureau (current "
        "assignment). Avg days to dispose = mean(actual_disposal_date - receipt_date) over "
        "disposed cases. Workload reflects current bureau assignment (post-transfer).",
        "columns": ["bureau_code", "bureau_name", "total_cases", "active_cases",
                    "disposed_cases", "disposal_rate_pct", "avg_days_to_dispose",
                    "overdue_active_cases"],
        "rows": rows,
    }


def report_regions(db: Session) -> dict:
    per_region: dict[str, dict] = {}
    for inst in db.scalars(select(Institution).options(selectinload(Institution.cases))):
        bucket = per_region.setdefault(inst.region, {
            "region": inst.region, "institutions": 0, "total_cases": 0,
            "active_cases": 0, "disposed_cases": 0, "overdue_active_cases": 0,
        })
        bucket["institutions"] += 1
        for c in inst.cases:
            bucket["total_cases"] += 1
            if c.status in ACTIVE_STATUSES:
                bucket["active_cases"] += 1
                if c.expected_disposal_date and c.expected_disposal_date < today():
                    bucket["overdue_active_cases"] += 1
            if c.status == CaseStatus.DISPOSED:
                bucket["disposed_cases"] += 1
    return {
        "title": "Region-wise case report",
        "definition": "Cases attributed to the institution's region. Active/overdue as per "
        "the institution report definitions.",
        "columns": ["region", "institutions", "total_cases", "active_cases",
                    "disposed_cases", "overdue_active_cases"],
        "rows": [per_region[k] for k in sorted(per_region)],
    }


def report_statuses(db: Session) -> dict:
    rows = []
    counts = dict(
        db.execute(select(ComplaintCase.status, func.count()).group_by(ComplaintCase.status)).all()
    )
    for status in CaseStatus:
        cases = list(db.scalars(select(ComplaintCase).where(ComplaintCase.status == status)))
        avg_age = round(sum(_age_days(c) for c in cases) / len(cases), 1) if cases else None
        rows.append({
            "status": status.value,
            "case_count": counts.get(status, 0),
            "avg_age_days": avg_age,
        })
    return {
        "title": "Status-wise distribution report",
        "definition": "Case counts by current status. Avg age = today - receipt_date for "
        "active/transferred cases; actual_disposal_date - receipt_date for DISPOSED cases.",
        "columns": ["status", "case_count", "avg_age_days"],
        "rows": rows,
    }


def report_ageing(db: Session) -> dict:
    active = list(db.scalars(select(ComplaintCase).where(ComplaintCase.status.in_(ACTIVE_STATUSES))))
    buckets: list[dict] = []
    for lo, hi in AGE_BUCKETS:
        label = f"{lo}-{hi}" if hi else f"{lo}+"
        members = [
            c for c in active
            if lo <= _age_days(c) and (hi is None or _age_days(c) <= hi)
        ]
        buckets.append({
            "age_bucket_days": label,
            "case_count": len(members),
            "case_ids": ",".join(sorted(c.case_id for c in members)),
        })
    return {
        "title": "Pending-case ageing report",
        "definition": "Age of currently ACTIVE cases = today - receipt_date, grouped in "
        "30/60/90/180-day buckets. Disposed cases are excluded by design.",
        "columns": ["age_bucket_days", "case_count", "case_ids"],
        "rows": buckets,
    }


def report_disposal(db: Session) -> dict:
    total = db.scalar(select(func.count(ComplaintCase.id))) or 0
    disposed = list(db.scalars(select(ComplaintCase).where(ComplaintCase.status == CaseStatus.DISPOSED)))
    avg_days = round(sum(_age_days(c) for c in disposed) / len(disposed), 1) if disposed else None
    monthly: dict[str, dict] = {}
    for c in disposed:
        key = f"{c.actual_disposal_date.year:04d}-{c.actual_disposal_date.month:02d}"
        monthly.setdefault(key, {"month": key, "disposals": 0})["disposals"] += 1
    return {
        "title": "Disposal rate report",
        "definition": "Disposal rate = DISPOSED cases / total registered cases. Avg days to "
        "dispose = mean(actual_disposal_date - receipt_date). No operational savings are "
        "claimed by this prototype.",
        "columns": ["metric", "value"],
        "rows": [
            {"metric": "total_cases", "value": total},
            {"metric": "disposed_cases", "value": len(disposed)},
            {"metric": "disposal_rate_pct",
             "value": round(100 * len(disposed) / total, 1) if total else None},
            {"metric": "avg_days_to_dispose", "value": avg_days},
        ] + [{"metric": f"disposals_in_{m['month']}", "value": m["disposals"]}
             for m in sorted(monthly.values(), key=lambda r: r["month"])],
        "columns_detail": ["month", "disposals"],
    }


def report_overlaps(db: Session) -> dict:
    alert_rows = db.execute(
        select(CoordinationAlert.alert_type, CoordinationAlert.status, func.count())
        .group_by(CoordinationAlert.alert_type, CoordinationAlert.status)
    ).all()
    assess_rows = db.execute(
        select(RelationshipAssessment.relationship_type, RelationshipAssessment.status, func.count())
        .group_by(RelationshipAssessment.relationship_type, RelationshipAssessment.status)
    ).all()
    rows = [
        {"dimension": "alert", "category": a.value, "state": s.value, "count": n}
        for a, s, n in alert_rows
    ] + [
        {"dimension": "assessment", "category": t.value, "state": s.value, "count": n}
        for t, s, n in assess_rows
    ]
    rows.sort(key=lambda r: (r["dimension"], r["category"], r["state"]))
    return {
        "title": "Cross-bureau overlap / coordination report",
        "definition": "Counts of coordination alerts and relationship assessments by kind and "
        "state. Cross-bureau alerts and same-incident assessments are tracked separately by "
        "design: one signals shared-institution workload, the other a reviewed incident "
        "relationship recommendation.",
        "columns": ["dimension", "category", "state", "count"],
        "rows": rows,
    }


REPORTS = {
    "institutions": report_institutions,
    "bureaus": report_bureaus,
    "regions": report_regions,
    "statuses": report_statuses,
    "ageing": report_ageing,
    "disposal": report_disposal,
    "overlaps": report_overlaps,
}


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text  # spreadsheet formula-injection guard
    return text


def build_csv(title: str, columns: list[str], rows: list[dict], filters: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([f"# INSTITRACE report: {title}"])
    writer.writerow([f"# Generated at (UTC): {now().isoformat()}"])
    applied = {k: v for k, v in filters.items() if v not in (None, "")}
    writer.writerow([f"# Applied filters: {applied if applied else 'none'}"])
    writer.writerow(["# Synthetic demo data - not real AICTE records"])
    writer.writerow([])
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_safe(row.get(col)) for col in columns])
    return buf.getvalue()
