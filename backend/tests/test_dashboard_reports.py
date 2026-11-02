"""Dashboard metric consistency + report/CSV tests."""
import csv
import io

from sqlalchemy import func, select

from app.models import (
    ACTIVE_STATUSES,
    AlertStatus,
    AlertType,
    AssessmentStatus,
    CaseStatus,
    ComplaintCase,
    CoordinationAlert,
    RelationshipAssessment,
)


def _db_counts(db):
    rows = dict(db.execute(
        select(ComplaintCase.status, func.count()).group_by(ComplaintCase.status)
    ).all())
    return {k.value if hasattr(k, "value") else k: v for k, v in rows.items()}


def test_dashboard_summary_matches_database(client, tokens, db):
    resp = client.get("/api/v1/dashboard/summary", headers=tokens["admin"])
    assert resp.status_code == 200
    summary = resp.json()
    counts = _db_counts(db)
    assert summary["total_cases"] == sum(counts.values())
    assert summary["pending"] == counts.get("PENDING", 0)
    assert summary["under_process"] == counts.get("UNDER_PROCESS", 0)
    assert summary["disposed"] == counts.get("DISPOSED", 0)
    assert summary["transferred"] == counts.get("TRANSFERRED", 0)
    assert summary["escalated"] == counts.get("ESCALATED", 0)

    expected_open = db.scalar(select(func.count(CoordinationAlert.id)).where(
        CoordinationAlert.alert_type == AlertType.CROSS_BUREAU_COORDINATION,
        CoordinationAlert.status != AlertStatus.RESOLVED,
    ))
    assert summary["open_coordination_alerts"] == expected_open
    assert "definitions" in summary  # metrics carry documented definitions


def test_bureau_workload_matches_database(client, tokens, db):
    workload = client.get("/api/v1/dashboard/bureau-workload", headers=tokens["admin"]).json()
    assert len(workload) >= 3
    for row in workload:
        total = db.scalar(select(func.count(ComplaintCase.id)).where(
            ComplaintCase.bureau_id == row["bureau_id"]))
        active = db.scalar(select(func.count(ComplaintCase.id)).where(
            ComplaintCase.bureau_id == row["bureau_id"],
            ComplaintCase.status.in_(list(ACTIVE_STATUSES))))
        assert row["total_cases"] == total
        assert row["active_cases"] == active


def test_trends_shape(client, tokens):
    data = client.get("/api/v1/dashboard/trends?months=6", headers=tokens["admin"]).json()
    assert len(data["monthly"]) == 6
    assert any(m["receipts"] > 0 for m in data["monthly"])


def test_ageing_buckets_cover_all_active_cases(client, tokens, db):
    report = client.get("/api/v1/reports/ageing", headers=tokens["admin"]).json()
    bucket_total = sum(r["case_count"] for r in report["rows"])
    active = db.scalar(select(func.count(ComplaintCase.id)).where(
        ComplaintCase.status.in_(list(ACTIVE_STATUSES))))
    assert bucket_total == active


def test_disposal_rate_calculation(client, tokens, db):
    report = client.get("/api/v1/reports/disposal", headers=tokens["admin"]).json()
    rows = {r["metric"]: r["value"] for r in report["rows"]}
    total = db.scalar(select(func.count(ComplaintCase.id)))
    disposed = db.scalar(select(func.count(ComplaintCase.id)).where(
        ComplaintCase.status == CaseStatus.DISPOSED))
    assert rows["total_cases"] == total
    assert rows["disposed_cases"] == disposed
    assert abs(rows["disposal_rate_pct"] - round(100 * disposed / total, 1)) < 0.001


def test_institutions_report_filter(client, tokens):
    all_rows = client.get("/api/v1/reports/institutions", headers=tokens["admin"]).json()["rows"]
    assert len(all_rows) == 15
    south = client.get("/api/v1/reports/institutions?region=Southern",
                       headers=tokens["admin"]).json()["rows"]
    assert 0 < len(south) < len(all_rows)
    assert all(r["region"] == "Southern" for r in south)


def test_csv_export_structure_and_filters(client, tokens):
    resp = client.get("/api/v1/reports/export.csv?report=institutions&region=Southern",
                      headers=tokens["admin"])
    assert resp.status_code == 200
    text = resp.text
    assert text.startswith("# INSTITRACE report"), "metadata header expected"
    assert "Applied filters" in text and "Southern" in text
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if r and not r[0].startswith("#")]
    header, *body = rows
    assert header[0] == "permanent_id"
    assert all(r[2] == "Southern" for r in body), "CSV must respect filters"


def _export_with_injection(client, tokens, monkey_url=None):
    return client.get("/api/v1/reports/export.csv?report=institutions", headers=tokens["admin"])


def test_csv_formula_injection_guard(db):
    from app.services import report_service

    payload = [{"name": "=HYPERLINK(\"https://evil\",\"x\")", "value": "+1+1", "safe": "-5"}]
    text = report_service.build_csv("guard-test", ["name", "value", "safe"], payload, {})
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if r and not r[0].startswith("#")]
    body = rows[1]
    assert body[0].startswith("'=")
    assert body[1].startswith("'+")
    assert body[2].startswith("'-"), "leading minus is also guarded"


def test_overlap_report_separates_alert_and_assessment_dimensions(client, tokens):
    report = client.get("/api/v1/reports/overlaps", headers=tokens["admin"]).json()
    dims = {r["dimension"] for r in report["rows"]}
    assert dims == {"alert", "assessment"}, \
        "cross-bureau alerts and same-incident assessments are separate concepts"
