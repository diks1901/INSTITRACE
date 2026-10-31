"""Deterministic synthetic demo data - INSTITRACE.

ALL data here is synthetic and clearly labelled DEMO. No real AICTE records,
real persons or real identifiers are used. Identifiers follow DEMO-INS-xxx /
DEMO-CASE-xxx. Dates are anchored to the day the seed runs so deadline
scenarios display correctly; content is otherwise fixed and repeatable.

Fixture scenarios (documented in docs/demo-script.md):
  A. same incident across bureaus           DEMO-CASE-001/002 @ DEMO-INS-001
  B. same institution, unrelated incidents  DEMO-CASE-003/004 @ DEMO-INS-002
  C. ambiguous / insufficient evidence      DEMO-CASE-005/006 @ DEMO-INS-003
  D. same incident, same bureau             DEMO-CASE-007/008 @ DEMO-INS-004
  E. different institutions, similar text   DEMO-CASE-009/010
  F. transfer with preserved history        DEMO-CASE-011 @ DEMO-INS-007
  G. overdue / approaching / stale-deadline  DEMO-CASE-012/013/014
"""
import argparse
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import now, today
from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import (
    AlertConditionState,
    AlertStatus,
    AlertType,
    AssessmentStatus,
    Bureau,
    CaseAction,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
    DemoUser,
    Institution,
    RelationshipAssessment,
    RelationshipReview,
    TransferRecord,
    AuditEvent,
    UserRole,
    Priority,
)
from .security import hash_password
import os

from .services import alert_service, matching_service
from .services.matching_service import review_assessment

DEMO_PASSWORDS = {
    "admin": os.environ.get("INSTITRACE_DEMO_ADMIN_PASSWORD", "InstiTrace#Demo1"),
    "officer.rb": os.environ.get("INSTITRACE_DEMO_OFFICER_PASSWORD", "Officer#Demo1"),
    "reviewer": os.environ.get("INSTITRACE_DEMO_REVIEWER_PASSWORD", "Reviewer#Demo1"),
    "manager": os.environ.get("INSTITRACE_DEMO_MANAGER_PASSWORD", "Manager#Demo1"),
}

BUREAUS = [
    ("RB", "Regulation Bureau", "Handles regulation and approval related complaints."),
    ("PGRC", "Public Grievance Redressal Cell", "Central grievance redressal cell."),
    ("EVC", "e-Governance & Vigilance Cell", "Demo third bureau/cell for coordination demos."),
]

INSTITUTIONS = [
    # permanent_id, name, region, state, district, type
    ("DEMO-INS-001", "Sunrise Institute of Technology", "Northern", "Delhi", "New Delhi", "Engineering & Technology"),
    ("DEMO-INS-002", "Lakeview College of Engineering", "Southern", "Karnataka", "Bengaluru Urban", "Engineering & Technology"),
    ("DEMO-INS-003", "Riverbend Management Institute", "Western", "Maharashtra", "Pune", "Management"),
    ("DEMO-INS-004", "Hillcrest Polytechnic College", "Northern", "Himachal Pradesh", "Shimla", "Polytechnic"),
    ("DEMO-INS-005", "Greenfield Institute of Pharmacy", "Eastern", "West Bengal", "Kolkata", "Pharmacy"),
    ("DEMO-INS-006", "Coastal College of Architecture", "Southern", "Tamil Nadu", "Chennai", "Architecture"),
    ("DEMO-INS-007", "Northgate Institute of Applied Arts", "Central", "Madhya Pradesh", "Bhopal", "Applied Arts & Crafts"),
    ("DEMO-INS-008", "Trident Engineering College", "Western", "Gujarat", "Ahmedabad", "Engineering & Technology"),
    ("DEMO-INS-009", "Silverline College of Management", "North-Eastern", "Assam", "Kamrup Metropolitan", "Management"),
    ("DEMO-INS-010", "Maple Institute of Hotel Management", "Northern", "Uttar Pradesh", "Lucknow", "Hotel Management & Catering"),
    ("DEMO-INS-011", "Blue Ridge Technical Campus", "Southern", "Kerala", "Ernakulam", "Engineering & Technology"),
    ("DEMO-INS-012", "Vedant Institute of Pharmacy", "Central", "Chhattisgarh", "Raipur", "Pharmacy"),
    ("DEMO-INS-013", "Palm Grove College of Planning", "Southern", "Andhra Pradesh", "Visakhapatnam", "Town & Country Planning"),
    ("DEMO-INS-014", "Horizon Institute of Technology", "Eastern", "Odisha", "Khordha", "Engineering & Technology"),
    ("DEMO-INS-015", "Cedar Valley Engineering Institute", "Western", "Rajasthan", "Jaipur", "Engineering & Technology"),
]

