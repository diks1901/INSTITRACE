# Test Report — INSTITRACE

Date of run environment: build sandbox (Linux, Python 3.11.2, Node v22.x, PostgreSQL 16.2 via
pgserver). All results below are actual outputs; nothing is fabricated or inferred.

## Backend — pytest (SQLite, default)

**Command**

```powershell
cd backend; ..\.venv\Scripts\Activate.ps1; pytest tests/ -q
```

**Result: 83 passed, 0 failed** (actual run: `83 passed, 3 warnings in 4.02s`; all 3 warnings are
third-party deprecation notices from the pinned FastAPI/Starlette stack — zero originate from
project code)

## Backend — pytest (PostgreSQL 16.2)

The identical suite runs against a real PostgreSQL server by pointing an env var at it:

```powershell
$env:INSTITRACE_TEST_DATABASE_URL="postgresql+psycopg2://postgres@/institrace_test?host=/tmp/itpg"
pytest tests/ -q
```

(Linux/macOS form; on Windows a normal TCP URL such as
`postgresql+psycopg2://postgres:postgres@localhost:5432/institrace_test` works the same way.
`psycopg2-binary` must be installed for PostgreSQL runs.)

**Result: 83 passed, 0 failed** (actual run: `83 passed, 3 warnings in 5.32s`; same third-party
deprecation notices as the SQLite run)

PostgreSQL verification also included: `alembic upgrade head` on a fresh PG database (pass),
seed load producing identical fixture counts (15 institutions / 40 cases / 36 assessments /
27 alerts), a live uvicorn smoke test (`/health`, `/dashboard/summary`, `/meta` →
`database_mode=postgresql`), and a schema-drift check (autogenerate diff = 0 operations on
both engines — migrations and models are in sync).

Suite breakdown (by file):

| Suite | Tests | Coverage highlights |
| --- | --- | --- |
| `test_matching.py` | 15 | Scenarios A–E; text-similarity guard; duplicate-free recompute; human-decision preservation; rule versioning; self-pair rejection; **v1.1.0 provenance semantics**: shared `source_record_ref` is procedural-only (never PSI), non-matching source refs prove nothing, shared incident refs still PSI, institution identity never assesses an incident |
| `test_alert_lifecycle.py` | 3 | **Alert occurrence lifecycle (FIX 1)**: coordination and deadline recurrence — condition gone ⇒ system `(auto)` resolves ⇒ condition back ⇒ NEW occurrence (history intact) ⇒ reruns create no duplicates; human-resolved-while-active suppression until the condition next goes absent |
| `test_evidence_review.py` | 5 | **Evidence-versioned review**: snapshot+hash pinned at review; unchanged evidence ⇒ nothing flagged; evidence change after CONFIRMED / REJECTED / DEFERRED ⇒ decision preserved + `requires_rereview` + `ASSESSMENT_EVIDENCE_CHANGED` audit; re-review re-pins; hash determinism |
| `test_migration_upgrade.py` | 4 | **Legacy migration (FIX 1)**: legacy DB at `69e0eedb34ac` with a RESOLVED alert → upgrade → recompute: no `IntegrityError`, occurrence 2 opened, occ-1 history preserved; ACTIVE legacy alert reused (no duplicate); legacy `system (auto)`-resolved recurrence; fresh-install `upgrade head` + seed stability (incl. review-history rows) |
| `test_psi_alert_lifecycle.py` | 8 | **PSI-alert evidence lifecycle (final fix)** — all 10 mandated scenarios except the config ones: insufficient→PSI creation, PSI→INSUFFICIENT resolution, PSI→NO_RELATIONSHIP resolution, no-duplicate recomputation, re-qualification→new occurrence, evidence-change-still-PSI consistency, full review-history survival, XBUREAU independence |
| `test_config_env.py` | 4 | **FIX 1 config audit**: `.env.example` ships the actual current rule-engine version; README-style `copy .env.example .env` fresh install loads 1.1.0 through real Settings machinery; loaded version drives every evidence fingerprint; no committed `.env` shadows the template |
| `test_review_history.py` | 4 | **Append-only review history (FIX 2) + version fingerprinting (FIX 3)**: full lifecycle initial-confirm → evidence change → re-review with different decision; both decisions remain API-accessible with their own snapshots/hashes; rule-version bump with identical evidence flags re-review; seed decisions present in history; hash includes `rule_version` |
| `test_workflow.py` | 13 | creation+history, duplicate IDs, status machine incl. terminal DISPOSED, transfer preserves history+audit, escalation, review persistence, invalid review rejected, resolved-alert traceability, role enforcement, filters |
| `test_deadlines.py` | 7 | approaching/overdue/disposed-deadline/escalation logic on a pinned clock; duplicate-free evaluation; auto-resolve on disposal; pending reminder |
| `test_dashboard_reports.py` | 9 | dashboard totals = live DB counts; bureau workload = DB; ageing buckets cover all active cases; disposal rate math; region filter; CSV structure+filters; CSV injection guard; overlap report separation of alert vs assessment dimensions |
| `test_api_reliability.py` | 11 | health/meta, error envelope, validation 422s, invalid FKs, pagination, audit read-only, auth required, bad login, institution detail, demo-reset role guard |

