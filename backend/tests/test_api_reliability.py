"""API reliability: error formats, auth, validation, pagination, health/meta."""


def test_health_and_meta(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    meta = client.get("/api/v1/meta").json()
    assert meta["rule_engine_version"] == "1.0.0"
    # mode must truthfully reflect the database under test (sqlite or postgresql)
    from .conftest import _TEST_DB_URL

    expected = "sqlite" if _TEST_DB_URL.startswith("sqlite") else "postgresql"
    assert meta["database_mode"] == expected
    assert "synthetic" in meta["demo_data_notice"]


def test_consistent_error_format(client, tokens):
    resp = client.get("/api/v1/cases/999999", headers=tokens["admin"])
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == 404
    assert "not found" in body["error"]["message"].lower()


def test_validation_error_format(client, tokens):
    resp = client.post("/api/v1/cases", headers=tokens["admin"], json={
        "case_id": "X",  # too short
        "institution_id": 1,
        "receipt_date": "2026-10-20",
        "category": "Others",
        "subject": "ok subject",
        "bureau_id": 1,
    })
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["message"] == "Validation failed"
    assert body["error"]["details"]


def test_expected_disposal_before_receipt_rejected(client, tokens):
    resp = client.post("/api/v1/cases", headers=tokens["admin"], json={
        "case_id": "DEMO-CASE-950", "institution_id": 1, "receipt_date": "2026-10-20",
        "category": "Others", "subject": "bad date ordering", "bureau_id": 1,
        "expected_disposal_date": "2026-10-01",
    })
    assert resp.status_code == 422


def test_invalid_foreign_keys_rejected(client, tokens):
    resp = client.post("/api/v1/cases", headers=tokens["admin"], json={
        "case_id": "DEMO-CASE-951", "institution_id": 424242, "receipt_date": "2026-10-20",
        "category": "Others", "subject": "bad institution ref", "bureau_id": 1,
    })
    assert resp.status_code == 422


def test_pagination(client, tokens):
    page1 = client.get("/api/v1/cases?page=1&page_size=10", headers=tokens["admin"]).json()
    page2 = client.get("/api/v1/cases?page=2&page_size=10", headers=tokens["admin"]).json()
    assert page1["total"] >= 40
    ids1 = {i["case_id"] for i in page1["items"]}
    ids2 = {i["case_id"] for i in page2["items"]}
    assert not ids1 & ids2, "pages must not overlap"


def test_audit_endpoint_is_read_only(client, tokens):
    assert client.get("/api/v1/audit-events", headers=tokens["admin"]).status_code == 200
    # append-only by design: no mutation routes exist (404 unknown / 405 method not allowed)
    assert client.post("/api/v1/audit-events", headers=tokens["admin"], json={}).status_code in (404, 405)
    assert client.request("DELETE", "/api/v1/audit-events/1", headers=tokens["admin"]).status_code in (404, 405)


def test_auth_required(client):
    assert client.get("/api/v1/dashboard/summary").status_code == 401
    assert client.get("/api/v1/alerts").status_code == 401
    assert client.get("/api/v1/institutions").status_code == 401


def test_login_rejects_bad_credentials(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_institution_search_and_detail(client, tokens):
    resp = client.get("/api/v1/institutions?q=Sunrise", headers=tokens["manager"])
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    inst = resp.json()["items"][0]
    detail = client.get(f"/api/v1/institutions/{inst['id']}", headers=tokens["manager"])
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["cases"]) >= 2
    assert body["summary"]["total_cases"] == len(body["cases"])
    assert body["institution"]["is_demo"] is True


def test_demo_reset_requires_admin(client, tokens):
    forbidden = client.post("/api/v1/admin/demo-reset", headers=tokens["manager"])
    assert forbidden.status_code == 403
