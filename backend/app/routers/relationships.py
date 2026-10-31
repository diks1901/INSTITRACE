"""Relationship assessment endpoints (same-incident coordination centre)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import (
    AssessmentStatus,
    ComplaintCase,
    DemoUser,
    RelationshipAssessment,
    RelationshipReview,
    RelationshipType,
)
from ..schemas import (
    Page,
    RecomputeResult,
    RelationshipAssessmentOut,
    ReviewOut,
    ReviewRequest,
)
from ..security import require_roles
from ..services import matching_service

router = APIRouter(prefix="/relationships", tags=["relationships"])


def _with_cases(db: Session, rows: list[RelationshipAssessment]) -> list[dict]:
    case_ids = {r.source_case_id for r in rows} | {r.candidate_case_id for r in rows}
    cases = {
        c.id: c for c in db.scalars(select(ComplaintCase).where(ComplaintCase.id.in_(case_ids)))
    } if case_ids else {}
    out = []
    for r in rows:
        item = RelationshipAssessmentOut.model_validate(r).model_dump()
        src, cand = cases.get(r.source_case_id), cases.get(r.candidate_case_id)
        item["source_case"] = {"id": src.id, "case_id": src.case_id, "status": src.status.value,
                               "bureau_id": src.bureau_id, "subject": src.subject,
                               "category": src.category} if src else None
        item["candidate_case"] = {"id": cand.id, "case_id": cand.case_id, "status": cand.status.value,
                                  "bureau_id": cand.bureau_id, "subject": cand.subject,
                                  "category": cand.category} if cand else None
        out.append(item)
    return out


@router.get("")
def list_assessments(
    status: AssessmentStatus | None = None,
    relationship_type: RelationshipType | None = None,
    institution_id: int | None = None,
    case_pk: int | None = Query(default=None, description="Internal case primary key, either side"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: DemoUser = Depends(require_roles()),
):
    stmt = select(RelationshipAssessment)
    if status:
        stmt = stmt.where(RelationshipAssessment.status == status)
    if relationship_type:
        stmt = stmt.where(RelationshipAssessment.relationship_type == relationship_type)
    if institution_id:
        stmt = stmt.where(RelationshipAssessment.institution_id == institution_id)
    if case_pk:
        stmt = stmt.where(
            (RelationshipAssessment.source_case_id == case_pk)
            | (RelationshipAssessment.candidate_case_id == case_pk)
        )
    stmt = stmt.order_by(RelationshipAssessment.created_at.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": _with_cases(db, rows), "total": total, "page": page, "page_size": page_size}


@router.post("/recompute", response_model=RecomputeResult)
def recompute(
    db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "REVIEWER")),
):
    return matching_service.recompute_all(db, actor=user.username)


@router.get("/{pk}")
def get_assessment(pk: int, db: Session = Depends(get_db),
                   _: DemoUser = Depends(require_roles())):
    row = db.get(RelationshipAssessment, pk)
    if row is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return _with_cases(db, [row])[0]


@router.post("/{pk}/review")
def review(
    pk: int, payload: ReviewRequest, db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN", "REVIEWER")),
):
    row = matching_service.review_assessment(
        db, pk, decision=payload.decision, rationale=payload.rationale,
        reviewer=user.username,
    )
    return _with_cases(db, [row])[0]


@router.get("/{pk}/reviews", response_model=list[ReviewOut])
def review_history(pk: int, db: Session = Depends(get_db),
                   _: DemoUser = Depends(require_roles())):
    """Append-only review history for an assessment, newest first."""
    if db.get(RelationshipAssessment, pk) is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return db.scalars(
        select(RelationshipReview)
        .where(RelationshipReview.assessment_id == pk)
        .order_by(RelationshipReview.reviewed_at.desc(), RelationshipReview.id.desc())
    ).all()
