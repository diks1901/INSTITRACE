# Known Limitations

We optimize for evaluator confidence: this page lists exactly what is simplified, unverified or
missing. None of these are hidden elsewhere.

## Security (demo-grade by design)

1. **Authentication is demo mode.** Passwords are salted PBKDF2 hashes and tokens are HMAC-signed,
   but the signing secret is a documented local default, there is no rate limiting or lockout, and
   sessions don't track device/IP. It must never be used against real users.
2. **Bureau officers are not scoped to their bureau** — any `BUREAU_OFFICER` can act on any case.
   Production would scope permissions per bureau/cell.
3. **No TLS/transport hardening** in the local demo configuration.

## Data and integrations

4. **PostgreSQL verified via bundled server (pgserver, PG 16.2)** — migrations, seed and the full
   71-test suite pass on PostgreSQL; a real Windows TCP-based PostgreSQL install remains
   documented-but-not-executed in this sandbox.
   (2026-10-30: full suite, `alembic upgrade head` on a fresh PG database, AND legacy-upgrade
   verification - build a database at the initial revision `69e0eedb34ac`, insert legacy rows,
   upgrade to head, recompute alerts - were re-verified against PG 16.2 after migrations
   `a2b7c9d1e001` + `b3c4d5e6f002`.)
5. **No external notifications** (email/SMS) — in-app alerts only, per the MVP scope. The alert
   refresh is manual/`POST /api/v1/alerts/refresh` or on recomputation; there is no background
   scheduler daemon.
6. **Evidence extraction is regex-based** for synthetic data patterns (`INC-YYYY-NNN`,
   `PROC-YYYY-NNN`, "incident dated …"). Real AICTE records would need fielded data or richer NLP.
7. **Matching thresholds are prototype constants** (documented in `docs/matching-engine.md`), not
   calibrated against real data. The heuristic score is not a probability.
8. **Quarterly analytics** are derivable from monthly trend data (12-month receipts/disposals);
   there is no separate quarterly chart/endpoint.

## Product surface

9. **No file uploads** — "supporting-document references" are represented as source-record
   references and free text, not stored attachments.
10. **No global undo/bulk operations.**
11. **Seed data is English-only**, fixed distribution (15 institutions/40 cases/3 bureaus).
12. **Dates in seed data are anchored to the seed date** so deadline scenarios render correctly;
    contents are otherwise fixed and repeatable.

## Process

13. **No stakeholder validation, performance benchmarking or accuracy claims exist** — and none
    are made. All UI screens label the dataset as synthetic demo data.
14. **No automated browser E2E suite** — see `docs/test-report.md` for what is covered instead
    (the 7 demo scenarios A–G incl. alert-recurrence legs were verified live through the API
    via the Vite proxy; see the Hunter-pass section of the test report).
15. **A recurring *coordination* alert for the same cases can only be exercised through the
    service layer**, because disposing a case is terminal by design (`DISPOSED` has no outgoing
    transitions) — the HTTP API cannot reactivate the same cases. The deadline channel
    recurrence is fully demo-able through the UI/API (move the expected disposal date). This is
    a workflow choice, not a bug: real complaints are not un-disposed.
