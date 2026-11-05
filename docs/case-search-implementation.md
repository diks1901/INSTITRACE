# Case Search — implementation & demonstration report

**Date:** 2026-11-04 · **Branch:** `arena/7c2a8ebe-institrace` · **Commit:** `e95f838`
**Scope decision (reconfirmed):** searches run on the existing `/cases` endpoint so
role/bureau scoping applies unchanged; only *additive, backwards-compatible*
parameters were added. No duplicate endpoints; no new dependencies; no engine,
threshold, seed or security changes.

---

## 1. Files changed / added

| File | Change |
|---|---|
| `backend/app/routers/cases.py` | `/cases`: added `case_id` (exact, case-insensitive) and `permanent_id` (exact, case-insensitive, joins `Institution` only when used). Existing params unchanged. |
| `backend/tests/test_case_search.py` | **17 tests**, one per mandated scenario (see §4). |
| `frontend/src/pages/CasesPage.tsx` | Top-of-registry `CaseSearchForm`: staged draft → Search button/Enter applies → URL params (shareable, source of truth); active-filter chips with per-chip removal; Clear filters; result count preserved in table header; row click → existing case detail page. |
| `frontend/src/pages/search.css` | Panel styling, government-formal; no design-system changes elsewhere. |
| `frontend/src/pages/CoordinationCentrePage.tsx` | Alert case chips now click through:`/cases?case_id=<id>` (alerts carry business IDs, so navigation uses the server-side exact-ID search — no internal-PK guessing). |
| `frontend/src/test/search-form.test.tsx` | **7 tests**: fields present, combined-filter submit, Enter submits, Clear resets, chips render/remove, disabled-clear-when-empty, empty fields dropped. |
| `README.md`, `docs/test-report.md`, `docs/requirements-traceability.md`, `docs/judge-qa.md`, `docs/sih-2026-pitch-deck.md`, `docs/prior-art.md`, `docs/known-limitations.md` | Test counts synced to the real runs (101/27 → **118/34**); traceability row 7 updated. |

## 2. API (`GET /api/v1/cases`)

| Param | Behaviour |
|---|---|
| `q` | partial, case-insensitive, over case ID **and** subject |
| `case_id` | **exact** case/complaint ID, case-insensitive |
| `institution_q` | partial over institution name **or** permanent ID |
| `permanent_id` | **exact** AICTE Permanent ID, case-insensitive |
| `bureau_id` | exact bureau id (officers: only own bureau) |
| `region` | exact region (institution) |
| `category` | exact complaint category |
| `status` | exact case status |
| `receipt_from` / `receipt_to` | receipt-date range (inclusive) |
| `overdue`/`approaching`/`review_state` | unchanged from before |
| `sort`/`sort_dir`/`page`/`page_size` | pagination applied **after** filtering (unchanged) |

## 3. Security behavior

Authorization is enforced inside `/cases` before any filter runs:
- Officer search (`officer.rb`) returns only own-bureau rows — verified live:
  `?q=CASE&status=UNDER_PROCESS&category=Infrastructure` → 1 result, all RB.
- Spoof attempt `?bureau_id=2` from RB officer → **403** (tested + live-verified).
- Even text searches cannot leak: `?permanent_id=DEMO-INS-002` as officer.rb
  returns only the RB case (`DEMO-CASE-003`), not the PGRC/NIC ones (live-verified).

## 4. Mandated scenarios → test coverage (`backend/tests/test_case_search.py`)

1. exact Case-ID search (`q` + `case_id`, incl. case-insensitive & near-match rejection)
2. partial Case-ID search
3. institution-name (partial) search
4. exact permanent-ID search (+ partial-rejected, + case-insensitive)
5. bureau filter · 6. status · 7. category
8. receipt-date range (boundary exactness against seeded dates)
9. combination of multiple filters
10. empty-result search
11. pagination combined with filters (page 1/2 disjoint, shared total)
12. bureau-level authorization / leakage guard
13. clearing filters restores the default list (admin unfiltered = 40)
14. search result opens the correct case detail (`/cases/{id}`)

Frontend scenarios (§1 table) cover: fields, Search/Enter, Clear, chips, URL state.

## 5. Verification (all actually executed this session)

| Suite | Result |
|---|---|
| Backend SQLite `pytest tests/` | **118/118** (101 pre-existing + 17 search) |
| Backend PostgreSQL 16.2 (fresh `institrace_test`) | **118/118** |
| Frontend Vitest | **34/34** (27 pre-existing + 7 search-form) |
| `tsc --noEmit` / `vite build` | clean / ✓ |
| Live API smoke vs seeded demo data (admin + RB officer) | all searches in §2/§3 returned expected totals |

## 6. Screenshots — honest note

Browser screenshots **could not be captured in this sandbox**: Playwright's CDN is
network-blocked and no browser binary is installed, so there is no headless
browser to render the UI. Per the standing rule "never claim untested = verified",
no fabricated or regenerated images are provided. Substitute evidence delivered:
7 passing component tests for the exact form markup, a clean production build, and
live-API smokes. To capture the real screenshots in ~2 minutes on any machine:
`cd backend && python -m uvicorn app.main:app` · `cd frontend && npm run dev` →
login (admin / InstiTrace#Demo1) → Case Registry → the **Search cases** panel is
visible at top; search `DEMO-CASE-001`, then chip-remove/clear to see states.
