"""Server-side Case Search — mandatory scenarios (SIH 26264 feature task).

All queries hit the real seeded database through the HTTP API; authorization
is enforced by bureau scoping inside the SAME endpoint, so no search can leak
foreign-bureau rows. Disposable session-scoped test DB (conftest).
"""
from datetime import timedelta

from sqlalchemy import func, select

from app.models import ComplaintCase


def _list(client, headers, **params):
    resp = client.get("/api/v1/cases", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _case(client, headers, uid):
    data = _list(client, headers, case_id=uid)
    assert data["total"] == 1 and data["items"][0]["case_id"] == uid
    return data["items"][0]


# 1. exact Case ID ------------------------------------------------------------
def test_search_by_exact_case_id(client, tokens):
    r = _list(client, tokens["admin"], q="DEMO-CASE-001")
    assert r["items"] and all(c["case_id"] == "DEMO-CASE-001" for c in r["items"])
    assert r["total"] == 1


def test_search_case_id_exact_param_is_precise(client, tokens):
    r = _list(client, tokens["admin"], case_id="DEMO-CASE-001")
    assert r["total"] == 1
    # case-insensitive exact
    r2 = _list(client, tokens["admin"], case_id="demo-case-001")
    assert r2["total"] == 1
    # exact rejects near matches
    assert _list(client, tokens["admin"], case_id="DEMO-CASE-001X")["total"] == 0


# 2. partial Case ID ----------------------------------------------------------
def test_search_partial_case_id(client, tokens):
    r = _list(client, tokens["admin"], q="CASE-00")
    assert r["total"] >= 9, r["total"]
    assert all("CASE-00" in c["case_id"] for c in r["items"])


# 3. institution name ---------------------------------------------------------
def test_search_institution_name_partial(client, tokens):
    r = _list(client, tokens["admin"], institution_q="Sunrise")
    assert r["total"] >= 2
    assert all("Sunrise" in c["institution"]["name"] for c in r["items"])


# 4. exact AICTE permanent ID -------------------------------------------------
def test_search_permanent_id_exact(client, tokens):
    r = _list(client, tokens["admin"], permanent_id="DEMO-INS-001")
    assert r["total"] >= 1
    assert all(c["institution"]["permanent_id"] == "DEMO-INS-001" for c in r["items"])


def test_search_permanent_id_partial_returns_nothing(client, tokens):
    r = _list(client, tokens["admin"], permanent_id="DEMO-INS-00")
    assert r["total"] == 0, "permanent_id must be exact, not partial"


def test_search_permanent_id_case_insensitive(client, tokens):
    r = _list(client, tokens["admin"], permanent_id="demo-ins-001")
    assert r["total"] >= 1


# 5/6/7. bureau / status / category -------------------------------------------
def test_search_bureau_filter(client, tokens, db):
    # RB count depends on suite order (authorization workflows transfer cases);
    # derive the expectation from the seeded disposable DB, never hardcode.
    expected = db.scalar(
        select(func.count()).select_from(ComplaintCase)
        .where(ComplaintCase.bureau_id == 1)
    )
    r = _list(client, tokens["admin"], bureau_id=1, page_size=200)
    assert r["total"] == expected and all(c["bureau_id"] == 1 for c in r["items"])


def test_search_status_filter(client, tokens):
    r = _list(client, tokens["admin"], status="ESCALATED", page_size=200)
    assert r["total"] >= 1 and all(c["status"] == "ESCALATED" for c in r["items"])


def test_search_category_filter(client, tokens):
    r = _list(client, tokens["admin"], category="Infrastructure", page_size=200)
    assert r["total"] >= 1 and all(c["category"] == "Infrastructure" for c in r["items"])


# 8. date range ---------------------------------------------------------------
def test_search_date_range(client, tokens, db):
    case = db.scalar(select(ComplaintCase).where(ComplaintCase.case_id == "DEMO-CASE-002"))
    r_from = (case.receipt_date + timedelta(days=1)).isoformat()
    r_to = (case.receipt_date + timedelta(days=30)).isoformat()
    r = _list(client, tokens["admin"], receipt_from=r_from, receipt_to=r_to, page_size=200)
    ids = {c["case_id"] for c in r["items"]}
    assert "DEMO-CASE-002" not in ids, "case received before range start must be excluded"
    r2 = _list(client, tokens["admin"], receipt_from=(case.receipt_date - timedelta(days=1)).isoformat(),
                receipt_to=case.receipt_date.isoformat(), page_size=200)
    assert "DEMO-CASE-002" in {c["case_id"] for c in r2["items"]}


# 9. combination --------------------------------------------------------------
def test_search_combined_filters(client, tokens):
    r = _list(client, tokens["admin"], q="DEMO-CASE-00", status="UNDER_PROCESS",
              bureau_id=2, category="Faculty & Staff", page_size=200)
    assert r["total"] >= 1
    for c in r["items"]:
        assert "DEMO-CASE-00" in c["case_id"] or "DEMO-CASE-00" in c["subject"]
        assert c["status"] == "UNDER_PROCESS" and c["bureau_id"] == 2 and c["category"] == "Faculty & Staff"


# 10. empty result ------------------------------------------------------------
def test_search_empty_results(client, tokens):
    r = _list(client, tokens["admin"], q="NO-SUCH-CASE-9999")
    assert r["total"] == 0 and r["items"] == []


# 11. pagination with filters --------------------------------------------------
def test_search_pagination_with_filters(client, tokens):
    all_rb = _list(client, tokens["admin"], bureau_id=1, page_size=200)["total"]
    p1 = _list(client, tokens["admin"], bureau_id=1, page_size=5, page=1)
    p2 = _list(client, tokens["admin"], bureau_id=1, page_size=5, page=2)
    assert p1["total"] == all_rb and p2["total"] == all_rb
    assert len(p1["items"]) == 5 and len(p2["items"]) == min(5, all_rb - 5)
    assert {c["id"] for c in p1["items"]}.isdisjoint({c["id"] for c in p2["items"]})


# 12. bureau-level authorization / leakage ------------------------------------
def test_search_officer_scope_and_no_leakage(client, tokens):
    r = _list(client, tokens["officer.rb"], page_size=200)
    assert {c["bureau_id"] for c in r["items"]} == {1}
    # spoof attempt through filters is refused
    resp = client.get("/api/v1/cases", params={"bureau_id": 2}, headers=tokens["officer.rb"])
    assert resp.status_code == 403
    # institution text search cannot smuggle foreign cases to the officer
    r2 = _list(client, tokens["officer.rb"], institution_q="Sunrise", page_size=200)
    assert {c["bureau_id"] for c in r2["items"]} == {1}


# 13. clearing filters restores default list -----------------------------------
def test_search_clear_filters_restores_full_list_admin(client, tokens):
    r = _list(client, tokens["admin"], page_size=200)
    assert r["total"] == 40


# 14. result opens the correct case --------------------------------------------
def test_search_result_opens_correct_case_detail(client, tokens):
    item = _case(client, tokens["admin"], "DEMO-CASE-022")
    resp = client.get(f"/api/v1/cases/{item['id']}", headers=tokens["admin"])
    assert resp.status_code == 200
    assert resp.json()["case"]["case_id"] == "DEMO-CASE-022"
