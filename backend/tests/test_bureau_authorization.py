"""Bureau-level (record-level) authorization for BUREAU_OFFICER accounts.

Design under test (mandate Part A):
- ADMIN: global operational access.
- BUREAU_OFFICER (assigned bureau): list/detail/mutations ONLY inside own
  bureau; cannot register into or spoof another bureau; can initiate a
  transfer from own bureau, afterwards ownership follows the receiving bureau.
- REVIEWER: relationship reviews across bureaus; no case operations.
- READ_ONLY_MANAGER: read-only everywhere; audit access intact.
- Cross-bureau coordination indicators (alerts/assessments/institution
  summaries) stay visible to officers — that visibility is INSTITRACE's point.
All tests run against the disposable session-scoped test database.
"""
from sqlalchemy import select

from .conftest import get_case_by_uid  # noqa: F401  (shared helper)
from app.models import AuditEvent, TransferRecord


def _pk(client, headers, uid: str) -> int:
    resp = client.get("/api/v1/cases", params={"q": uid}, headers=headers)
    items = resp.json()["items"]
    assert items and items[0]["case_id"] == uid
    return items[0]["id"]


def test_officer_assignment_loads_from_seed(db):
    from app.models import DemoUser, Bureau
    user = db.scalar(select(DemoUser).where(DemoUser.username == "officer.rb"))
    assert user is not None and user.bureau_id is not None, "officer.rb must have a bureau"
    rb = db.scalar(select(Bureau).where(Bureau.code == "RB"))
    assert user.bureau_id == rb.id


# --- officer scoping ---------------------------------------------------------
def test_officer_lists_only_own_bureau_cases(client, tokens):
    mine = client.get("/api/v1/cases", params={"page_size": 200}, headers=tokens["officer.rb"])
    assert mine.status_code == 200
    bureaus = {i["bureau_id"] for i in mine.json()["items"]}
    assert bureaus == {1}, f"officer list must contain RB only, got {bureaus}"


def test_officer_cannot_spoof_bureau_in_list_filter(client, tokens):
    resp = client.get("/api/v1/cases", params={"bureau_id": 2}, headers=tokens["officer.rb"])
    assert resp.status_code == 403
    # filtering by own bureau explicitly is fine
    ok = client.get("/api/v1/cases", params={"bureau_id": 1}, headers=tokens["officer.rb"])
    assert ok.status_code == 200


def test_officer_cannot_open_foreign_case_detail(client, tokens):
    pgrc_pk = _pk(client, tokens["admin"], "DEMO-CASE-002")  # PGRC case
    assert client.get(f"/api/v1/cases/{pgrc_pk}", headers=tokens["officer.rb"]).status_code == 403
    assert client.get(f"/api/v1/cases/{pgrc_pk}/history", headers=tokens["officer.rb"]).status_code == 403
    evc_pk = _pk(client, tokens["admin"], "DEMO-CASE-007") if False else None
    # EVC check via list-backed pk (some EVC case ids exist in seed)
    items = client.get("/api/v1/cases", params={"bureau_id": 3, "page_size": 1}, headers=tokens["admin"]).json()["items"]
    if items:
        pk = items[0]["id"]
        assert client.get(f"/api/v1/cases/{pk}", headers=tokens["officer.rb"]).status_code == 403


def test_officer_can_open_own_case_detail(client, tokens):
    pk = _pk(client, tokens["admin"], "DEMO-CASE-001")  # RB case
    resp = client.get(f"/api/v1/cases/{pk}", headers=tokens["officer.rb"])
    assert resp.status_code == 200
    assert resp.json()["case"]["case_id"] == "DEMO-CASE-001"


def test_officer_cannot_mutate_foreign_case(client, tokens):
    pgrc_pk = _pk(client, tokens["admin"], "DEMO-CASE-002")
    probes = {
        "PATCH": client.patch(f"/api/v1/cases/{pgrc_pk}", headers=tokens["officer.rb"],
                              json={"subject": "spoof attempt"}),
        "ACTION": client.post(f"/api/v1/cases/{pgrc_pk}/actions", headers=tokens["officer.rb"],
                              json={"action_type": "NOTE", "summary": "spoof attempt"}),
        "STATUS": client.post(f"/api/v1/cases/{pgrc_pk}/status", headers=tokens["officer.rb"],
                              json={"to_status": "UNDER_PROCESS", "summary": "spoof"}),
        "ASSIGN": client.post(f"/api/v1/cases/{pgrc_pk}/assign", headers=tokens["officer.rb"],
                              json={"officer_name": "Spoof Officer", "summary": "spoof attempt"}),
        "NEXT_ACTION": client.post(f"/api/v1/cases/{pgrc_pk}/next-action", headers=tokens["officer.rb"],
                                   json={"next_action": "spoof attempt"}),
        "ESCALATE": client.post(f"/api/v1/cases/{pgrc_pk}/escalate", headers=tokens["officer.rb"],
                                json={"reason": "spoof attempt probe"}),
        "TRANSFER": client.post(f"/api/v1/cases/{pgrc_pk}/transfer", headers=tokens["officer.rb"],
                                json={"to_bureau_id": 1, "to_officer_name": "Spoof Officer", "reason": "spoof attempt"}),
    }
    for name, r in probes.items():
        assert r.status_code == 403, f"{name} must be 403 for foreign-bureau case, got {r.status_code}"


