"""Complaint/case registry endpoints with server-side filtering, sorting,
pagination and the transactional case workflow actions."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..clock import today
from ..config import get_settings
from ..database import get_db
from ..models import (
    ACTIVE_STATUSES,
    AlertStatus,
    AlertType,
    AssessmentStatus,
    Bureau,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
    DemoUser,
    Institution,
    RelationshipAssessment,
)
from ..schemas import (
    AddActionRequest,
    AssignmentUpdateRequest,
    CaseActionOut,
    CaseCreate,
    CaseDetailOut,
    CaseOut,
    CaseUpdate,
    EscalateRequest,
    NextActionUpdateRequest,
    Page,
    RelationshipAssessmentOut,
    StatusUpdateRequest,
    TransferRequest,
)
from ..security import require_roles
from ..services import case_service

router = APIRouter(prefix="/cases", tags=["cases"])

READ = require_roles()

SORTABLE = {
    "receipt_date": ComplaintCase.receipt_date,
    "expected_disposal_date": ComplaintCase.expected_disposal_date,
    "status": ComplaintCase.status,
    "case_id": ComplaintCase.case_id,
    "category": ComplaintCase.category,
    "priority": ComplaintCase.priority,
}


@router.get("", response_model=Page[CaseOut])
def list_cases(
    q: str | None = Query(default=None, description="Search case ID or subject"),
    institution_id: int | None = None,
    institution_q: str | None = Query(default=None, description="Institution name/permanent ID"),
    bureau_id: int | None = None,
    region: str | None = None,
    category: str | None = None,
    status: CaseStatus | None = None,
    receipt_from: date | None = None,
    receipt_to: date | None = None,
    overdue: bool | None = Query(default=None, description="Only overdue active cases"),
    approaching: bool | None = Query(default=None, description="Approaching deadline (prototype threshold)"),
    review_state: AssessmentStatus | None = Query(
        default=None, description="Only cases having an assessment in this review state"
    ),
    sort: str = Query(default="receipt_date"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: DemoUser = Depends(READ),
):
    setts = get_settings()
    stmt = select(ComplaintCase).options(
        selectinload(ComplaintCase.institution), selectinload(ComplaintCase.bureau)
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where((ComplaintCase.case_id.ilike(like)) | (ComplaintCase.subject.ilike(like)))
    if institution_id:
        stmt = stmt.where(ComplaintCase.institution_id == institution_id)
    if institution_q or region:
        stmt = stmt.join(Institution, ComplaintCase.institution_id == Institution.id)
        if institution_q:
            like = f"%{institution_q}%"
            stmt = stmt.where((Institution.name.ilike(like)) | (Institution.permanent_id.ilike(like)))
        if region:
            stmt = stmt.where(Institution.region == region)
    if bureau_id:
        stmt = stmt.where(ComplaintCase.bureau_id == bureau_id)
    if category:
        stmt = stmt.where(ComplaintCase.category == category)
    if status:
        stmt = stmt.where(ComplaintCase.status == status)
    if receipt_from:
        stmt = stmt.where(ComplaintCase.receipt_date >= receipt_from)
    if receipt_to:
        stmt = stmt.where(ComplaintCase.receipt_date <= receipt_to)
    today_d = today()
    if overdue:
        stmt = stmt.where(
            ComplaintCase.status.in_(ACTIVE_STATUSES),
            ComplaintCase.expected_disposal_date.is_not(None),
            ComplaintCase.expected_disposal_date < today_d,
        )
    if approaching:
        stmt = stmt.where(
            ComplaintCase.status.in_(ACTIVE_STATUSES),
            ComplaintCase.expected_disposal_date.is_not(None),
            ComplaintCase.expected_disposal_date >= today_d,
            ComplaintCase.expected_disposal_date <= today_d + timedelta(days=setts.deadline_warning_days),
        )
    if review_state:
        sub = (
            select(RelationshipAssessment.id)
            .where(
                RelationshipAssessment.status == review_state,
                (RelationshipAssessment.source_case_id == ComplaintCase.id)
                | (RelationshipAssessment.candidate_case_id == ComplaintCase.id),
            )
            .exists()
        )
        stmt = stmt.where(sub)

    sort_col = SORTABLE.get(sort, ComplaintCase.receipt_date)
    stmt = stmt.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc(),
                         ComplaintCase.id.asc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[CaseOut.model_validate(c) for c in items],
                total=total, page=page, page_size=page_size)


@router.post("", response_model=CaseOut, status_code=201)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER")),
):
    case = case_service.create_case(db, payload, user.username)
    return CaseOut.model_validate(case)


def _detail(db: Session, pk: int) -> dict:
    case = db.scalar(
        select(ComplaintCase).where(ComplaintCase.id == pk).options(
            selectinload(ComplaintCase.institution),
            selectinload(ComplaintCase.bureau),
            selectinload(ComplaintCase.actions),
            selectinload(ComplaintCase.transfers),
        )
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    assessments = db.scalars(
        select(RelationshipAssessment).where(
            (RelationshipAssessment.source_case_id == pk)
            | (RelationshipAssessment.candidate_case_id == pk)
        ).order_by(RelationshipAssessment.created_at.desc())
    ).all()
    # All alert types carry institution_id; scope by institution (portable
    # SQL, no JSON-containment dialect differences) then match membership in
    # Python - exact and works identically on SQLite and PostgreSQL.
    alerts = db.scalars(
        select(CoordinationAlert)
        .where(CoordinationAlert.institution_id == case.institution_id)
        .order_by(CoordinationAlert.created_at.desc())
    ).all()
    alerts = [a for a in alerts if case.case_id in (a.case_ids or [])]
    return {
        "case": CaseDetailOut.model_validate(case),
        "assessments": [RelationshipAssessmentOut.model_validate(a) for a in assessments],
        "alerts": alerts,
    }


@router.get("/{pk}")
def case_detail(pk: int, db: Session = Depends(get_db), _: DemoUser = Depends(READ)):
    return _detail(db, pk)


@router.patch("/{pk}", response_model=CaseOut)
def update_case(
    pk: int, payload: CaseUpdate, db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER")),
):
    return CaseOut.model_validate(case_service.update_case(db, pk, payload, user.username))


@router.get("/{pk}/history", response_model=list[CaseActionOut])
def case_history(pk: int, db: Session = Depends(get_db), _: DemoUser = Depends(READ)):
    case = db.get(ComplaintCase, pk)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return [CaseActionOut.model_validate(a) for a in case.actions]


@router.post("/{pk}/actions", response_model=CaseOut, status_code=201)
def add_action(
    pk: int, payload: AddActionRequest, db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER")),
):
    return CaseOut.model_validate(
        case_service.add_action(db, pk, summary=payload.summary,
                                action_type=payload.action_type, actor=user.username)
    )


@router.post("/{pk}/status", response_model=CaseOut)
def update_status(
    pk: int, payload: StatusUpdateRequest, db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER")),
):
    return CaseOut.model_validate(
        case_service.change_status(
            db, pk, to_status=payload.to_status, summary=payload.summary,
            rationale=payload.rationale, actor=user.username,
            actual_disposal_date=payload.actual_disposal_date,
        )
    )


@router.post("/{pk}/assign", response_model=CaseOut)
def assign(
    pk: int, payload: AssignmentUpdateRequest, db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER")),
):
    return CaseOut.model_validate(
        case_service.change_assignment(db, pk, officer_name=payload.officer_name,
                                       summary=payload.summary, actor=user.username)
    )


@router.post("/{pk}/transfer", response_model=CaseOut)
def transfer(
    pk: int, payload: TransferRequest, db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER")),
):
    return CaseOut.model_validate(
        case_service.transfer_case(db, pk, to_bureau_id=payload.to_bureau_id,
                                   to_officer_name=payload.to_officer_name,
                                   reason=payload.reason, actor=user.username)
    )


@router.post("/{pk}/escalate", response_model=CaseOut)
def escalate(
    pk: int, payload: EscalateRequest, db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER")),
):
    return CaseOut.model_validate(
        case_service.escalate_case(db, pk, reason=payload.reason, actor=user.username)
    )


@router.post("/{pk}/next-action", response_model=CaseOut)
def next_action(
    pk: int, payload: NextActionUpdateRequest, db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "BUREAU_OFFICER")),
):
    return CaseOut.model_validate(
        case_service.update_next_action(
            db, pk, next_action=payload.next_action,
            next_action_due_date=payload.next_action_due_date,
            expected_disposal_date=payload.expected_disposal_date, actor=user.username,
        )
    )



