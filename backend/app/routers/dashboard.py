"""Dashboard endpoints - all values computed from the live database."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DemoUser
from ..security import require_roles
from ..services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    return dashboard_service.summary(db)


@router.get("/bureau-workload")
def bureau_workload(db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    return dashboard_service.bureau_workload(db)


@router.get("/trends")
def trends(months: int = Query(default=12, ge=1, le=36),
           db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    return dashboard_service.trends(db, months=months)