def test_officer_can_mutate_own_case_with_audit(client, tokens, db):
    pk = _pk(client, tokens["admin"], "DEMO-CASE-012")  # RB case per seed
    payload = {"action_type": "FOLLOW_UP", "summary": "pytest: officer remark inside own bureau"}
    resp = client.post(f"/api/v1/cases/{pk}/actions", headers=tokens["officer.rb"], json=payload)
    assert resp.status_code == 201, resp.text
    audits = db.scalars(
        select(AuditEvent).where(AuditEvent.event_type == "CASE_ACTION_ADDED",
                                 AuditEvent.actor == "officer.rb")
    ).all()
    assert audits, "permitted operation must be audited"


def test_officer_cannot_register_into_foreign_bureau(client, tokens):
    resp = client.post("/api/v1/cases", headers=tokens["officer.rb"], json={
        "case_id": "DEMO-CASE-991", "institution_id": 1, "receipt_date": "2026-10-31",
        "category": "Others", "subject": "spoof bureau create", "bureau_id": 2,
    })
    assert resp.status_code == 403


def test_officer_transfer_out_of_own_bureau_changes_ownership(client, tokens, db):
    pk = _pk(client, tokens["admin"], "DEMO-CASE-035")  # RB case
    resp = client.post(f"/api/v1/cases/{pk}/transfer", headers=tokens["officer.rb"], json={
        "to_bureau_id": 3, "to_officer_name": "Demo Officer E. Rao",
        "reason": "scoped-transfer regression (pytest)",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["bureau_id"] == 3, "ownership moves to the receiving bureau"
    # after transfer, the RB officer no longer operates on it
    again = client.patch(f"/api/v1/cases/{pk}", headers=tokens["officer.rb"],
                         json={"subject": "should be denied after transfer"})
    assert again.status_code == 403
    # history preserved
    transfers = db.scalars(select(TransferRecord).where(TransferRecord.case_id == pk)).all()
    assert any(t.from_bureau_id == 1 and t.to_bureau_id == 3 for t in transfers)


def test_officer_keeps_cross_bureau_coordination_visibility(client, tokens):
    """Coordination indicators (alerts list / assessments) remain readable."""
    alerts = client.get("/api/v1/alerts", headers=tokens["officer.rb"])
    assert alerts.status_code == 200 and alerts.json()["total"] > 0
    rel = client.get("/api/v1/relationships", headers=tokens["officer.rb"])
    assert rel.status_code == 200 and rel.json()["total"] > 0
    inst = client.get("/api/v1/institutions/1", headers=tokens["officer.rb"])
    assert inst.status_code == 200
    body = inst.json()
    assert body["summary"]["total_cases"] >= 2, "institution summary stays global"
    assert body["visible_case_scope"] == "own_bureau"
    assert {c["bureau_id"] for c in body["cases"]} <= {1}, "embedded case payloads are scoped"


def test_officer_cannot_act_on_foreign_alert(client, tokens, db):
    # Find an OPEN alert involving only PGRC cases (no RB case)
    from app.models import CoordinationAlert, AlertStatus, ComplaintCase
    alerts = db.scalars(select(CoordinationAlert).where(CoordinationAlert.status == AlertStatus.OPEN)).all()
    target = None
    for a in alerts:
        ids = a.case_ids or []
        bureaus = {c.bureau_id for c in db.scalars(
            select(ComplaintCase).where(ComplaintCase.case_id.in_(ids))).all()} if ids else set()
        if bureaus and 1 not in bureaus:
            target = a
            break
    if target is not None:
        r = client.post(f"/api/v1/alerts/{target.id}/acknowledge", headers=tokens["officer.rb"],
                        json={"note": "attempt"})
        assert r.status_code == 403
    # Admin can always act; acknowledging any OPEN alert as admin works
    any_open = alerts[0]
    r_admin = client.post(f"/api/v1/alerts/{any_open.id}/acknowledge", headers=tokens["admin"],
                          json={"note": "admin ack ok"})
    assert r_admin.status_code in (200, 422)  # 422 only if its state pre-moved by another test


# --- other roles intact -------------------------------------------------------
def test_admin_retains_global_case_access(client, tokens):
    pgrc_pk = _pk(client, tokens["admin"], "DEMO-CASE-002")
    assert client.get(f"/api/v1/cases/{pgrc_pk}", headers=tokens["admin"]).status_code == 200
    resp = client.patch(f"/api/v1/cases/{pgrc_pk}", headers=tokens["admin"],
                        json={"next_action": "admin global check (pytest)"})
    assert resp.status_code == 200


def test_reviewer_reviews_but_cannot_operate_cases(client, tokens):
    pending = client.get("/api/v1/relationships",
                         params={"status": "PENDING_REVIEW"}, headers=tokens["reviewer"])
    items = pending.json()["items"]
    if items:
        pk = items[0]["id"]
        r = client.post(f"/api/v1/relationships/{pk}/review", headers=tokens["reviewer"],
                        json={"decision": "DEFERRED", "rationale": "pytest scoped-authz probe defer"})
        assert r.status_code == 200
    pgrc_pk = _pk(client, tokens["admin"], "DEMO-CASE-002")
    assert client.patch(f"/api/v1/cases/{pgrc_pk}", headers=tokens["reviewer"],
                        json={"subject": "no"}).status_code == 403


def test_manager_readonly_with_audit_access(client, tokens):
    assert client.get("/api/v1/cases", headers=tokens["manager"]).status_code == 200
    assert client.get("/api/v1/audit-events", headers=tokens["manager"]).status_code == 200
    pk = _pk(client, tokens["admin"], "DEMO-CASE-012")
    assert client.patch(f"/api/v1/cases/{pk}", headers=tokens["manager"],
                        json={"subject": "no"}).status_code == 403
    assert client.post("/api/v1/relationships/recompute", headers=tokens["manager"]).status_code == 403
