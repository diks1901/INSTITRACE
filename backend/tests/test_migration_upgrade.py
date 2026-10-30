"""FIX 1 regression: upgrading a LEGACY database (revision 69e0eedb34ac) that
already contains coordination alerts must not crash or misbehave.

The upgraded evaluator needs alert_condition_state for historical keys;
a2b7c9d1e001 and b3c4d5e6f002 both apply an idempotent backfill. Without it,
the first recomputation hits:
  IntegrityError: UNIQUE constraint failed:
  coordination_alerts.logical_key, coordination_alerts.occurrence

These tests (1) build a legacy DB at the PREVIOUS migration, (2) insert
legacy cases + alerts in the old shape, (3) upgrade to head, (4) run real
alert recomputation, and (5) verify occurrence numbering + history. A
fresh-install path (empty DB -> upgrade head -> seed) is covered too.
"""
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import AlertStatus, AlertType, CoordinationAlert
from app.services import alert_service

BACKEND = Path(__file__).resolve().parent.parent

LEGACY_REVISION = "69e0eedb34ac"  # initial schema (pre occurrence lifecycle)


def _alembic_upgrade(db_url: str, revision: str):
    """Run `alembic upgrade` against an isolated database, programmatically."""
    from alembic import command
    from alembic.config import Config

    old_url = os.environ.get("INSTITRACE_DATABASE_URL")
    os.environ["INSTITRACE_DATABASE_URL"] = db_url
    get_settings.cache_clear()
    try:
        cfg = Config()
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(cfg, revision)
    finally:
        if old_url is not None:
            os.environ["INSTITRACE_DATABASE_URL"] = old_url
        get_settings.cache_clear()


