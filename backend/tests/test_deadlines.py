"""Deadline/overdue alert tests with an injected (pinned) clock."""
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app import clock
from app.models import (
    AlertStatus,
    AlertType,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
)
from app.services import alert_service

from .conftest import get_case_by_uid

TODAY = datetime(2026, 10, 29, 9, 0, 0)


def _alerts(db, alert_type):
    return db.scalars(select(CoordinationAlert).where(CoordinationAlert.alert_type == alert_type)).all()


def test_approaching_deadline_with_pinned_clock(db):
    clock.set_now(TODAY)
    # DEMO-CASE-013 was seeded ~2 days before its expected disposal relative
    # to seed day; re-anchor to the pinned date to make the test deterministic.
    case = get_case_by_uid(db, "DEMO-CASE-013")
    case.expected_disposal_date = TODAY.date() + timedelta(days=2)
    db.commit()

    alert_service.evaluate_alerts(db)
    matches = [
        a for a in _alerts(db, AlertType.APPROACHING_DEADLINE)
        if a.case_ids == ["DEMO-CASE-013"] and a.status != AlertStatus.RESOLVED
    ]
    assert matches, "expected an APPROACHING_DEADLINE alert"
    assert "prototype" in matches[0].description.lower() or "demo" in matches[0].description.lower()


def test_overdue_active_case(db):
    clock.set_now(TODAY)
    case = get_case_by_uid(db, "DEMO-CASE-012")
    case.expected_disposal_date = TODAY.date() - timedelta(days=10)
    db.commit()

    alert_service.evaluate_alerts(db)
    overdue = [a for a in _alerts(db, AlertType.OVERDUE)
               if a.case_ids == ["DEMO-CASE-012"] and a.status != AlertStatus.RESOLVED]
    assert overdue, "expected OVERDUE alert for active case past expected disposal"
    assert "10 day(s)" in overdue[0].description


def test_disposed_case_never_overdue(db):
    clock.set_now(TODAY)
    case = get_case_by_uid(db, "DEMO-CASE-014")  # DISPOSED with old deadline in seed
    assert case.status == CaseStatus.DISPOSED
    case.expected_disposal_date = TODAY.date() - timedelta(days=30)  # deadline passed long ago
    db.commit()

    alert_service.evaluate_alerts(db)
    for alert_type in (AlertType.OVERDUE, AlertType.APPROACHING_DEADLINE, AlertType.ESCALATION_REQUIRED):
        hits = [a for a in _alerts(db, alert_type)
                if a.case_ids == ["DEMO-CASE-014"] and a.status != AlertStatus.RESOLVED]
        assert hits == [], f"disposed case must not produce {alert_type.value} alerts"


def test_repeated_evaluation_no_duplicates(db):
    clock.set_now(TODAY)
    get_case_by_uid(db, "DEMO-CASE-012").expected_disposal_date = TODAY.date() - timedelta(days=10)
    db.commit()
    alert_service.evaluate_alerts(db)
    alert_service.evaluate_alerts(db)  # rerun
    r = alert_service.evaluate_alerts(db)
    assert r["alerts_created"] == 0
    # exactly one ACTIVE alert per condition-instance (earlier condition
    # instances may exist as RESOLVED history rows - that is by design)
    live = db.scalars(
        select(CoordinationAlert).where(
            CoordinationAlert.alert_type == AlertType.OVERDUE,
            CoordinationAlert.status != AlertStatus.RESOLVED,
            CoordinationAlert.dedupe_key.like("OVERDUE:DEMO-CASE-012:%"),
        )
    ).all()
    assert len(live) == 1, "exactly one live alert per condition-instance"
    assert live[0].dedupe_key == f"OVERDUE:DEMO-CASE-012:{(TODAY.date() - timedelta(days=10)).isoformat()}"


def test_deadline_change_creates_new_instance_and_auto_resolves_old(db):
    """Documented alert-instance semantics: moving a case's expected disposal
    date is a NEW condition instance - the stale alert auto-resolves and is
    not duplicated or reopened."""
    clock.set_now(TODAY)
    case = get_case_by_uid(db, "DEMO-CASE-022")  # seeded active with a deadline
    alert_service.evaluate_alerts(db)
    before = [
        a for a in db.scalars(
            select(CoordinationAlert).where(
                CoordinationAlert.institution_id == case.institution_id
            )
        )
        if case.case_id in (a.case_ids or [])
    ]
    old_keys = {a.dedupe_key for a in before}

    new_date = TODAY.date() + timedelta(days=2)
    case.expected_disposal_date = new_date
    db.commit()
    result = alert_service.evaluate_alerts(db)

    after = [
        a for a in db.scalars(
            select(CoordinationAlert).where(
                CoordinationAlert.institution_id == case.institution_id
            )
        )
        if case.case_id in (a.case_ids or [])
    ]
    new_keys = {a.dedupe_key for a in after}
    new_live = [a for a in after if a.status != AlertStatus.RESOLVED and a.dedupe_key not in old_keys]
    assert new_live, f"expected a new alert instance for the moved deadline (created={result['alerts_created']})"
    assert new_keys - old_keys, "dedupe key must change with the condition instance"



def test_disposal_auto_resolves_open_overdue_alert(db):
    clock.set_now(TODAY)
    case = get_case_by_uid(db, "DEMO-CASE-012")
    case.expected_disposal_date = TODAY.date() - timedelta(days=10)
    db.commit()
    alert_service.evaluate_alerts(db)

    # disposing the case must auto-resolve its operational alert on next run
    case.status = CaseStatus.DISPOSED
    case.actual_disposal_date = TODAY.date()
    db.commit()
    alert_service.evaluate_alerts(db)

    stale = [a for a in _alerts(db, AlertType.OVERDUE) if a.case_ids == ["DEMO-CASE-012"]]
    assert all(a.status == AlertStatus.RESOLVED for a in stale)

    # cleanup for other tests sharing the session db
    case.status = CaseStatus.UNDER_PROCESS
    case.actual_disposal_date = None
    db.commit()


def test_pending_reminder_for_overdue_next_action(db):
    clock.set_now(TODAY)
    case = get_case_by_uid(db, "DEMO-CASE-018")
    case.next_action = "Reminder to examination section"
    case.next_action_due_date = TODAY.date() - timedelta(days=3)
    db.commit()
    alert_service.evaluate_alerts(db)
    reminders = [a for a in _alerts(db, AlertType.PENDING_REMINDER)
                 if a.case_ids == ["DEMO-CASE-018"] and a.status != AlertStatus.RESOLVED]
    assert reminders
