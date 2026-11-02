"""Test fixtures: an isolated SQLite database seeded with the deterministic
synthetic demo dataset, plus authenticated test clients per role."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

# The test database defaults to a throwaway SQLite file. Set
# INSTITRACE_TEST_DATABASE_URL to run the SAME suite against PostgreSQL
# (e.g. postgresql+psycopg2://postgres@/institrace_test?host=/tmp/itpg).
_tmp = tempfile.mkdtemp(prefix="institrace-test-")
_TEST_DB_URL = os.environ.get(
    "INSTITRACE_TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db"
)
os.environ["INSTITRACE_DATABASE_URL"] = _TEST_DB_URL
os.environ["INSTITRACE_SECRET_KEY"] = "test-secret"
os.environ["INSTITRACE_DEADLINE_WARNING_DAYS"] = "3"
os.environ["INSTITRACE_ESCALATION_OVERDUE_DAYS"] = "7"

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import clock
from app.database import Base, get_db
from app.main import app
from app.models import (
    AlertStatus,
    AlertType,
    AssessmentStatus,
    Bureau,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
    Institution,
    RelationshipAssessment,
    RelationshipType,
    TransferRecord,
)
from app.seed import seed_demo

from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def db_engine():
    kwargs = {}
    if _TEST_DB_URL.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(_TEST_DB_URL, **kwargs)

    if _TEST_DB_URL.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    seed_demo(session, reset=False)
    session.close()
    yield engine


@pytest.fixture()
def db(db_engine):
    TestingSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client(db_engine):
    TestingSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def tokens(db_engine):
    TestingSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    out = {}
    with TestClient(app) as c:
        for username, password in (
            ("admin", "InstiTrace#Demo1"),
            ("officer.rb", "Officer#Demo1"),
            ("reviewer", "Reviewer#Demo1"),
            ("manager", "Manager#Demo1"),
        ):
            resp = c.post("/api/v1/auth/login", json={"username": username, "password": password})
            assert resp.status_code == 200, resp.text
            out[username] = {"Authorization": f"Bearer {resp.json()['token']}"}
    app.dependency_overrides.clear()
    return out


@pytest.fixture(autouse=True)
def _reset_clock():
    yield
    clock.set_now(None)


# ---------------------------------------------------------------- helpers ---
def get_case_by_uid(db, uid: str) -> ComplaintCase:
    from sqlalchemy import select

    return db.scalar(select(ComplaintCase).where(ComplaintCase.case_id == uid))


def pair(db, uid_a: str, uid_b: str) -> RelationshipAssessment:
    from sqlalchemy import select

    a, b = sorted([uid_a, uid_b])
    return db.scalar(select(RelationshipAssessment).where(RelationshipAssessment.pair_key == f"{a}|{b}"))


__all__ = ["get_case_by_uid", "pair"]
