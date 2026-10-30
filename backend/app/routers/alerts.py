"""Coordination & operational alert endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AlertStatus, AlertType, CoordinationAlert, DemoUser
from ..schemas import AcknowledgeRequest, AlertOut, Page, ResolveRequest
from ..security import require_roles
from ..services import alert_service
from ..services.audit import record_audit
from ..clock import now

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=Page[AlertOut])
def list_alerts(
    alert_type: AlertType | None = None,
    status: AlertStatus | None = None,
    institution_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: DemoUser = Depends(require_roles()),
):
    items, total = alert_service.list_alerts(
        db, alert_type=alert_type, status=status, institution_id=institution_id,
        page=page, page_size=page_size,
    )
    return Page(items=[AlertOut.model_validate(a) for a in items],
                total=total, page=page, page_size=page_size)


@router.post("/refresh")
def refresh_alerts(
    db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER", "REVIEWER")),
):
    """Explicit alert-refresh mechanism for the demo (documented: reruns the
    deterministic evaluation; never duplicates alerts or reopens resolved ones)."""
    result = alert_service.evaluate_alerts(db)
    record_audit(db, actor=user.username, event_type="ALERTS_REFRESHED",
                 entity_type="system", entity_id="alerts",
                 summary="Alert evaluation rerun", meta=result)
    db.commit()
    return result


@router.get("/{pk}", response_model=AlertOut)
def get_alert(pk: int, db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    alert = db.get(CoordinationAlert, pk)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/{pk}/acknowledge", response_model=AlertOut)
def acknowledge(
    pk: int, payload: AcknowledgeRequest, db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER", "REVIEWER")),
):
    alert = db.get(CoordinationAlert, pk)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status != AlertStatus.OPEN:
        raise HTTPException(status_code=422, detail="Only OPEN alerts can be acknowledged")
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = user.username
    alert.acknowledged_at = now()
    record_audit(db, actor=user.username, event_type="ALERT_ACKNOWLEDGED",
                 entity_type="coordination_alert", entity_id=str(alert.id),
                 summary=f"Alert {alert.alert_type.value} acknowledged",
                 rationale=payload.note,
                 before={"status": "OPEN"}, after={"status": "ACKNOWLEDGED"})
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/{pk}/resolve", response_model=AlertOut)
def resolve(
    pk: int, payload: ResolveRequest, db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER", "REVIEWER")),
):
    alert = db.get(CoordinationAlert, pk)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == AlertStatus.RESOLVED:
        raise HTTPException(status_code=422, detail="Alert is already resolved")
    before = {"status": alert.status.value}
    alert.status = AlertStatus.RESOLVED
    alert.resolved_by = user.username
    alert.resolved_at = now()
    alert.resolution_note = payload.resolution_note
    record_audit(db, actor=user.username, event_type="ALERT_RESOLVED",
                 entity_type="coordination_alert", entity_id=str(alert.id),
                 summary=f"Alert {alert.alert_type.value} resolved",
                 rationale=payload.resolution_note,
                 before=before, after={"status": "RESOLVED"})
    db.commit()
    db.refresh(alert)
    return alert
