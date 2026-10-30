"""FIX 1 regression: alert occurrence lifecycle.

When a condition that previously produced an alert disappears (evaluated
absent), the alert auto-resolves ("system (auto)"). If the condition later
RECURS, a brand-new ACTIVE alert occurrence must be created - the resolved
row stays as history, and repeated recomputation must never duplicate the
active occurrence. Covered for coordination alerts AND deadline alerts.

A human who resolves an alert while the condition is still active explicitly
suppresses respawning for as long as the condition keeps being active.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app import clock
from app.models import (
    AlertConditionState,
    AlertStatus,
    AlertType,
    Bureau,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
    Institution,
    Priority,
)
from app.services import alert_service


def _make_case(db, uid, institution_id, bureau_id, **kw):
    c = ComplaintCase(
        case_id=uid,
        institution_id=institution_id,
        bureau_id=bureau_id,
        receipt_date=date(2026, 1, 5),
        category="Fee Refund",
        subject=f"Synthetic lifecycle probe {uid}",
        description="Synthetic test case; not real data.",
        status=CaseStatus.UNDER_PROCESS,
        priority=Priority.MEDIUM,
        **kw,
    )
    db.add(c)
    db.commit()
    return c


@pytest.fixture()
def probe_institution(db):
    inst = Institution(
        permanent_id="PERM-LIFE-PROBE", name="Lifecycle Probe Institution",
        address="Synthetic", region="TEST", state="TEST", district="TEST",
        institution_type="Synthetic", is_demo=True,
    )
    db.add(inst)
    db.flush()
    rb = db.scalar(select(Bureau).where(Bureau.code == "RB"))
    pgrc = db.scalar(select(Bureau).where(Bureau.code == "PGRC"))
    yield inst, rb, pgrc
    # cleanup: remove everything the probe created so other tests see the
    # pristine seeded dataset.
    for case in db.scalars(
        select(ComplaintCase).where(ComplaintCase.institution_id == inst.id)
    ).all():
        db.delete(case)
    for alert in db.scalars(
        select(CoordinationAlert).where(CoordinationAlert.institution_id == inst.id)
    ).all():
        db.delete(alert)
    db.flush()
    db.delete(inst)
    db.commit()


def _alerts_for(db, logical_key):
    return db.scalars(
        select(CoordinationAlert)
        .where(CoordinationAlert.logical_key == logical_key)
        .order_by(CoordinationAlert.occurrence)
    ).all()


def test_coordination_alert_recurrence_creates_new_occurrence(db, probe_institution):
    inst, rb, pgrc = probe_institution
    a = _make_case(db, "LIFE-XB-1", inst.id, rb.id)
    b = _make_case(db, "LIFE-XB-2", inst.id, pgrc.id)
    logical_key = f"XBUREAU:{inst.id}:LIFE-XB-1,LIFE-XB-2"

    # 1. condition present -> one active occurrence 1
    alert_service.evaluate_alerts(db)
    alerts = _alerts_for(db, logical_key)
    assert len(alerts) == 1
    assert alerts[0].occurrence == 1
    assert alerts[0].status in (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED)

    # 2. condition disappears (both cases disposed)
    a.status = CaseStatus.DISPOSED
    b.status = CaseStatus.DISPOSED
    db.commit()

    # 3. recompute -> system (auto) resolves it
    alert_service.evaluate_alerts(db)
    alerts = _alerts_for(db, logical_key)
    assert len(alerts) == 1
    assert alerts[0].status == AlertStatus.RESOLVED
    assert alerts[0].resolved_by == "system (auto)"

    # 4. condition returns
    a.status = CaseStatus.UNDER_PROCESS
    b.status = CaseStatus.UNDER_PROCESS
    db.commit()

    # 5. recompute -> a NEW active alert (occurrence 2) appears; history intact
    alert_service.evaluate_alerts(db)
    alerts = _alerts_for(db, logical_key)
    assert len(alerts) == 2, "expected occurrence 2 along preserved occurrence 1"
    first, second = alerts
    assert first.status == AlertStatus.RESOLVED
    assert second.occurrence == 2
    assert second.status == AlertStatus.OPEN
    assert second.title == first.title
    assert second.created_at >= first.created_at

    # 6. recompute again -> still exactly one active alert, NO duplicate
    alert_service.evaluate_alerts(db)
    alerts = _alerts_for(db, logical_key)
    assert len(alerts) == 2
    active = [x for x in alerts if x.status != AlertStatus.RESOLVED]
    assert len(active) == 1

    # 7. earlier evaluation runs recorded the condition state
    state = db.get(AlertConditionState, logical_key)
    assert state is not None
    assert state.present is True
    assert state.occurrences == 2


def test_deadline_alert_recurrence_creates_new_occurrence(db, probe_institution):
    inst, rb, _ = probe_institution
    today = date.today()
    exp = today - timedelta(days=5)
    case = _make_case(db, "LIFE-DL-1", inst.id, rb.id, expected_disposal_date=exp)
    logical_key = f"OVERDUE:LIFE-DL-1:{exp.isoformat()}"

    clock.set_now(datetime_now(today))
    try:
        # 1. overdue while active -> active alert occurrence 1
        alert_service.evaluate_alerts(db)
        alerts = [
            x for x in _alerts_for(db, logical_key)
        ]
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.OVERDUE
        assert alerts[0].status != AlertStatus.RESOLVED

        # 2. case disposed -> condition gone
        case.status = CaseStatus.DISPOSED
        db.commit()

        # 3. recompute -> auto-resolved, also resolve handled by system
        alert_service.evaluate_alerts(db)
        assert _alerts_for(db, logical_key)[0].status == AlertStatus.RESOLVED

        # 4. case reactivated (disposal withdrawn) -> condition back
        case.status = CaseStatus.UNDER_PROCESS
        db.commit()

        # 5. recompute -> NEW alert occurrence 2; history intact
        alert_service.evaluate_alerts(db)
        alerts = _alerts_for(db, logical_key)
        assert len(alerts) == 2
        assert alerts[0].status == AlertStatus.RESOLVED
        assert alerts[1].occurrence == 2 and alerts[1].status == AlertStatus.OPEN

        # 6. recompute again -> no duplicate active alert
        alert_service.evaluate_alerts(db)
        alerts = _alerts_for(db, logical_key)
        assert len(alerts) == 2
        assert sum(1 for x in alerts if x.status != AlertStatus.RESOLVED) == 1
    finally:
        clock.set_now(None)


def test_human_resolved_active_condition_does_not_respawn(db, probe_institution):
    """Documented safeguard: if a human RESOLVES an alert while the condition
    is still active, the system must not silently respawn it every recompute.
    A new occurrence is opened only after the condition was observed absent."""
    inst, rb, pgrc = probe_institution
    a = _make_case(db, "LIFE-HR-1", inst.id, rb.id)
    b = _make_case(db, "LIFE-HR-2", inst.id, pgrc.id)
    logical_key = f"XBUREAU:{inst.id}:LIFE-HR-1,LIFE-HR-2"

    alert_service.evaluate_alerts(db)
    alert = _alerts_for(db, logical_key)[0]
    # human resolves it while the condition is still active
    alert.status = AlertStatus.RESOLVED
    alert.resolved_by = "reviewer"
    alert.resolution_note = "coordination completed"
    db.commit()

    # recompute with the condition still active -> no respawn
    alert_service.evaluate_alerts(db)
    alerts = _alerts_for(db, logical_key)
    assert len(alerts) == 1

    # condition goes absent and returns -> now a new occurrence is expected
    a.status = CaseStatus.DISPOSED
    b.status = CaseStatus.DISPOSED
    db.commit()
    alert_service.evaluate_alerts(db)  # record absence
    a.status = CaseStatus.UNDER_PROCESS
    b.status = CaseStatus.UNDER_PROCESS
    db.commit()
    alert_service.evaluate_alerts(db)
    alerts = _alerts_for(db, logical_key)
    assert len(alerts) == 2
    assert alerts[1].occurrence == 2
    assert alerts[1].status == AlertStatus.OPEN


def datetime_now(d: date):
    from datetime import datetime, timezone

    return datetime(d.year, d.month, d.day, 9, 0, tzinfo=timezone.utc)
