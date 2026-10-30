# Test Report — INSTITRACE

Date of run environment: build sandbox (Linux, Python 3.11.2, Node v22.x, PostgreSQL 16.2 via
pgserver). All results below are actual outputs; nothing is fabricated or inferred.

## Backend — pytest (SQLite, default)

**Command**

```powershell
cd backend; ..\.venv\Scripts\Activate.ps1; pytest tests/ -q
```

**Result: 63 passed, 0 failed** (actual run: `63 passed, 3 warnings in 1.54s`)

## Backend — pytest (PostgreSQL 16.2)

The identical suite runs against a real PostgreSQL server by pointing an env var at it:

```powershell
$env:INSTITRACE_TEST_DATABASE_URL="postgresql+psycopg2://postgres@/institrace_test?host=/tmp/itpg"
pytest tests/ -q
```

(Linux/macOS form; on Windows a normal TCP URL such as
`postgresql+psycopg2://postgres:postgres@localhost:5432/institrace_test` works the same way.
`psycopg2-binary` must be installed for PostgreSQL runs.)

**Result: 63 passed, 0 failed** (actual run: `63 passed, 3 warnings in 2.41s`)

PostgreSQL verification also included: `alembic upgrade head` on a fresh PG database (pass),
seed load producing identical fixture counts (15 institutions / 40 cases / 36 assessments /
27 alerts), a live uvicorn smoke test (`/health`, `/dashboard/summary`, `/meta` →
`database_mode=postgresql`), and a schema-drift check (autogenerate diff = 0 operations on
both engines — migrations and models are in sync).

Suite breakdown (by file):

| Suite | Tests | Coverage highlights |
| --- | --- | --- |
| `test_matching.py` | 14 | Scenarios A–E; text-similarity guard; duplicate-free recompute; human-decision preservation; rule versioning; self-pair rejection; **v1.1.0 provenance semantics**: shared `source_record_ref` is procedural-only (never PSI), non-matching source refs prove nothing, shared incident refs still PSI, institution identity never assesses an incident |
| `test_alert_lifecycle.py` | 3 | **Alert occurrence lifecycle (FIX 1)**: coordination and deadline recurrence — condition gone ⇒ system `(auto)` resolves ⇒ condition back ⇒ NEW occurrence (history intact) ⇒ reruns create no duplicates; human-resolved-while-active suppression until the condition next goes absent |
| `test_evidence_review.py` | 5 | **Evidence-versioned review (FIX 3)**: snapshot+hash pinned at review; unchanged evidence ⇒ nothing flagged; evidence change after CONFIRMED / REJECTED / DEFERRED ⇒ decision preserved + `requires_rereview` + `ASSESSMENT_EVIDENCE_CHANGED` audit; re-review re-pins; hash determinism |
| `test_workflow.py` | 12 | creation+history, duplicate IDs, status machine incl. terminal DISPOSED, transfer preserves history+audit, escalation, review persistence, invalid review rejected, resolved-alert traceability, role enforcement, filters |
| `test_deadlines.py` | 6 | approaching/overdue/disposed-deadline/escalation logic on a pinned clock; duplicate-free evaluation; auto-resolve on disposal; pending reminder |
| `test_dashboard_reports.py` | 9 | dashboard totals = live DB counts; bureau workload = DB; ageing buckets cover all active cases; disposal rate math; region filter; CSV structure+filters; CSV injection guard; overlap report separation of alert vs assessment dimensions |
| `test_api_reliability.py` | 13 | health/meta, error envelope, validation 422s, invalid FKs, pagination, audit read-only, auth required, bad login, institution detail, demo-reset role guard |

## Frontend — vitest + TypeScript

**Commands**

```powershell
cd frontend
npm test          # vitest run
npm run typecheck # tsc --noEmit
npm run build     # tsc --noEmit && vite build
```

**Results**

- `PASS 13 tests` (`Test Files 2 passed (2), Tests 13 passed (13)`)
- `tsc --noEmit` → clean (zero type errors)
- `vite build` → succeeds (production bundle emitted to `frontend/dist/`)

Frontend tests cover: API client auth/error/401-session handling, query building, status/review
badge labeling (recommendation vs decision distinction, audit-pass regression guards on alert
badge classes/lifecycle states), demo-data labeling, empty states, InstitutionForm client
validation blocking submission, and the five mandated statuses all having labels.

## Hunter-pass outcomes (2026-10-30, second audit round)

Three confirmed-in-code defects were fixed and regression-tested end-to-end:

1. **Resolved alert conditions could never recur (alert service upsert).** Replaced dedupe-key
   upsert with an occurrence lifecycle: `alert_condition_state` tracks condition presence, a
   recurring condition opens a NEW alert occurrence (`coordination_alerts` unique on
   `(logical_key, occurrence)`), absent conditions are resolved `system (auto)` with history
   retained, and human-resolved-while-active suppresses silent respawning. Verified live
   (Scenario G legs G1–G5 below) and by `test_alert_lifecycle.py`.