## Frontend — vitest + TypeScript

**Commands**

```powershell
cd frontend
npm test          # vitest run
npm run typecheck # tsc --noEmit
npm run build     # tsc --noEmit && vite build
```

**Results**

- `PASS 15 tests` (`Test Files 2 passed (2) — tests 15 passed (15)`: `src/test/client.test.ts`
  5 + `src/test/components.test.tsx` 10; an earlier version of this report said 13 — that count
  was stale, the real suites always numbered 15)
- `tsc --noEmit` → clean (zero type errors)
- `vite build` → succeeds (production bundle emitted to `frontend/dist/`)

Frontend tests cover: API client auth/error/401-session handling, query building, status/review
badge labeling (recommendation vs decision distinction, audit-pass regression guards on alert
badge classes/lifecycle states), demo-data labeling, empty states, InstitutionForm client
validation blocking submission, and the five mandated statuses all having labels.

## Final stabilization pass (2026-10-30, fourth round)

A final configuration-and-lifecycle audit confirmed two defects in code and one stale
documentation claim. All fixed and regression-tested; no features added, no tests weakened:

1. **Rule-engine version misconfiguration (`.env.example` vs `config.py`).** The shipped
   template carried `INSTITRACE_RULE_ENGINE_VERSION=1.0.0` while the code default is `1.1.0`;
   since the README instructs users to copy `.env.example` to `.env`, a documented fresh install
   ran out-of-date rule semantics and stamped evidence hashes with the wrong version. Template
   fixed to `1.1.0`. Verified: copied-template `.env` loads `1.1.0` via `get_settings()`; the
   seeded database has all 36 assessments stamped `rule_version='1.1.0'`; the stored evidence
   hash of a live assessment reproduces with `compute_evidence_hash(..., rule_version='1.1.0')`
   and differs at `1.0.0`; the running API's `/api/v1/meta` exposes `rule_engine_version=1.1.0`.
2. **`POTENTIAL_SAME_INCIDENT` alerts were frozen at assessment-creation time.** The matching
   service created (or failed to create) the "possible same incident" alert only inside the
   *create* branch of the pair loop, so a pair that later qualified — or later stopped
   qualifying — kept a stale alert state. The service now runs an alert lifecycle for every
   pair on every recompute (`tests/test_psi_alert_lifecycle.py`, 8 tests covering the full
   mandated lifecycle):
   - assessment transitions INSUFFICIENT_EVIDENCE / NO_RELATIONSHIP_ESTABLISHED → PSI ⇒ alert
     created (linked to the assessment id + current evidence hash);
   - a pair losing its supporting evidence ⇒ the still-active alert is auto-resolved
     (`system (auto)`, note names the new relationship type) while all prior history stays;
   - repeated recomputation reuses the active occurrence — zero duplicate alerts;
   - qualifying evidence returning later opens a NEW occurrence (history preserved);
   - informational PSI alerts remain separate from operational cross-bureau coordination
     alerts, never auto-confirm or merge anything, and every reviewer decision in
     `relationship_reviews` is untouched by the lifecycle (append-only).
   Alerts now expose `assessment_id` + `evidence_hash` through the API (new nullable columns,
   migration `c5d6e7f8a103`), so every informational alert is pinned to the exact assessment
   and evidence version it was raised from; the Coordination Centre displays the link.
