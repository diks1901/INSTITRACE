"""Health and metadata endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import AlertStatus, AlertType, AssessmentStatus, CaseStatus, Institution, Priority, RelationshipType

router = APIRouter(tags=["meta"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(func.count(Institution.id)))
    return {"status": "ok", "database": "reachable"}


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    s = get_settings()
    from ..models import Bureau

    bureaus = db.scalars(select(Bureau).where(Bureau.active.is_(True)).order_by(Bureau.code)).all()
    return {
        "app": "INSTITRACE",
        "app_version": s.app_version,
        "rule_engine_version": s.rule_engine_version,
        "database_mode": "sqlite" if s.is_sqlite else "postgresql",
        "deadline_warning_days": s.deadline_warning_days,
        "escalation_overdue_days": s.escalation_overdue_days,
        "statuses": [st.value for st in CaseStatus],
        "alert_types": [a.value for a in AlertType],
        "alert_statuses": [a.value for a in AlertStatus],
        "assessment_statuses": [a.value for a in AssessmentStatus],
        "relationship_types": [r.value for r in RelationshipType],
        "priorities": [p.value for p in Priority],
        "bureaus": [{"id": b.id, "code": b.code, "name": b.name} for b in bureaus],
        "demo_data_notice": "All institutions, cases and users are synthetic demo data. "
        "Deadline thresholds are prototype defaults, not official AICTE SLAs.",
    }
