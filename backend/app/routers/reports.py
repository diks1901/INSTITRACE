"""Reports, analytics and CSV export endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DemoUser
from ..security import require_roles
from ..services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


def _run(db: Session, name: str, region: str | None = None, state: str | None = None) -> dict:
    fn = report_service.REPORTS.get(name)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"Unknown report '{name}'")
    if name == "institutions":
        return fn(db, region=region, state=state)
    return fn(db)


@router.get("/institutions")
def institutions_report(region: str | None = None, state: str | None = None,
                        db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    return _run(db, "institutions", region, state)


@router.get("/bureaus")
def bureaus_report(db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    return _run(db, "bureaus")


@router.get("/regions")
def regions_report(db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    return _run(db, "regions")


@router.get("/statuses")
def statuses_report(db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    return _run(db, "statuses")


@router.get("/ageing")
def ageing_report(db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    return _run(db, "ageing")


@router.get("/disposal")
def disposal_report(db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    return _run(db, "disposal")


@router.get("/overlaps")
def overlaps_report(db: Session = Depends(get_db), _: DemoUser = Depends(require_roles())):
    return _run(db, "overlaps")


@router.get("/export.csv")
def export_csv(
    report: str = Query(default="institutions"),
    region: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
    _: DemoUser = Depends(require_roles()),
):
    filters = {"report": report, "region": region, "state": state}
    data = _run(db, report, region, state)
    csv_text = report_service.build_csv(data["title"], data["columns"], data["rows"], filters)
    filename = f"institrace-{report}-report.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