2. **`source_record_ref` was treated as an incident reference (R1).** Engine v1.1.0 separates
   provenance (`R7_SHARED_SOURCE_RECORD_PROVENANCE`, typed evidence, weight 0 — procedural
   link only) from incident references. Verified by the new engine tests in
   `test_matching.py`.
3. **Human decisions were pinned to nothing.** Assessments now record `evidence_hash`,
   `reviewed_evidence_hash` and a full `evidence_snapshot` at decision time; a material
   evidence change after CONFIRMED/REJECTED/DEFERRED sets `requires_rereview` and writes an
   `ASSESSMENT_EVIDENCE_CHANGED` audit event, while the decision and its original snapshot are
   preserved. Exposed in the API (`requires_rereview`, snapshot) and flagged in the UI.
   Verified by `test_evidence_review.py`.

Both defects also required a schema migration: `a2b7c9d1e001` (alembic, batch-safe for SQLite
and portable to PostgreSQL; verified on both). Rules/behaviours: rule engine `1.1.0`.

### Live scenario verification (through the Vite proxy at :5173, admin role, 2026-10-30)

```
PASS - A: shared incident-ref across bureaus -> PSI + coordination alert with non-duplicate wording
PASS - B: distinct incident refs -> NO_RELATIONSHIP_ESTABLISHED with recorded conflicts
PASS - C: sparse records -> INSUFFICIENT_EVIDENCE with missing-inventory; missing != negative
PASS - D: same-bureau PSI, and NO cross-bureau coordination alert for that institution alone
PASS - E: different institutions are never assessed by the engine
PASS - F: recompute preserves human CONFIRMED decision + reviewer + rationale; no rereview flag (unchanged evidence)
PASS - F2: reviewed assessment exposes pinned evidence snapshot + hash through the API
PASS - G1: deadline moved to future -> OVERDUE alert auto-resolved by system (not deleted)
PASS - G2: condition returns -> NEW active alert occurrence 2; occurrence-1 history row intact
PASS - G3: repeated refreshes create NO duplicate active alerts
PASS - G4: disposing the pair auto-resolves the coordination alert (system (auto)), row retained
PASS - G5: DISPOSED -> active is REJECTED by the state machine (422) - no silent reopening
```

(Same checks pass on the fixed SQLite seed: 15 institutions / 40 cases / 36 assessments /
27 alerts.)

## Audit-pass outcomes (2026-10-30)

Real defects found and fixed during the audit:

1. **Date-coupled deadline test** (`test_repeated_evaluation_no_duplicates`): assumed the seed
   date equals the pinned test clock; fixed to assert exactly one LIVE alert per
   condition-instance (prior date-anchored instances may legitimately exist as RESOLVED history),
   plus a new regression test proving a changed expected-disposal date creates a NEW alert
   instance and auto-resolves the stale one without duplicates.
2. **JSON containment was not portable to PostgreSQL** (`.contains()` on a JSON column): replaced
   with an institution-scoped query + exact membership filtering in `cases.py` and tests.
3. **Missing PBKDF2-dep-independent defects**: none — but the audit also fixed
   `alert_service.list_alerts` (previously loaded the whole table to count it) and report N+1
   loads (`selectinload` eager loading), invisible UI bugs (alert badges reusing relationship
   styles; internal numeric IDs shown to humans in two screens), and removed dead code
   (unused export/variable).

## Live E2E verification (manual, real servers)

With `uvicorn app.main:app` on :8000 and `vite` on :5173 (proxy → backend):

- `GET /api/v1/health` → `{"status":"ok"}`
- Login as `reviewer`, defer assessment DEMO-CASE-005↔006 → `DEFERRED`; then
  `POST /api/v1/relationships/recompute` →
  `{"assessments_created":0,"assessments_updated":0,"alerts_created":0,"human_decisions_preserved":3}`
  and the deferred decision + reviewer persisted.
- Dashboard summary served live numbers (`total_cases: 40`, `open_coordination_alerts: 8` at seed).

## NOT VERIFIED (honest list)

- **TCP PostgreSQL + DSN via environment .env loading** — verified using PostgreSQL 16.2 over a
  local unix socket (pgserver) with migrations, seed and the full 50-test suite; a Windows
  TCP-DSN walkthrough is documented but not executed here.
- **Browser automation** (no Playwright/Cypress E2E) — interactions verified by HTTP-level tests,
  component tests with jsdom, and manual curl-based E2E.
- **Lint tooling** — no ESLint/ruff config; type checking serves as the static check for the
  frontend; Python style kept consistent manually.
