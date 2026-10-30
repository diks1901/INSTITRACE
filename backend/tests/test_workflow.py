"""Case workflow tests: creation, transitions, transfer, escalation, review,
history and audit integrity."""
from sqlalchemy import func, select

from app.models import (
    AuditEvent,
    CaseAction,
    CaseStatus,
    ComplaintCase,
    TransferRecord,
)

from .conftest import get_case_by_uid


def _pk(client, headers, uid):
    resp = client.get(f"/api/v1/cases?q={uid}", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    return next(i["id"] for i in items if i["case_id"] == uid)


def test_case_creation_and_initial_history(client, tokens, db):
    resp = client.post("/api/v1/cases", headers=tokens["admin"], json={
        "case_id": "DEMO-CASE-900",
        "institution_id": 1,
        "receipt_date": "2026-10-20",
        "category": "Fees & Refund",
        "subject": "Synthetic test case for fee refund",
        "description": "Created by pytest.",
        "bureau_id": 1,
        "officer_name": "Demo Officer R. Verma",
        "priority": "MEDIUM",
        "expected_disposal_date": "2026-11-15",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "PENDING"
    hist = client.get(f"/api/v1/cases/{body['id']}/history", headers=tokens["admin"]).json()
    assert any(h["action_type"] == "CREATED" for h in hist)
    audit = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == "DEMO-CASE-900",
                                               AuditEvent.event_type == "CASE_CREATED"))
    assert audit is not None


def test_duplicate_case_id_rejected(client, tokens):
    resp = client.post("/api/v1/cases", headers=tokens["admin"], json={
        "case_id": "DEMO-CASE-001", "institution_id": 1, "receipt_date": "2026-10-20",
        "category": "Others", "subject": "duplicate id attempt", "bureau_id": 1,
    })
    assert resp.status_code == 409
    assert "error" in resp.json()


def test_duplicate_institution_permanent_id_rejected(client, tokens):
    resp = client.post("/api/v1/institutions", headers=tokens["admin"], json={
        "permanent_id": "DEMO-INS-001", "name": "Duplicate Institution",
        "region": "Northern", "state": "Delhi",
    })
    assert resp.status_code == 409


def test_status_change_history_and_invalid_transition(client, tokens):
    pk = _pk(client, tokens["admin"], "DEMO-CASE-036")
    ok = client.post(f"/api/v1/cases/{pk}/status", headers=tokens["admin"], json={
        "to_status": "UNDER_PROCESS", "summary": "Scrutiny started",
    })
    assert ok.status_code == 200
    assert ok.json()["status"] == "UNDER_PROCESS"

    # now UNDER_PROCESS -> PENDING is invalid
    bad = client.post(f"/api/v1/cases/{pk}/status", headers=tokens["admin"], json={
        "to_status": "PENDING", "summary": "Try to go back",
    })
    assert bad.status_code == 422
    assert "Invalid status transition" in bad.json()["error"]["message"]

    hist = client.get(f"/api/v1/cases/{pk}/history", headers=tokens["admin"]).json()
    status_events = [h for h in hist if h["action_type"] == "STATUS_CHANGE"]
    assert any(h["to_status"] == "UNDER_PROCESS" for h in status_events)


def test_disposed_is_terminal(client, tokens):
    pk = _pk(client, tokens["admin"], "DEMO-CASE-014")  # seeded DISPOSED
    resp = client.post(f"/api/v1/cases/{pk}/status", headers=tokens["admin"], json={
        "to_status": "UNDER_PROCESS", "summary": "reopen attempt",
    })
    assert resp.status_code == 422


def test_transfer_preserves_history_and_audit(client, tokens, db):
    pk = _pk(client, tokens["admin"], "DEMO-CASE-034")
    case_before = get_case_by_uid(db, "DEMO-CASE-034")
    old_bureau = case_before.bureau_id
    target_bureau = 3 if old_bureau != 3 else 1

    resp = client.post(f"/api/v1/cases/{pk}/transfer", headers=tokens["officer.rb"], json={
        "to_bureau_id": target_bureau,
        "to_officer_name": "Demo Officer E. Rao",
        "reason": "Domain reassignment during pytest",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "TRANSFERRED", "transfer must not dispose the case"
    assert body["bureau_id"] == target_bureau

    db.expire_all()
    transfers = db.scalars(select(TransferRecord).where(TransferRecord.case_id == pk)).all()
    assert len(transfers) >= 1
    assert any(t.from_bureau_id == old_bureau and t.to_bureau_id == target_bureau
               for t in transfers)
    audit = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == "DEMO-CASE-034",
                                                AuditEvent.event_type == "CASE_TRANSFERRED")).all()
    assert audit, "transfer must create an audit event"
    hist = client.get(f"/api/v1/cases/{pk}/history", headers=tokens["admin"]).json()
    assert any(h["action_type"] == "TRANSFER" for h in hist)


def test_transfer_disposed_case_rejected(client, tokens):
    pk = _pk(client, tokens["admin"], "DEMO-CASE-014")
    resp = client.post(f"/api/v1/cases/{pk}/transfer", headers=tokens["admin"], json={
        "to_bureau_id": 2, "to_officer_name": "Demo Officer P. Nair", "reason": "should fail",
    })
    assert resp.status_code == 422


def test_escalation_recorded(client, tokens, db):
    pk = _pk(client, tokens["admin"], "DEMO-CASE-026")
    resp = client.post(f"/api/v1/cases/{pk}/escalate", headers=tokens["admin"], json={
        "reason": "No progress despite reminders (pytest)",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ESCALATED"
    hist = client.get(f"/api/v1/cases/{pk}/history", headers=tokens["admin"]).json()
    assert any(h["action_type"] == "STATUS_CHANGE" and h["to_status"] == "ESCALATED"
               for h in hist)


def test_review_decision_persists_with_rationale(client, tokens):
    resp = client.get("/api/v1/relationships?status=PENDING_REVIEW&relationship_type=POTENTIAL_SAME_INCIDENT",
                      headers=tokens["reviewer"])
    assert resp.status_code == 200
    pending = resp.json()["items"]
    assert pending, "expected at least one pending same-incident assessment"
    target = pending[0]
    review = client.post(f"/api/v1/relationships/{target['id']}/review",
                         headers=tokens["reviewer"],
                         json={"decision": "DEFERRED",
                               "rationale": "Need the original complainant statements before deciding."})
    assert review.status_code == 200
    body = review.json()
    assert body["status"] == "DEFERRED"
    assert body["reviewer_identity"] == "reviewer"
    assert body["reviewer_rationale"].startswith("Need the original")

    again = client.get(f"/api/v1/relationships/{target['id']}", headers=tokens["admin"])
    assert again.json()["status"] == "DEFERRED"


def test_review_validation_rejects_invalid_decision(client, tokens):
    resp = client.get("/api/v1/relationships?status=PENDING_REVIEW", headers=tokens["reviewer"])
    target = resp.json()["items"][0]
    bad = client.post(f"/api/v1/relationships/{target['id']}/review",
                      headers=tokens["reviewer"],
                      json={"decision": "PENDING_REVIEW", "rationale": "not a decision"})
    assert bad.status_code == 422


def test_resolved_alerts_remain_traceable(client, tokens):
    resp = client.get("/api/v1/alerts?status=RESOLVED", headers=tokens["admin"])
    assert resp.json()["total"] >= 1
    first = resp.json()["items"][0]
    detail = client.get(f"/api/v1/alerts/{first['id']}", headers=tokens["admin"])
    assert detail.status_code == 200
    assert detail.json()["resolved_by"] is not None


def test_role_enforcement(client, tokens):
    """READ_ONLY_MANAGER cannot mutate; REVIEWER cannot create cases."""
    ro_create = client.post("/api/v1/cases", headers=tokens["manager"], json={
        "case_id": "DEMO-CASE-901", "institution_id": 1, "receipt_date": "2026-10-20",
        "category": "Others", "subject": "should be forbidden", "bureau_id": 1,
    })
    assert ro_create.status_code == 403

    resp = client.get("/api/v1/relationships?status=PENDING_REVIEW", headers=tokens["reviewer"])
    target = resp.json()["items"][0]
    officer_review = client.post(f"/api/v1/relationships/{target['id']}/review",
                                 headers=tokens["officer.rb"],
                                 json={"decision": "CONFIRMED", "rationale": "officer should not review"})
    assert officer_review.status_code == 403

    no_auth = client.get("/api/v1/cases")
    assert no_auth.status_code == 401


def test_case_filters(client, tokens):
    resp = client.get("/api/v1/cases?status=ESCALATED", headers=tokens["admin"])
    assert all(i["status"] == "ESCALATED" for i in resp.json()["items"])
    resp = client.get("/api/v1/cases?region=Southern", headers=tokens["admin"])
    assert resp.json()["total"] >= 2
    resp = client.get("/api/v1/cases?overdue=true", headers=tokens["admin"])
    items = resp.json()["items"]
    assert items, "expected overdue cases"
    assert all(i["status"] != "DISPOSED" for i in items)
