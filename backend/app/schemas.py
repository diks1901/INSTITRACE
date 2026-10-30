"""Pydantic request/response schemas. These define the API contract and carry
server-side validation for every consequential action."""
from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import (
    AlertStatus,
    AlertType,
    AssessmentStatus,
    CaseStatus,
    Priority,
    RelationshipType,
    UserRole,
)

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------- auth ------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    token: str
    username: str
    display_name: str
    role: UserRole
    demo_notice: str


class CurrentUser(BaseModel):
    username: str
    display_name: str
    role: UserRole


# ------------------------------------------------------------ institutions --
class InstitutionBase(BaseModel):
    permanent_id: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=3, max_length=255)
    address: str = ""
    region: str = Field(min_length=2, max_length=64)
    state: str = Field(min_length=2, max_length=64)
    district: str | None = None
    institution_type: str | None = None


class InstitutionCreate(InstitutionBase):
    pass


class InstitutionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    address: str | None = None
    region: str | None = Field(default=None, min_length=2, max_length=64)
    state: str | None = Field(default=None, min_length=2, max_length=64)
    district: str | None = None
    institution_type: str | None = None


class InstitutionOut(InstitutionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class InstitutionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    permanent_id: str
    name: str
    region: str
    state: str


# ---------------------------------------------------------------- cases -----
class CaseBase(BaseModel):
    case_id: str = Field(min_length=3, max_length=64)
    institution_id: int
    receipt_date: date
    category: str = Field(min_length=2, max_length=64)
    subject: str = Field(min_length=3, max_length=255)
    description: str = ""
    bureau_id: int
    officer_name: str = ""
    priority: Priority = Priority.MEDIUM
    next_action: str | None = None
    next_action_due_date: date | None = None
    expected_disposal_date: date | None = None
    source_record_ref: str | None = None


class CaseCreate(CaseBase):
    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.expected_disposal_date is not None
            and self.expected_disposal_date < self.receipt_date
        ):
            raise ValueError("expected_disposal_date cannot be before receipt_date")
        return self


class CaseUpdate(BaseModel):
    institution_id: int | None = None
    receipt_date: date | None = None
    category: str | None = Field(default=None, min_length=2, max_length=64)
    subject: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    officer_name: str | None = None
    priority: Priority | None = None
    next_action: str | None = None
    next_action_due_date: date | None = None
    expected_disposal_date: date | None = None
    source_record_ref: str | None = None


class BureauOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: str
    institution_id: int
    receipt_date: date
    category: str
    subject: str
    description: str
    status: CaseStatus
    bureau_id: int
    officer_name: str
    priority: Priority
    last_action_summary: str | None
    last_action_at: datetime | None
    next_action: str | None
    next_action_due_date: date | None
    expected_disposal_date: date | None
    actual_disposal_date: date | None
    source_record_ref: str | None
    created_at: datetime
    updated_at: datetime
    institution: InstitutionSummary
    bureau: BureauOut


class CaseActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action_type: str
    summary: str
    actor: str
    from_status: str | None
    to_status: str | None
    acted_at: datetime


class TransferRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    from_bureau_id: int
    to_bureau_id: int
    from_officer: str
    to_officer: str
    reason: str
    actor: str
    transferred_at: datetime


class CaseDetailOut(CaseOut):
    actions: list[CaseActionOut] = []
    transfers: list[TransferRecordOut] = []


# ------------------------------------------------------- case workflow -----
class StatusUpdateRequest(BaseModel):
    to_status: CaseStatus
    summary: str = Field(min_length=3, max_length=512)
    rationale: str | None = None
    actual_disposal_date: date | None = None

    @model_validator(mode="after")
    def disposal_date_required(self):
        if self.to_status == CaseStatus.DISPOSED and self.actual_disposal_date is None:
            # default handled in service; explicit date preferred
            pass
        return self


class AssignmentUpdateRequest(BaseModel):
    officer_name: str = Field(min_length=2, max_length=128)
    summary: str = Field(min_length=3, max_length=512)


class TransferRequest(BaseModel):
    to_bureau_id: int
    to_officer_name: str = Field(min_length=2, max_length=128)
    reason: str = Field(min_length=5, max_length=512)


class EscalateRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=512)


class AddActionRequest(BaseModel):
    summary: str = Field(min_length=3, max_length=512)
    action_type: str = Field(default="REMARK", max_length=64)


class NextActionUpdateRequest(BaseModel):
    next_action: str = Field(min_length=3, max_length=512)
    next_action_due_date: date | None = None
    expected_disposal_date: date | None = None


# ---------------------------------------------------------- relationships ---
class RelationshipAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_case_id: int
    candidate_case_id: int
    institution_id: int | None
    relationship_type: RelationshipType
    supporting_evidence: list
    conflicting_evidence: list
    missing_evidence: list
    rules_fired: list
    score: float | None
    rule_version: str
    # evidence-versioned review fields (pinned to what the reviewer saw)
    evidence_hash: str | None = None
    reviewed_evidence_hash: str | None = None
    evidence_snapshot: dict | None = None
    requires_rereview: bool = False
    status: AssessmentStatus
    reviewer_identity: str | None
    reviewer_rationale: str | None
    reviewed_at: datetime | None
    last_recomputed_at: datetime | None
    created_at: datetime


class ReviewRequest(BaseModel):
    decision: AssessmentStatus  # CONFIRMED | REJECTED | DEFERRED only (validated in service)
    rationale: str = Field(min_length=5, max_length=1024)


class RecomputeResult(BaseModel):
    assessments_created: int
    assessments_updated: int
    alerts_created: int
    human_decisions_preserved: int


# ---------------------------------------------------------------- alerts ----
class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    alert_type: AlertType
    institution_id: int | None
    case_ids: list
    title: str
    description: str
    occurrence: int = 1  # which recurrence of this condition this alert is
    status: AlertStatus
    acknowledged_by: str | None
    acknowledged_at: datetime | None
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime


class AcknowledgeRequest(BaseModel):
    note: str | None = Field(default=None, max_length=512)


class ResolveRequest(BaseModel):
    resolution_note: str = Field(min_length=5, max_length=1024)


# ---------------------------------------------------------------- audit -----
class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor: str
    event_type: str
    entity_type: str
    entity_id: str
    summary: str
    rationale: str | None
    before_state: dict | None
    after_state: dict | None
    event_meta: dict | None
    created_at: datetime