def _session(db_url: str):
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _insert_legacy_rows(db, *, alert_status="RESOLVED", resolved_by="reviewer"):
    """Insert one institution, two bureaus, two active cases and one legacy
    coordination alert row in the 69e0eedb34ac column shape (no logical_key /
    occurrence columns yet)."""
    db.execute(text(
        "INSERT INTO institutions (permanent_id, name, address, region, state, is_demo,"
        " created_at, updated_at) VALUES ('PERM-LEG', 'Legacy Institute', 'addr', 'R', 'S', 1,"
        " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    ))
    db.execute(text(
        "INSERT INTO bureaus (code, name, active) VALUES ('RB', 'Regulation Bureau', 1)"
    ))
    db.execute(text(
        "INSERT INTO bureaus (code, name, active) VALUES ('PGRC', 'Grievance Cell', 1)"
    ))
    for uid, bid in (("LEG-A", 1), ("LEG-B", 2)):
        db.execute(text(
            "INSERT INTO complaint_cases (case_id, institution_id, receipt_date, category,"
            " subject, description, status, bureau_id, officer_name, priority,"
            " created_at, updated_at)"
            f" VALUES ('{uid}', 1, DATE('now'), 'Fee Refund', 'Legacy case {uid}',"
            " 'Legacy description text.', 'UNDER_PROCESS', :bid, 'Legacy Officer', 'MEDIUM',"
            " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ), {"bid": bid})
    db.execute(text(
        "INSERT INTO coordination_alerts (alert_type, institution_id, case_ids, title,"
        " description, dedupe_key, status, resolved_by, resolved_at, created_at)"
        " VALUES ('CROSS_BUREAU_COORDINATION', 1, '[\"LEG-A\", \"LEG-B\"]',"
        " 'Legacy XB alert', 'Legacy description.', 'XBUREAU:1:LEG-A,LEG-B',"
        f" '{alert_status}', :rb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    ), {"rb": resolved_by})
    db.commit()


@pytest.fixture()
def legacy_db(tmp_path):
    """A legacy database at the initial migration with one RESOLVED XB alert."""
    url = f"sqlite:///{tmp_path}/legacy.db"
    _alembic_upgrade(url, LEGACY_REVISION)
    db = _session(url)
    yield db, url
    db.close()


def alerts_for(db, logical_key):
    from sqlalchemy import select

    return db.scalars(
        select(CoordinationAlert)
        .where(CoordinationAlert.logical_key == logical_key)
        .order_by(CoordinationAlert.occurrence)
    ).all()


def test_upgrade_with_resolved_alert_then_recompute_no_integrity_error(legacy_db):
    """The exact reported defect: legacy resolved alert + recurring condition
    must NOT raise UNIQUE(violation) and must open occurrence 2."""
    db, url = legacy_db
    _insert_legacy_rows(db)
    db.close()

    _alembic_upgrade(url, "head")

    db = _session(url)
    # state backfilled from history
    row = db.execute(text("SELECT present, occurrences FROM alert_condition_state"
                          " WHERE logical_key='XBUREAU:1:LEG-A,LEG-B'")).one()
    assert row.occurrences == 1, "max historical occurrence preserved"

    result = alert_service.evaluate_alerts(db)  # must not raise IntegrityError
    assert result["alerts_created"] == 1
    alerts = alerts_for(db, "XBUREAU:1:LEG-A,LEG-B")
    assert len(alerts) == 2
    assert alerts[0].occurrence == 1
    assert alerts[0].status == AlertStatus.RESOLVED, "historical record preserved untouched"
    assert alerts[0].resolved_by == "reviewer"
    assert alerts[1].occurrence == 2, "returning condition opens the NEXT occurrence"
    assert alerts[1].status == AlertStatus.OPEN

    # repeated evaluation must never duplicate the active alert
    again = alert_service.evaluate_alerts(db)
    assert again["alerts_created"] == 0
    assert len(alerts_for(db, "XBUREAU:1:LEG-A,LEG-B")) == 2


def test_upgrade_with_active_legacy_alert_is_reused_not_duplicated(tmp_path):
    url = f"sqlite:///{tmp_path}/legacy_active.db"
    _alembic_upgrade(url, LEGACY_REVISION)
    db = _session(url)
    _insert_legacy_rows(db, alert_status="ACKNOWLEDGED", resolved_by=None)
    db.close()

    _alembic_upgrade(url, "head")
    db = _session(url)
    # backfill marks the key present so the evaluator reuses the active row
    state = db.execute(text("SELECT present, occurrences FROM alert_condition_state"
                            " WHERE logical_key='XBUREAU:1:LEG-A,LEG-B'")).one()
    assert state.present == 1

    result = alert_service.evaluate_alerts(db)
    assert result["alerts_created"] == 0
    alerts = alerts_for(db, "XBUREAU:1:LEG-A,LEG-B")
    assert len(alerts) == 1
    assert alerts[0].status == AlertStatus.ACKNOWLEDGED  # pre-upgrade state untouched


def test_upgrade_legacy_system_auto_resolved_alert_recurrence(tmp_path):
    """Legacy row resolved by 'system (auto)' + returning condition -> occ 2."""
    url = f"sqlite:///{tmp_path}/legacy_sysauto.db"
    _alembic_upgrade(url, LEGACY_REVISION)
    db = _session(url)
    _insert_legacy_rows(db, alert_status="RESOLVED", resolved_by="system (auto)")
    db.close()
    _alembic_upgrade(url, "head")

    db = _session(url)
    alert_service.evaluate_alerts(db)
    alerts = alerts_for(db, "XBUREAU:1:LEG-A,LEG-B")
    assert len(alerts) == 2 and alerts[1].occurrence == 2


def test_fresh_install_upgrade_head_and_seed(tmp_path):
    """Fresh installation path: empty DB -> upgrade head -> seed -> stable."""
    url = f"sqlite:///{tmp_path}/fresh.db"
    _alembic_upgrade(url, "head")
    db = _session(url)
    from app.seed import seed_demo

    result = seed_demo(db, reset=False)
    assert result["seeded"] is True

    # double evaluation after seed must create nothing new
    r1 = alert_service.evaluate_alerts(db)
    assert r1["alerts_created"] == 0 and r1["alerts_auto_resolved"] == 0

    # all alerts are first occurrences with backfilled/tracked state present
    rows = db.scalars(text_to_select_all(CoordinationAlert)).all()
    assert rows and all(a.occurrence == 1 for a in rows)

    # the seeded human decisions produced review-history rows (FIX 2)
    n_reviews = db.execute(text("SELECT COUNT(*) FROM relationship_reviews")).scalar()
    assert n_reviews == 2, "seeded CONFIRMED + REJECTED decisions must be in history"

    # alembic head reached (read the chain tail from the migration files
    # instead of hardcoding, so later revisions do not break this test)
    import glob, re

    heads = [Path(p).stem.split("_")[0] for p in glob.glob(str(BACKEND / "alembic/versions/*.py"))]
    versions = set()
    downs = set()
    for p in glob.glob(str(BACKEND / "alembic/versions/*.py")):
        src = Path(p).read_text()
        m1 = re.search(r'^revision: str = "([a-f0-9]+)"', src, re.M)
        m2 = re.search(r'^down_revision: Union\[str, None\] = "([a-f0-9]+)"', src, re.M)
        if m1:
            versions.add(m1.group(1))
        if m2:
            downs.add(m2.group(1))
    expected_head = next(iter(versions - downs))
    head = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert head == expected_head
    db.close()


def text_to_select_all(model):
    from sqlalchemy import select

    return select(model)