CATEGORIES = [
    "Fees & Refund", "Admission & Enrollment", "Examination & Results",
    "Faculty & Staff", "Infrastructure", "Recognition & Approval",
    "Scholarship", "Ragging & Safety", "Document Verification", "Others",
]


def _date(days_ago: int = 0, days_ahead: int = 0):
    return today() - timedelta(days=days_ago) + timedelta(days=days_ahead)


def _attach_history(db: Session, case: ComplaintCase, entries: list[tuple[str, str, str, int]]):
    """entries: (action_type, summary, actor, acted_days_ago)."""
    for action_type, summary, actor, days_ago in entries:
        db.add(
            CaseAction(
                case_id=case.id,
                action_type=action_type,
                summary=summary,
                actor=actor,
                acted_at=now() - timedelta(days=days_ago),
                from_status=None,
                to_status=None,
            )
        )


def seed_demo(db: Session, reset: bool = False) -> dict:
    if reset:
        for model in (AlertConditionState, CoordinationAlert, RelationshipReview,
                      RelationshipAssessment, TransferRecord, CaseAction, AuditEvent,
                      ComplaintCase, Institution, Bureau, DemoUser):
            db.query(model).delete(synchronize_session=False)
        db.commit()

    if db.scalar(func_count(Institution)) > 0:
        return {"seeded": False, "reason": "Database already contains institutions. Use --reset for a demo reset."}

    bureaus = {code: Bureau(code=code, name=name, description=desc) for code, name, desc in BUREAUS}
    db.add_all(bureaus.values())
    db.flush()

    institutions: dict[str, Institution] = {}
    for pid, name, region, state, district, itype in INSTITUTIONS:
        inst = Institution(
            permanent_id=pid, name=name, address=f"Demo Campus Road, {district}",
            region=region, state=state, district=district,
            institution_type=itype, is_demo=True,
        )
        db.add(inst)
        institutions[pid] = inst
    db.flush()

    def C(case_uid: str, inst: str, bureau: str, category: str, subject: str,
          description: str, *, receipt_days_ago: int, status: CaseStatus,
          officer: str, priority: Priority = Priority.MEDIUM,
          expected_in: int | None = None, expected_overdue_by: int | None = None,
          disposed_days_ago: int | None = None,
          next_action: str | None = None, next_due_days_ago: int | None = None,
          source_record_ref: str | None = None) -> ComplaintCase:
        case = ComplaintCase(
            case_id=case_uid,
            institution_id=institutions[inst].id,
            receipt_date=_date(days_ago=receipt_days_ago),
            category=category,
            subject=subject,
            description=description,
            status=status,
            bureau_id=bureaus[bureau].id,
            officer_name=officer,
            priority=priority,
            expected_disposal_date=(
                _date(days_ahead=expected_in) if expected_in is not None
                else _date(days_ago=expected_overdue_by) if expected_overdue_by is not None
                else None
            ),
            actual_disposal_date=_date(days_ago=disposed_days_ago) if disposed_days_ago else None,
            next_action=next_action,
            next_action_due_date=_date(days_ago=next_due_days_ago) if next_due_days_ago is not None else None,
            source_record_ref=source_record_ref,
        )
        db.add(case)
        db.flush()
        db.add(CaseAction(
            case_id=case.id, action_type="CREATED",
            summary=f"Case {case_uid} registered (synthetic demo record).",
            actor="seed", from_status=None, to_status=CaseStatus.PENDING.value,
            acted_at=now() - timedelta(days=receipt_days_ago),
        ))
        if status != CaseStatus.PENDING:
            db.add(CaseAction(
                case_id=case.id, action_type="STATUS_CHANGE",
                summary=f"Status updated to {status.value}.",
                actor="seed", from_status=CaseStatus.PENDING.value, to_status=status.value,
                acted_at=now() - timedelta(days=max(0, receipt_days_ago - 3)),
            ))
        return case

    # ---------------- Scenario A: same incident, different bureaus ----------
    C("DEMO-CASE-001", "DEMO-INS-001", "RB", "Faculty & Staff",
      "Non-payment of faculty salaries for five months (INC-2025-0042)",
      "Faculty members report that salaries have not been disbursed for five "
      "months. Incident dated 2025-08-14, reference INC-2025-0042 and "
      "proceeding PROC-2025-0110 of the management committee are cited. "
      "Documented wage records and committee minutes are attached as references.",
      receipt_days_ago=54, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer R. Verma",
      expected_overdue_by=6, source_record_ref="SRC-PGPORTAL-1001",
      next_action="Obtain management response on salary disbursement schedule")
    C("DEMO-CASE-002", "DEMO-INS-001", "PGRC", "Faculty & Staff",
      "Salary dues complaint citing incident INC-2025-0042",
      "Grievance from teaching staff regarding unpaid salaries for the same "
      "period. Incident dated 2025-08-16 cites INC-2025-0042 and refers to "
      "proceeding PROC-2025-0110. Wage records, committee minutes and staff "
      "statements corroborate the claim.",
      receipt_days_ago=40, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer P. Nair",
      expected_in=11, source_record_ref="SRC-CPGRAMS-2202",
      next_action="Coordinate with Regulation Bureau on overlapping handling")

    # ---------------- Scenario B: same institution, unrelated incidents ------
    C("DEMO-CASE-003", "DEMO-INS-002", "RB", "Recognition & Approval",
      "Unapproved additional intake in CSE programme (INC-2025-0101)",
      "It is alleged that the college admitted 60 additional students into the "
      "Computer Science programme without approval. Incident dated 2025-03-10, "
      "reference INC-2025-0101 relates to the admission cycle audit.",
      receipt_days_ago=80, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer R. Verma",
      expected_in=20, next_action="Verify admission audit report")
    C("DEMO-CASE-004", "DEMO-INS-002", "PGRC", "Infrastructure",
      "Hostel water supply failure for three weeks (INC-2025-0207)",
      "Students of the boys' hostel report continuous water supply failure. "
      "Incident dated 2025-09-28, reference INC-2025-0207 relates to hostel "
      "maintenance, unrelated to any admission process.",
      receipt_days_ago=30, status=CaseStatus.PENDING, officer="Demo Officer P. Nair",
      expected_in=18, next_action="Seek engineering section inspection")

    # ---------------- Scenario C: ambiguous / insufficient evidence ----------
    C("DEMO-CASE-005", "DEMO-INS-003", "RB", "Others",
      "General complaint about administration",
      "Complainant expresses dissatisfaction with the administration. "
      "No specific incident reference, date or details provided.",
      receipt_days_ago=35, status=CaseStatus.PENDING, officer="Demo Officer R. Verma",
      expected_in=25)
    C("DEMO-CASE-006", "DEMO-INS-003", "PGRC", "Admission & Enrollment",
      "Query regarding enrollment paperwork",
      "Stakeholder asks about enrollment paperwork handling. "
      "No incident reference or clear dates given; record is incomplete.",
      receipt_days_ago=28, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer P. Nair",
      expected_in=9)

    # ---------------- Scenario D: same incident, same bureau -----------------
    C("DEMO-CASE-007", "DEMO-INS-004", "RB", "Document Verification",
      "Fake document submission during verification drive (INC-2025-0333)",
      "During document verification, forged migration certificates were "
      "detected. Incident dated 2025-07-02, reference INC-2025-0333. "
      "Verification cell memo and lab report cited as evidence.",
      receipt_days_ago=95, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer R. Verma",
      expected_in=14)
    C("DEMO-CASE-008", "DEMO-INS-004", "RB", "Document Verification",
      "Follow-up complaint on forged certificates INC-2025-0333",
      "A second complaint concerning the same forged migration certificates "
      "episode. Incident dated 2025-07-04, cites INC-2025-0333 and the "
      "verification cell memo. Lab report corroborates.",
      receipt_days_ago=88, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer R. Verma",
      expected_in=14)

    # ---------------- Scenario E: different institutions, similar wording ----
    C("DEMO-CASE-009", "DEMO-INS-005", "RB", "Fees & Refund",
      "Hostel fee refund not processed after admission withdrawal",
      "Student withdrew admission before classes began and requests hostel fee "
      "refund. Incident dated 2025-06-11, reference INC-2025-0501.",
      receipt_days_ago=25, status=CaseStatus.PENDING, officer="Demo Officer R. Verma",
      expected_in=17)
    C("DEMO-CASE-010", "DEMO-INS-006", "PGRC", "Fees & Refund",
      "Hostel fee refund not processed after admission withdrawal",
      "Student withdrew admission before classes began and requests hostel fee "
      "refund. Incident dated 2025-08-19, reference INC-2025-0777.",
      receipt_days_ago=22, status=CaseStatus.PENDING, officer="Demo Officer P. Nair",
      expected_in=13)

    # ---------------- Scenario F: transfer with preserved history -------------
    f_case = C("DEMO-CASE-011", "DEMO-INS-007", "EVC", "Scholarship",
      "Scholarship disbursement stalled after portal migration",
      "Students report scholarship disbursements stalled since the portal "
      "migration. Incident dated 2025-08-30, reference INC-2025-0666.",
      receipt_days_ago=48, status=CaseStatus.TRANSFERRED, officer="Demo Officer E. Rao",
      expected_overdue_by=4, next_action="Confirm portal reconciliation report",
      source_record_ref="SRC-NSP-3120")
    db.add(TransferRecord(
        case_id=f_case.id, from_bureau_id=bureaus["RB"].id, to_bureau_id=bureaus["EVC"].id,
        from_officer="Demo Officer R. Verma", to_officer="Demo Officer E. Rao",
        reason="Subject matter falls under e-Governance portal reconciliation.",
        actor="seed", transferred_at=now() - timedelta(days=10),
    ))
    db.add(CaseAction(
        case_id=f_case.id, action_type="TRANSFER",
        summary="Transferred from Regulation Bureau to e-Governance & Vigilance Cell "
        "(portal reconciliation domain).",
        actor="seed", from_status=CaseStatus.UNDER_PROCESS.value,
        to_status=CaseStatus.TRANSFERRED.value,
        acted_at=now() - timedelta(days=10),
    ))

    # ---------------- Scenario G: deadline handling ---------------------------
    C("DEMO-CASE-012", "DEMO-INS-008", "RB", "Infrastructure",
      "Laboratory safety equipment missing during inspection",
      "Inspection found mandated laboratory safety equipment missing. "
      "Incident dated 2025-07-21, reference INC-2025-0888.",
      receipt_days_ago=70, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer R. Verma",
      expected_overdue_by=10, next_action="Issue compliance notice")
    C("DEMO-CASE-013", "DEMO-INS-008", "PGRC", "Examination & Results",
      "Result withheld citing internal mark dispute",
      "Final-year student reports result withheld over disputed internal marks. "
      "Incident dated 2025-09-05, reference INC-2025-0910.",
      receipt_days_ago=33, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer P. Nair",
      expected_in=2, next_action="Collect examiner committee minutes")
    g_disp = C("DEMO-CASE-014", "DEMO-INS-009", "RB", "Admission & Enrollment",
      "Duplicate enrollment record resolved",
      "Duplicate enrollment record was identified and corrected by the "
      "institution registrar. Disposed after verification.",
      receipt_days_ago=60, status=CaseStatus.DISPOSED, officer="Demo Officer R. Verma",
      expected_overdue_by=12, disposed_days_ago=5)
    g_disp.last_action_summary = "Disposed after registrar verification."

    # ---------------- Additional volume across bureaus/regions/months --------
    C("DEMO-CASE-015", "DEMO-INS-010", "EVC", "Others",
      "Online grievance portal account locked",
      "Complainant unable to access portal account after password reset loop. "
      "Incident dated 2025-08-01, reference INC-2025-1200.",
      receipt_days_ago=90, status=CaseStatus.ESCALATED, officer="Demo Officer E. Rao",
      expected_overdue_by=15, priority=Priority.HIGH,
      next_action="Escalation review by cell head")
    C("DEMO-CASE-016", "DEMO-INS-010", "RB", "Faculty & Staff",
      "Guest faculty contract renewal dispute",
      "Guest faculty allege abrupt non-renewal of contracts. "
      "Incident dated 2025-07-14, reference INC-2025-1188.",
      receipt_days_ago=85, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer R. Verma",
      expected_in=6)
    C("DEMO-CASE-017", "DEMO-INS-011", "PGRC", "Scholarship",
      "Scholarship name mismatch corrected and closed",
      "Scholarship held due to name mismatch; corrected after document "
      "verification and disposed.",
      receipt_days_ago=120, status=CaseStatus.DISPOSED, officer="Demo Officer P. Nair",
      disposed_days_ago=80, expected_overdue_by=95)
    C("DEMO-CASE-018", "DEMO-INS-011", "PGRC", "Examination & Results",
      "Revaluation application not acknowledged",
      "Student reports revaluation application unacknowledged for six weeks. "
      "Incident dated 2025-09-12, reference INC-2025-1302.",
      receipt_days_ago=44, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer P. Nair",
      expected_in=21, next_action="Reminder to examination section",
      next_due_days_ago=3)
    C("DEMO-CASE-019", "DEMO-INS-012", "RB", "Document Verification",
      "Degree verification request completed",
      "Employer-requested degree verification completed and disposed.",
      receipt_days_ago=150, status=CaseStatus.DISPOSED, officer="Demo Officer R. Verma",
      disposed_days_ago=110, expected_overdue_by=125)
    C("DEMO-CASE-020", "DEMO-INS-012", "RB", "Ragging & Safety",
      "Alleged ragging incident in first-year hostel (INC-2025-1404)",
      "Parents report alleged ragging in first-year hostel block B. Incident "
      "dated 2025-10-02, reference INC-2025-1404.",
      receipt_days_ago=26, status=CaseStatus.ESCALATED, officer="Demo Officer R. Verma",
      expected_in=4, priority=Priority.HIGH, next_action="Awaiting anti-ragging committee report",
      next_due_days_ago=1)
    C("DEMO-CASE-021", "DEMO-INS-013", "PGRC", "Fees & Refund",
      "Caution deposit refund settled",
      "Caution deposit refund processed after escalation to accounts and "
      "disposed.",
      receipt_days_ago=65, status=CaseStatus.DISPOSED, officer="Demo Officer P. Nair",
      disposed_days_ago=20, expected_overdue_by=30)
    C("DEMO-CASE-022", "DEMO-INS-013", "EVC", "Others",
      "Student portal grade display error",
      "Portal displays incorrect grades for one course; IT ticket opened. "
      "Incident dated 2025-10-15, reference INC-2025-1499.",
      receipt_days_ago=12, status=CaseStatus.PENDING, officer="Demo Officer E. Rao",
      expected_in=3)
    C("DEMO-CASE-023", "DEMO-INS-014", "RB", "Recognition & Approval",
      "Alleged operation without extension of approval",
      "Institute allegedly admitting students without extension of approval "
      "for 2025-26. Incident dated 2025-06-30, reference INC-2025-1555.",
      receipt_days_ago=100, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer R. Verma",
      expected_overdue_by=35, priority=Priority.HIGH,
      next_action="Legal opinion on inspection findings")
    C("DEMO-CASE-024", "DEMO-INS-014", "RB", "Infrastructure",
      "Workshop machinery maintenance complaint closed",
      "Deprecated workshop machinery repaired after notice; disposed.",
      receipt_days_ago=170, status=CaseStatus.DISPOSED, officer="Demo Officer R. Verma",
      disposed_days_ago=130, expected_overdue_by=145)
    C("DEMO-CASE-025", "DEMO-INS-014", "PGRC", "Fees & Refund",
      "Transport fee excess charged; refunded",
      "Excess transport fee charge refunded to students; disposed.",
      receipt_days_ago=75, status=CaseStatus.DISPOSED, officer="Demo Officer P. Nair",
      disposed_days_ago=15, expected_overdue_by=40)
    C("DEMO-CASE-026", "DEMO-INS-015", "EVC", "Others",
      "Biometric attendance data sync failure",
      "Biometric attendance devices not syncing attendance to central server. "
      "Incident dated 2025-10-20, reference INC-2025-1601.",
      receipt_days_ago=9, status=CaseStatus.PENDING, officer="Demo Officer E. Rao",
      expected_in=21)
    C("DEMO-CASE-027", "DEMO-INS-015", "EVC", "Scholarship",
      "Merit scholarship list not published on portal",
      "Merit scholarship beneficiary list missing from portal since "
      "publication date. Incident dated 2025-05-18, reference INC-2025-1622.",
      receipt_days_ago=160, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer E. Rao",
      expected_overdue_by=40, next_action="Verify publication workflow with NIC team")
    C("DEMO-CASE-028", "DEMO-INS-010", "RB", "Faculty & Staff",
      "Non-payment of arrears closed after disbursement",
      "Arrears disbursed to staff after verification; disposed.",
      receipt_days_ago=155, status=CaseStatus.DISPOSED, officer="Demo Officer R. Verma",
      disposed_days_ago=125, expected_overdue_by=140)
    C("DEMO-CASE-029", "DEMO-INS-011", "PGRC", "Admission & Enrollment",
      "Admission cancellation request processed",
      "Admission cancellation and refund processed per norms; disposed.",
      receipt_days_ago=130, status=CaseStatus.DISPOSED, officer="Demo Officer P. Nair",
      disposed_days_ago=95, expected_overdue_by=105)
    C("DEMO-CASE-030", "DEMO-INS-012", "EVC", "Others",
      "Email account provisioning delay resolved",
      "Institutional email accounts provisioned after ticket escalation; "
      "disposed.",
      receipt_days_ago=95, status=CaseStatus.DISPOSED, officer="Demo Officer E. Rao",
      disposed_days_ago=55, expected_overdue_by=70)
    C("DEMO-CASE-031", "DEMO-INS-014", "RB", "Examination & Results",
      "Transcript issuance delay resolved",
      "Pending transcripts issued to alumni applicants; disposed.",
      receipt_days_ago=68, status=CaseStatus.DISPOSED, officer="Demo Officer R. Verma",
      disposed_days_ago=32, expected_overdue_by=45)
    C("DEMO-CASE-032", "DEMO-INS-013", "PGRC", "Infrastructure",
      "Library air-conditioning repair completed",
      "Library HVAC repaired and confirmed; disposed.",
      receipt_days_ago=58, status=CaseStatus.DISPOSED, officer="Demo Officer P. Nair",
      disposed_days_ago=22, expected_overdue_by=28)
    C("DEMO-CASE-033", "DEMO-INS-003", "PGRC", "Scholarship",
      "Scholarship eligibility criteria clarification",
      "Stakeholder seeks clarification on scholarship eligibility criteria "
      "for the current academic year.",
      receipt_days_ago=40, status=CaseStatus.PENDING, officer="Demo Officer P. Nair",
      expected_in=16)
    C("DEMO-CASE-034", "DEMO-INS-005", "PGRC", "Examination & Results",
      "Backlog exam schedule not announced",
      "Students report backlog examination schedule not yet announced. "
      "Incident dated 2025-08-24, reference INC-2025-1720.",
      receipt_days_ago=75, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer P. Nair",
      expected_in=30)
    C("DEMO-CASE-035", "DEMO-INS-006", "RB", "Recognition & Approval",
      "Alleged excess admissions beyond sanctioned intake",
      "Excess admissions beyond sanctioned intake alleged in B.Arch "
      "programme. Incident dated 2025-05-05, reference INC-2025-1812.",
      receipt_days_ago=165, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer R. Verma",
      expected_overdue_by=20,
      next_action="Review intake audit working notes")
    C("DEMO-CASE-036", "DEMO-INS-009", "EVC", "Others",
      "Online fee receipt not generated",
      "Fee receipts not generated on portal after payment; bank reference "
      "shared. Incident dated 2025-10-18, reference INC-2025-1904.",
      receipt_days_ago=10, status=CaseStatus.PENDING, officer="Demo Officer E. Rao",
      expected_in=19, next_action="Follow up with payment gateway team")
    C("DEMO-CASE-037", "DEMO-INS-015", "RB", "Faculty & Staff",
      "Faculty workload norm violation complaint",
      "Faculty allege teaching workload beyond norms in two departments. "
      "Incident dated 2025-04-02, reference INC-2025-1950.",
      receipt_days_ago=205, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer R. Verma",
      expected_overdue_by=55,
      next_action="Awaiting department-wise workload statements")
    C("DEMO-CASE-038", "DEMO-INS-001", "PGRC", "Infrastructure",
      "Sports ground fencing repaired",
      "Broken fencing around sports ground repaired; verified and disposed.",
      receipt_days_ago=115, status=CaseStatus.DISPOSED, officer="Demo Officer P. Nair",
      disposed_days_ago=70, expected_overdue_by=90)
    C("DEMO-CASE-039", "DEMO-INS-002", "EVC", "Document Verification",
      "Certificate attestation portal outage",
      "Certificate attestation module down for several days. Incident dated "
      "2025-09-25, reference INC-2025-1988.",
      receipt_days_ago=45, status=CaseStatus.ESCALATED, officer="Demo Officer E. Rao",
      expected_in=10, next_action="Vendor SLA review meeting")
    C("DEMO-CASE-040", "DEMO-INS-007", "PGRC", "Admission & Enrollment",
      "NRI quota admission documentation query",
      "Clarification sought on documentation for NRI quota admission. "
      "Incident dated 2025-10-10, reference INC-2025-1995.",
      receipt_days_ago=25, status=CaseStatus.UNDER_PROCESS, officer="Demo Officer P. Nair",
      expected_in=8, next_action="Draft clarification note")

    # ---------------- demo users ---------------------------------------------
    users = [
        ("admin", "Demo Administrator", UserRole.ADMIN),
        ("officer.rb", "Demo Bureau Officer (RB)", UserRole.BUREAU_OFFICER),
        ("reviewer", "Demo Relationship Reviewer", UserRole.REVIEWER),
        ("manager", "Demo Read-Only Manager", UserRole.READ_ONLY_MANAGER),
    ]
    for username, display, role in users:
        digest, salt = hash_password(DEMO_PASSWORDS[username])
        db.add(DemoUser(username=username, display_name=display, role=role,
                        password_hash=digest, password_salt=salt))
    db.commit()

    # ---------------- run engine + alert evaluation ---------------------------
    match_result = matching_service.recompute_all(db, actor="seed")
    alert_result = alert_service.evaluate_alerts(db)

    # ---------------- pre-seeded review decisions (Scenarios A/B) -------------
    assessments = {
        a.pair_key: a for a in db.scalars(select(RelationshipAssessment))
    }
    a_pair = assessments.get("DEMO-CASE-001|DEMO-CASE-002")
    if a_pair:
        review_assessment(db, a_pair.id, decision=AssessmentStatus.CONFIRMED,
                          rationale="Shared incident reference INC-2025-0042, compatible "
                          "incident dates and corroborating wage records; coordinating "
                          "disposal across RB and PGRC (synthetic demo decision).",
                          reviewer="reviewer")
    b_pair = assessments.get("DEMO-CASE-003|DEMO-CASE-004")
    if b_pair:
        review_assessment(db, b_pair.id, decision=AssessmentStatus.REJECTED,
                          rationale="Distinct incident references (INC-2025-0101 vs "
                          "INC-2025-0207) and incident dates months apart; incidents are "
                          "unrelated despite the shared institution (synthetic demo decision).",
                          reviewer="reviewer")

    # Lifecycle examples: acknowledge one cross-bureau alert and resolve
    # another, so the coordination centre shows all alert states immediately.
    xb_alerts = db.scalars(
        select(CoordinationAlert)
        .where(CoordinationAlert.alert_type == AlertType.CROSS_BUREAU_COORDINATION,
               CoordinationAlert.status == AlertStatus.OPEN)
        .order_by(CoordinationAlert.id)
    ).all()
    if xb_alerts:
        xb_alerts[0].status = AlertStatus.ACKNOWLEDGED
        xb_alerts[0].acknowledged_by = "admin"
        xb_alerts[0].acknowledged_at = now()
    if len(xb_alerts) > 1:
        xb_alerts[1].status = AlertStatus.RESOLVED
        xb_alerts[1].resolved_by = "admin"
        xb_alerts[1].resolved_at = now()
        xb_alerts[1].resolution_note = ("Officers conferred; cases confirmed to concern separate "
                                        "matters. Coordination note circulated (synthetic demo).")
    db.commit()

    return {
        "seeded": True,
        "institutions": len(INSTITUTIONS),
        "cases": 40,
        "bureaus": len(BUREAUS),
        "users": len(users),
        **match_result.model_dump(),
        **alert_result,
    }


def func_count(model):
    from sqlalchemy import func, select as _select

    return _select(func.count()).select_from(model)


def run_migrations() -> None:
    """Apply Alembic migrations (primary schema path)."""
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")


def main():
    parser = argparse.ArgumentParser(description="Seed INSTITRACE with synthetic demo data.")
    parser.add_argument("--reset", action="store_true",
                        help="DANGER: wipe all demo data and reseed from scratch.")
    args = parser.parse_args()
    try:
        run_migrations()
    except Exception as exc:  # pragma: no cover - fallback for unusual setups
        print(f"Warning: migrations could not run ({exc}); falling back to create_all")
        Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        result = seed_demo(db, reset=args.reset)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