3. **Stale test-count documentation.** This report claimed 13 frontend tests and a 71-test
   backend; the real suites were 15 frontend / 76 backend at the time (per-file counts were also
   stale for 5 suites). Corrected to actual measured numbers. A subsequent mandate-driven round
   added 7 regression tests (PSI-lifecycle +3, config audit +4), bringing the backend suite to
   its current **83** — all counts above and in README/known-limitations reflect 83 passed on
   both engines, 15 frontend.

Both defects verified in code before changing anything; all fixes followed by fresh-database
verification on SQLite and PostgreSQL (see the pytest sections above).

## Final critical-defect round (2026-10-30, third round)

An independent audit reproduced `IntegrityError: UNIQUE constraint failed:
coordination_alerts.logical_key, coordination_alerts.occurrence` on legacy databases and two
further gaps. All fixed and regression-tested:

1. **Legacy-database migration backfill.** `alembic/versions/a2b7c9d1e001` now backfills
   `alert_condition_state` from existing alerts (max occurrence per key; `present` = has an
   active row; `WHERE NOT IN` guard makes it idempotent), and `b3c4d5e6f002` re-applies the
   same backfill for databases that had already run `a2b7c9d1e001` without it. Upgrade paths
   verified: legacy SQLite + legacy PostgreSQL 16.2 (build a DB at `69e0eedb34ac`, insert a
   resolved alert with the old column shape, `upgrade head`, recompute → occurrence 2 opened,
   occurrence 1 preserved, no IntegrityError, repeat evaluation creates nothing) and fresh
   installs on both engines. See `backend/tests/test_migration_upgrade.py`.
2. **Append-only review history.** New `relationship_reviews` table (migration
   `b3c4d5e6f002`): every CONFIRMED/REJECTED/DEFERRED decision is recorded with the evidence
   snapshot, evidence hash and rule version it was made against; the assessment row keeps only
   the latest state. Exposed via `GET /api/v1/relationships/{id}/reviews` (newest first) and
   shown in the Coordination Centre's expanded evidence panel. Verified live: seed decisions
   present, re-review appends (no erase), 3 entries after a confirm→defer→confirm cycle.
3. **Rule-engine version in the evidence fingerprint.** `compute_evidence_hash()` now mixes in
   the rule-engine version, so a semantics bump flags prior decisions for re-review even when
   the serialized evidence is byte-identical. Regression-tested both at hash-unit level and
   end-to-end (`test_rule_version_change_with_identical_evidence_flags_rereview`).

A genuine defect WAS found during PostgreSQL verification of this round (the backfill SQL used
`MAX(boolean)`, which exists on neither PG nor is it needed): rewritten as the portable
`(MAX(CASE WHEN status != 'RESOLVED' THEN 1 ELSE 0 END) <> 0)`. PG's transactional DDL rolled
the failed revision back cleanly; the fixed migration passed on both engines.

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

Review-history API verification (live, admin, through the Vite proxy):

```
PASS - seeded review history row: CONFIRMED | by reviewer | v1.1.0 | snapshot: POTENTIAL_SAME_INCIDENT
PASS - re-review appended (no erase): [DEFERRED, CONFIRMED] (newest first)
PASS - history holds 3 append-only entries after confirm -> defer -> confirm
PASS - unknown assessment reviews -> HTTP 404
```

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
  local unix socket (pgserver) with migrations, seed and the full 83-test suite; a Windows
  TCP-DSN walkthrough is documented but not executed here.
- **Browser automation** (no Playwright/Cypress E2E) — interactions verified by HTTP-level tests,
  component tests with jsdom, and manual curl-based E2E.
- **Lint tooling** — no ESLint/ruff config; type checking serves as the static check for the
  frontend; Python style kept consistent manually.
