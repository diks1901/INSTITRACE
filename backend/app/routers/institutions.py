"""Institution directory endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import (
    AlertStatus,
    AssessmentStatus,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
    DemoUser,
    Institution,
    RelationshipAssessment,
    UserRole,
)
from ..schemas import (
    CaseOut,
    InstitutionCreate,
    InstitutionOut,
    InstitutionUpdate,
    Page,
)
from ..security import require_roles
from ..services.audit import record_audit
from ..clock import now

router = APIRouter(prefix="/institutions", tags=["institutions"])


@router.get("", response_model=Page[InstitutionOut])
def list_institutions(
    q: str | None = Query(default=None, description="Search name or permanent ID"),
    region: str | None = None,
    state: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: DemoUser = Depends(require_roles()),
):
    stmt = select(Institution)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Institution.name.ilike(like)) | (Institution.permanent_id.ilike(like)))
    if region:
        stmt = stmt.where(Institution.region == region)
    if state:
        stmt = stmt.where(Institution.state == state)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(Institution.name).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(items=[InstitutionOut.model_validate(i) for i in items],
                total=total, page=page, page_size=page_size)


@router.post("", response_model=InstitutionOut, status_code=201)
def create_institution(
    payload: InstitutionCreate,
    db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles(UserRole.ADMIN)),
):
    if db.scalar(select(Institution).where(Institution.permanent_id == payload.permanent_id)):
        raise HTTPException(status_code=409, detail="Institution permanent ID already exists")
    inst = Institution(**payload.model_dump(), is_demo=True)
    db.add(inst)
    db.flush()
    record_audit(db, actor=user.username, event_type="INSTITUTION_CREATED",
                 entity_type="institution", entity_id=inst.permanent_id,
                 summary=f"Institution {inst.name} created",
                 after={"name": inst.name, "region": inst.region})
    db.commit()
    db.refresh(inst)
    return inst


@router.get("/{pk}")
def institution_detail(
    pk: int,
    db: Session = Depends(get_db),
    _: DemoUser = Depends(require_roles()),
):
    inst = db.get(Institution, pk)
    if inst is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    cases = db.scalars(
        select(ComplaintCase).where(ComplaintCase.institution_id == pk)
        .options(selectinload(ComplaintCase.bureau), selectinload(ComplaintCase.institution))
        .order_by(ComplaintCase.receipt_date.desc())
    ).all()
    alerts = db.scalars(
        select(CoordinationAlert).where(CoordinationAlert.institution_id == pk)
        .order_by(CoordinationAlert.created_at.desc())
    ).all()
    assessments = db.scalars(
        select(RelationshipAssessment).where(RelationshipAssessment.institution_id == pk)
        .order_by(RelationshipAssessment.created_at.desc())
    ).all()
    return {
        "institution": InstitutionOut.model_validate(inst),
        "cases": [CaseOut.model_validate(c) for c in cases],
        "alerts": alerts,
        "assessments": assessments,
        "summary": {
            "total_cases": len(cases),
            "active_cases": sum(1 for c in cases if c.status != CaseStatus.DISPOSED),
            "open_coordination_alerts": sum(
                1 for a in alerts if a.status != AlertStatus.RESOLVED
                and a.alert_type.value == "CROSS_BUREAU_COORDINATION"
            ),
            "pending_reviews": sum(
                1 for a in assessments if a.status == AssessmentStatus.PENDING_REVIEW
            ),
        },
    }


@router.patch("/{pk}", response_model=InstitutionOut)
def update_institution(
    pk: int,
    payload: InstitutionUpdate,
    db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles(UserRole.ADMIN)),
):
    inst = db.get(Institution, pk)
    if inst is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    data = payload.model_dump(exclude_unset=True)
    before = {"name": inst.name, "region": inst.region, "state": inst.state}
    for field, value in data.items():
        setattr(inst, field, value)
    inst.updated_at = now()
    record_audit(db, actor=user.username, event_type="INSTITUTION_UPDATED",
                 entity_type="institution", entity_id=inst.permanent_id,
                 summary=f"Institution updated fields: {sorted(data.keys())}",
                 before=before,
                 after={"name": inst.name, "region": inst.region, "state": inst.state})
    db.commit()
    db.refresh(inst)
    return inst


@router.get("/{pk}/cases", response_model=list[CaseOut])
def institution_cases(
    pk: int,
    db: Session = Depends(get_db),
    _: DemoUser = Depends(require_roles()),
):
    if db.get(Institution, pk) is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    cases = db.scalars(
        select(ComplaintCase).where(ComplaintCase.institution_id == pk)
        .options(selectinload(ComplaintCase.bureau), selectinload(ComplaintCase.institution))
        .order_by(ComplaintCase.receipt_date.desc())
    ).all()
    return [CaseOut.model_validate(c) for c in cases]
