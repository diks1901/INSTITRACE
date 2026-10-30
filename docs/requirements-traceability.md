# Requirements Traceability — SIH26264

Status legend: ✅ Implemented & tested · 🔶 Implemented, partially verified · ❌ Gap

| # | Problem-statement requirement | Where implemented | Test evidence | Status |
| --- | --- | --- | --- | --- |
| 1 | Centralized institution profile + consolidated complaint history | `InstitutionDetailPage`; `GET /institutions/{id}` returns profile+cases+alerts+assessments | `test_institution_search_and_detail` | ✅ |
| 2 | Complaint IDs, receipt dates, categories, statuses, assigned bureaus/officers | `complaint_cases` model; Cases registry UI | `test_case_creation_and_initial_history`, `test_case_filters` | ✅ |
| 3 | Last action, next action, expected disposal date, action history | Case fields + `case_actions`; Case detail UI timeline | `test_status_change_history_and_invalid_transition` | ✅ |
| 4 | Cross-bureau overlap detection and alerts | `alert_service.evaluate_alerts` + `CROSS_BUREAU_COORDINATION` alerts + Coordination Centre | `test_scenario_a_*`, `test_repeat_recompute_creates_no_duplicates` | ✅ |
| 5 | Linking/mapping related cases | `relationship_assessments` (pair-based, explainable) | `test_scenario_d_*` | ✅ |
| 6 | Dashboard metrics + workload monitoring | `dashboard_service` + Dashboard UI with charts | `test_dashboard_summary_matches_database`, `test_bureau_workload_matches_database` | ✅ |
| 7 | Search/filters across institutions, cases, bureaus, regions, categories, statuses, date ranges | `/cases` filters + `/institutions` filters (server-side, paginated) | `test_case_filters`, `test_pagination` | ✅ |
| 8 | Pending reminders, deadline warnings, escalation alerts | `PENDING_REMINDER`, `APPROACHING_DEADLINE`, `OVERDUE`, `ESCALATION_REQUIRED` alert types | `tests/test_deadlines.py` (pinned clock) | ✅ |
| 9 | Institution/region/bureau/status-wise reports | `report_service` + Reports UI | `test_institutions_report_filter`, `test_disposal_rate_calculation` | ✅ |
| 10 | Ageing, disposal rates, overlap reporting, monthly/quarterly analytics | `/reports/ageing|disposal|overlaps`, `/dashboard/trends` (monthly; quarterly aggregation = derived from monthly rows in UI/report definitions) | `test_ageing_buckets_cover_all_active_cases`, `test_trends_shape` | ✅ (quarterly view is derived, not a separate chart — see limitations) |
| 11 | Explainable rule-based / AI-assisted identification of related complaints | `app/matching/engine.py` rules R1–R6 with evidence lists and abstention | `backend/tests/test_matching.py` (8 tests) | ✅ |
| 12 | Valid state transitions; transfer must not erase history/silently dispose | `VALID_TRANSITIONS`, `case_service.transfer_case`, status machine | `test_transfer_*`, `test_disposed_is_terminal` | ✅ |
| 13 | Human review with confirm/reject/defer + rationale, preserved across recomputation | `POST /relationships/{id}/review`, recompute preserve logic | `test_review_decision_persists_with_rationale`, `test_human_decision_preserved_across_recompute` | ✅ |
| 14 | No duplicate alerts on recomputation | `dedupe_key` unique constraint + upsert logic | `test_repeat_recompute_creates_no_duplicates`, `test_repeated_evaluation_no_duplicates` | ✅ |
| 15 | Two history layers (case action history vs audit trail), audit append-only | `case_actions` vs `audit_events`; routers expose no mutation for audit | `test_audit_endpoint_is_read_only` | ✅ |
| 16 | Demo access with roles; backend-enforced permissions | 4 demo users; `require_roles` guards; PBKDF2 hashing; signed expiring tokens | `test_role_enforcement`, `test_auth_required`, `test_login_rejects_bad_credentials` | ✅ (demo-grade; see limitations) |
| 17 | CSV export: headers, escaping, filtered rows, timestamp, filters, formula-injection protection | `(GET /reports/export.csv)` + `build_csv` | `test_csv_export_structure_and_filters`, `test_csv_formula_injection_guard` | ✅ |
| 18 | Deadlines: overdue computed from expected disposal + status; disposed not overdue | `alert_service` ACTIVE_STATUSES gating | `test_disposed_case_never_overdue`, `test_disposal_auto_resolves_open_overdue_alert` | ✅ |
| 19 | Consistent API errors, correct status codes, validation | Exception handlers in `main.py`, Pydantic schemas | `test_consistent_error_format`, `test_validation_error_format` | ✅ |
| 20 | PostgreSQL primary + SQLite fallback, env-based config, migrations | `INSTITRACE_DATABASE_URL`, Alembic initial migration | SQLite: full suite. PostgreSQL 16.2: migrations + seed + full 50-test suite + live API smoke + zero schema drift (pgserver-bundled server) | ✅ |
| 21 | Deterministic synthetic seed w/ scenarios A–G, ~15 institutions, ~40 cases, all statuses | `app/seed.py`; idempotent; `--reset` explicit | seed assertions inside tests; idempotence via `seed_demo` guard | ✅ |
| 22 | Settings/system page: bureaus, statuses, thresholds, rule version, DB mode, app version, demo disclosure | Settings & Status page + `/meta` | manual + `test_health_and_meta` | ✅ |
| 23 | No dead/placeholder UI; loading/empty/error states | components (`Loading`, `EmptyState`, `ErrorState`); every button wired | frontend tests (`components.test.tsx`) + manual E2E | ✅ |
| 24 | OpenAPI docs | FastAPI autodocs at `/docs` | manual (server running) | ✅ |

## Explicit non-goals (documented gaps)

- Email/SMS dispatch — in-app alerts only (allowed by spec Part 7).
- Real AICTE authentication/SSO — demo mode only.
- Quarterly *chart* — quarterly figures derive from monthly trend rows; no separate quarterly chart is rendered.
