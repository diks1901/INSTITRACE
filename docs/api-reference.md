# API Reference — INSTITRACE v0.1.0

All endpoints are versioned under `/api/v1`. Interactive docs (live Swagger UI) run at
`http://localhost:8000/docs`.

## Conventions

- **Auth**: `Authorization: Bearer <token>` from `POST /api/v1/auth/login`. Missing/invalid →
  `401`; insufficient role → `403`. Role guards are enforced on the backend for every
  consequential action.
- **Errors**: a consistent envelope `{ "error": { "code": <http>, "message": "...", "details"?: [...] } }`.
  Validation failures are `422` with per-field details.
- **Pagination**: list endpoints accept `page` (≥1) and `page_size` (≤200) and return
  `{ items, total, page, page_size }`.

## Auth

| Method | Path | Role | Description |
| --- | --- | --- | --- |
| POST | `/auth/login` | — | Demo login; returns signed expiring token (demo-grade) |
| GET | `/auth/me` | any | Current identity |

## Health & metadata

| Method | Path | Role | Description |
| --- | --- | --- | --- |
| GET | `/health` | any | Liveness + DB reachability |
| GET | `/meta` | any | Versions, DB mode, bureaus, statuses, thresholds, demo notice |

## Dashboard (all values computed from the database)

| Method | Path | Role | Description |
| --- | --- | --- | --- |
| GET | `/dashboard/summary` | any | Status counts, overdue/approaching, open alerts, pending reviews + metric definitions |
| GET | `/dashboard/bureau-workload` | any | Total/active cases per bureau |
| GET | `/dashboard/trends?months=12` | any | Monthly receipts/disposals |

## Institutions

| Method | Path | Role |
| --- | --- | --- |
| GET | `/institutions?q=&region=&state=&page=&page_size=` | any |
| POST | `/institutions` | ADMIN (409 on duplicate permanent ID) |
| GET | `/institutions/{id}` | any — includes consolidated case history, alerts, assessments, summary |
| PATCH | `/institutions/{id}` | ADMIN |
| GET | `/institutions/{id}/cases` | any |

## Cases

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| GET | `/cases?...` | any | Filters: `q, institution_id, institution_q, bureau_id, region, category, status, receipt_from, receipt_to, overdue, approaching, review_state, sort, sort_dir` + pagination |
| POST | `/cases` | ADMIN, BUREAU_OFFICER | 409 duplicate ID; 422 invalid FKs/dates; writes history+audit |
| GET | `/cases/{id}` | any | Metadata + actions + transfers + assessments + alerts |
| PATCH | `/cases/{id}` | ADMIN, BUREAU_OFFICER | Partial update with audit |
| GET | `/cases/{id}/history` | any | Chronological business history |
| POST | `/cases/{id}/actions` | ADMIN, BUREAU_OFFICER | Append remark/action |
| POST | `/cases/{id}/status` | ADMIN, BUREAU_OFFICER | Enforces the status machine; 422 on illegal transition |
| POST | `/cases/{id}/assign` | ADMIN, BUREAU_OFFICER | Officer reassignment |
| POST | `/cases/{id}/transfer` | ADMIN, BUREAU_OFFICER | Transfer record + history + audit; never disposes |
| POST | `/cases/{id}/escalate` | ADMIN, BUREAU_OFFICER | Status → ESCALATED with reason |
| POST | `/cases/{id}/next-action` | ADMIN, BUREAU_OFFICER | Next action + deadline fields |

## Relationship assessments

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| GET | `/relationships?status=&relationship_type=&institution_id=&case_pk=` | any | Includes embedded source/candidate case summaries and evidence lists |
| GET | `/relationships/{id}` | any | |
| POST | `/relationships/{id}/review` | ADMIN, REVIEWER | `CONFIRMED` / `REJECTED` / `DEFERRED` + rationale; persists across recomputes |
| POST | `/relationships/recompute` | ADMIN, REVIEWER | Idempotent; counts created/updated/duplicates-prevented/preserved decisions |

## Alerts

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| GET | `/alerts?alert_type=&status=&institution_id=` | any | Cross-bureau, same-incident, reminder, deadline, overdue, escalation alerts |
| GET | `/alerts/{id}` | any | |
| POST | `/alerts/{id}/acknowledge` | ADMIN, BUREAU_OFFICER, REVIEWER | OPEN → ACKNOWLEDGED |
| POST | `/alerts/{id}/resolve` | ADMIN, BUREAU_OFFICER, REVIEWER | Requires resolution note; 422 if already resolved |
| POST | `/alerts/refresh` | ADMIN, BUREAU_OFFICER, REVIEWER | The documented alert-refresh mechanism; idempotent |

## Reports

| Method | Path | Description |
| --- | --- | --- |
| GET | `/reports/institutions?region=&state=` | Per-institution totals/active/disposed/overdue |
| GET | `/reports/bureaus` | Workload, disposal rate, avg days to dispose |
| GET | `/reports/regions` | Region aggregation |
| GET | `/reports/statuses` | Status distribution + average age |
| GET | `/reports/ageing` | Active-case age buckets (0–30, 31–60, 61–90, 91–180, 180+) |
| GET | `/reports/disposal` | Disposal rate + monthly disposals |
| GET | `/reports/overlaps` | Alerts × states and assessments × states |
| GET | `/reports/export.csv?report=&region=&state=` | CSV with metadata header rows, formula-injection guard, applied filters |

All report responses include a `definition` string stating exactly how figures are computed.

## Audit

| Method | Path | Role | Description |
| --- | --- | --- | --- |
| GET | `/audit-events?entity_type=&event_type=&actor=&entity_id=` | any | Append-only trail; no mutation routes exist by design |

## Admin

| Method | Path | Role | Description |
| --- | --- | --- | --- |
| POST | `/admin/demo-reset` | ADMIN | Explicit, destructive reseed of the synthetic dataset |
