"""SQLAlchemy domain model for INSTITRACE.

Documents the three core domain distinctions kept strictly separate:
  A. Same-institution relationships (institution_id on cases only).
  B. Cross-bureau coordination alerts (CoordinationAlert rows).
  C. Potential same-incident assessments (RelationshipAssessment rows).
"""
import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .clock import now as clock_now
from .database import Base


class CaseStatus(str, enum.Enum):
    PENDING = "PENDING"
    UNDER_PROCESS = "UNDER_PROCESS"
    DISPOSED = "DISPOSED"
    TRANSFERRED = "TRANSFERRED"
    ESCALATED = "ESCALATED"


# Valid state transitions. DISPOSED is terminal. A TRANSFERRED case can be
# re-accepted by the receiving bureau (back to PENDING/UNDER_PROCESS) - a
# transfer changes handling, it never disposes the case.
VALID_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.PENDING: {
        CaseStatus.UNDER_PROCESS,
        CaseStatus.DISPOSED,
        CaseStatus.TRANSFERRED,
        CaseStatus.ESCALATED,
    },
    CaseStatus.UNDER_PROCESS: {
        CaseStatus.DISPOSED,
        CaseStatus.TRANSFERRED,
        CaseStatus.ESCALATED,
    },
    CaseStatus.ESCALATED: {
        CaseStatus.UNDER_PROCESS,
        CaseStatus.DISPOSED,
        CaseStatus.TRANSFERRED,
    },
    CaseStatus.TRANSFERRED: {CaseStatus.PENDING, CaseStatus.UNDER_PROCESS},
    CaseStatus.DISPOSED: set(),
}

#: Statuses that count as "active" for deadline/overdue/alert purposes.
ACTIVE_STATUSES = {
    CaseStatus.PENDING,
    CaseStatus.UNDER_PROCESS,
    CaseStatus.ESCALATED,
    CaseStatus.TRANSFERRED,
}


class Priority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RelationshipType(str, enum.Enum):
    POTENTIAL_SAME_INCIDENT = "POTENTIAL_SAME_INCIDENT"
    PROCEDURAL_LINK = "PROCEDURAL_LINK"
    NO_RELATIONSHIP_ESTABLISHED = "NO_RELATIONSHIP_ESTABLISHED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AssessmentStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class AlertType(str, enum.Enum):
    CROSS_BUREAU_COORDINATION = "CROSS_BUREAU_COORDINATION"
    POTENTIAL_SAME_INCIDENT = "POTENTIAL_SAME_INCIDENT"
    PENDING_REMINDER = "PENDING_REMINDER"
    APPROACHING_DEADLINE = "APPROACHING_DEADLINE"
    OVERDUE = "OVERDUE"
    ESCALATION_REQUIRED = "ESCALATION_REQUIRED"


class AlertStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    BUREAU_OFFICER = "BUREAU_OFFICER"
    REVIEWER = "REVIEWER"
    READ_ONLY_MANAGER = "READ_ONLY_MANAGER"


class Bureau(Base):
    __tablename__ = "bureaus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    cases: Mapped[list["ComplaintCase"]] = relationship(back_populates="bureau")


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permanent_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    address: Mapped[str] = mapped_column(Text, default="", nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    district: Mapped[str | None] = mapped_column(String(64))
    institution_type: Mapped[str | None] = mapped_column(String(64))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=clock_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=clock_now, onupdate=clock_now, nullable=False
    )

    cases: Mapped[list["ComplaintCase"]] = relationship(back_populates="institution")


class ComplaintCase(Base):
    __tablename__ = "complaint_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id"), nullable=False, index=True
    )
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, native_enum=False), nullable=False, default=CaseStatus.PENDING, index=True
    )
    bureau_id: Mapped[int] = mapped_column(ForeignKey("bureaus.id"), nullable=False, index=True)
    officer_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, native_enum=False), nullable=False, default=Priority.MEDIUM
    )
    last_action_summary: Mapped[str | None] = mapped_column(String(512))
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_action: Mapped[str | None] = mapped_column(String(512))
    next_action_due_date: Mapped[date | None] = mapped_column(Date)
    expected_disposal_date: Mapped[date | None] = mapped_column(Date, index=True)
    actual_disposal_date: Mapped[date | None] = mapped_column(Date)
    source_record_ref: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=clock_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=clock_now, onupdate=clock_now, nullable=False
    )

    institution: Mapped[Institution] = relationship(back_populates="cases")
    bureau: Mapped[Bureau] = relationship(back_populates="cases")
    actions: Mapped[list["CaseAction"]] = relationship(
        back_populates="case", order_by="CaseAction.acted_at", cascade="all, delete-orphan"
    )
    transfers: Mapped[list["TransferRecord"]] = relationship(
        back_populates="case", order_by="TransferRecord.transferred_at", cascade="all, delete-orphan"
    )


class CaseAction(Base):
    """Business action history belonging to one complaint case (append-only via API)."""

    __tablename__ = "case_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("complaint_cases.id"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    acted_at: Mapped[datetime] = mapped_column(DateTime, default=clock_now, nullable=False)

    case: Mapped[ComplaintCase] = relationship(back_populates="actions")


