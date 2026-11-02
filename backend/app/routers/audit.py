"""Audit trail endpoints - READ ONLY. No update/delete routes exist by design."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditEvent, DemoUser
from ..schemas import AuditEventOut, Page
from ..security import require_roles

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=Page[AuditEventOut])
def list_audit_events(
    entity_type: str | None = None,
    event_type: str | None = None,
    actor: str | None = None,
    entity_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: DemoUser = Depends(require_roles()),
):
    stmt = select(AuditEvent)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if actor:
        stmt = stmt.where(AuditEvent.actor == actor)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    stmt = stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[AuditEventOut.model_validate(e) for e in items],
                total=total, page=page, page_size=page_size)