class TransferRecord(Base):
    __tablename__ = "transfer_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("complaint_cases.id"), nullable=False, index=True)
    from_bureau_id: Mapped[int] = mapped_column(ForeignKey("bureaus.id"), nullable=False)
    to_bureau_id: Mapped[int] = mapped_column(ForeignKey("bureaus.id"), nullable=False)
    from_officer: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    to_officer: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    transferred_at: Mapped[datetime] = mapped_column(DateTime, default=clock_now, nullable=False)

    case: Mapped[ComplaintCase] = relationship(back_populates="transfers")


class RelationshipAssessment(Base):
    """Automated, explainable assessment of a pair of cases for a possible
    same-incident or procedural relationship. Human review decisions are kept
    separate from the automated recommendation and survive recomputation."""

    __tablename__ = "relationship_assessments"
    __table_args__ = (
        UniqueConstraint("pair_key", name="uq_assessment_pair"),
        Index("ix_assessment_status_type", "status", "relationship_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pair_key: Mapped[str] = mapped_column(String(160), nullable=False)
    source_case_id: Mapped[int] = mapped_column(ForeignKey("complaint_cases.id"), nullable=False)
    candidate_case_id: Mapped[int] = mapped_column(ForeignKey("complaint_cases.id"), nullable=False)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"), index=True)
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType, native_enum=False), nullable=False
    )
    supporting_evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    conflicting_evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    missing_evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rules_fired: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    score: Mapped[float | None] = mapped_column(Integer)  # heuristic agreement count, NOT a probability
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    # Evidence-versioned human review: the reviewer's decision is pinned to the
    # exact evidence they saw. If recomputation materially changes the evidence
    # (hash mismatch), the decision is PRESERVED but flagged requires_rereview
    # instead of being silently displayed as if it applies to new evidence.
    evidence_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    reviewed_evidence_hash: Mapped[str | None] = mapped_column(String(64))
    evidence_snapshot: Mapped[dict | None] = mapped_column(JSON)
    requires_rereview: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[AssessmentStatus] = mapped_column(
        Enum(AssessmentStatus, native_enum=False),
        nullable=False,
        default=AssessmentStatus.PENDING_REVIEW,
        index=True,
    )
    reviewer_identity: Mapped[str | None] = mapped_column(String(128))
    reviewer_rationale: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_recomputed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=clock_now, nullable=False)

    source_case: Mapped[ComplaintCase] = relationship(foreign_keys=[source_case_id])
    candidate_case: Mapped[ComplaintCase] = relationship(foreign_keys=[candidate_case_id])
    institution: Mapped[Institution | None] = relationship()


class RelationshipReview(Base):
    """Append-only history of human review decisions (FIX 2).

    Every CONFIRMED / REJECTED / DEFERRED decision - including every re-review
    - gets an immutable row here carrying the exact evidence snapshot, the
    evidence hash and the rule-engine version the reviewer decided against.
    Rows are never updated or deleted by the application; the assessment row
    itself keeps only the latest state.
    """

    __tablename__ = "relationship_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("relationship_assessments.id"), nullable=False, index=True
    )
    decision: Mapped[AssessmentStatus] = mapped_column(
        Enum(AssessmentStatus, native_enum=False), nullable=False, index=True
    )
    reviewer_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer_rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    evidence_snapshot: Mapped[dict | None] = mapped_column(JSON)
    evidence_hash: Mapped[str | None] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")


class CoordinationAlert(Base):
    """In-app alert with an occurrence lifecycle.

    `logical_key` identifies the recurring CONDITION (e.g. cross-bureau split
    for one institution, a case's overdue state for a given expected date).
    `occurrence` numbers successive activations of that condition. Resolved
    rows are immutable history: a recurring condition opens occurrence N+1 as
    a NEW active alert while all previous rows stay intact. At most one
    active (OPEN/ACKNOWLEDGED) alert exists per logical key at any time.
    """

    __tablename__ = "coordination_alerts"
    __table_args__ = (
        UniqueConstraint("logical_key", "occurrence", name="uq_alert_occurrence"),
        Index("ix_alerts_type_status", "alert_type", "status"),
        Index("ix_alerts_logical_key", "logical_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, native_enum=False), nullable=False, index=True
    )
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"), index=True)
    case_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # logical_key stays stable across occurrences; dedupe_key additionally
    # carries the occurrence number so every stored alert row is unique.
    logical_key: Mapped[str] = mapped_column(String(255), nullable=False)
    occurrence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, native_enum=False), nullable=False, default=AlertStatus.OPEN, index=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(128))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_by: Mapped[str | None] = mapped_column(String(128))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    # Informational same-incident alerts link to the assessment + evidence
    # version that raised them; NULL for operational alerts.
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("relationship_assessments.id"), index=True
    )
    evidence_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=clock_now, nullable=False)

    institution: Mapped[Institution | None] = relationship()


class AlertConditionState(Base):
    """Persisted presence state of each alert logical key across evaluations.

    Tracks whether the condition was present at the last evaluation, so that:
      * a condition that DISAPPEARED and LATER RETURNS opens a new occurrence;
      * a human-resolved alert while the condition persisted is not instantly
        respawned by the next recomputation (the resolution stands until the
        condition has been observed absent at least once)."""

    __tablename__ = "alert_condition_state"

    logical_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=clock_now, nullable=False)


class AuditEvent(Base):
    """Append-only audit trail of significant changes and decisions.

    There are deliberately no update/delete endpoints for this table."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    before_state: Mapped[dict | None] = mapped_column(JSON)
    after_state: Mapped[dict | None] = mapped_column(JSON)
    event_meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=clock_now, nullable=False, index=True)


class DemoUser(Base):
    __tablename__ = "demo_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
