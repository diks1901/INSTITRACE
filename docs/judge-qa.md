# Judge Q&A — 17 prepared questions

Team SONARA · SIH 2026 · PS SIH26264. Two-tier answers: the **short** line is for the
room; the **technical** answer is for a judge who digs deeper.

---

**Q1. How do you avoid false positives — treating two genuinely different complaints as one incident?**

**Short:** We never merge automatically, and we separate two concepts that are easy to confuse: "same institution handled by two bureaus" (a coordination alert) vs "same underlying incident" (an evidence-scored assessment). The demo shows one rejected false-positive deliberately.

**Technical:** Institution overlap and incident similarity are distinct systems. Overlap is a *notification* (CROSS_BUREAU_COORDINATION alert) — it makes no claim about the case substance. Incident linkage goes through rules R1–R7 requiring (a) a minimum of 3 supporting evidence points (`SAME_INCIDENT_MIN_SUPPORT=3`), (b) explicit conflict channels (R3 date-gap > 60 days; R6 distinct incident references) that *block* linkage, and (c) automatic abstention (INSUFFICIENT_EVIDENCE) when evidence is thin or missing. Seeded pair 003↔004 verifies this: same institution, dates 202 days apart → NO_RELATIONSHIP_ESTABLISHED with named conflicting evidence. Human decision required; DISPOSED is terminal.

---

**Q2. Why rules instead of AI/ML for the matching engine?**

**Short:** This domain is legal-adjacent and decision-making must be explainable line-by-line. A hallucinating LLM or a black-box score is unacceptable when an officer's decision goes on record.

**Technical:** Every assessment emits named supporting/conflicting/missing evidence items, a deterministic rule version (currently `1.1.0`) and an evidence fingerprint hash — anyone can recompute and verify a historical decision reflects what the engine actually saw. Rules are expandable (R7 = document-hash match) without retraining, and each rule has negative-path tests. We reserve LLM/classifier upgrades for *assist* features (summaries) — never for the verdict path.

---

**Q3. What happens when evidence is simply not there — do you guess?**

**Short:** No. The engine **abstains**: it reports INSUFFICIENT_EVIDENCE with an explicit list of *what is missing* ("no explicit incident reference in one record", "no explicit incident date"), and the reviewer has a first-class **Defer** action with a mandatory rationale.

**Technical:** The abstain list is data — it feeds the review UI (a caution banner explains the engine abstained and suggests Defer, while a truly insufficient match without review stays flagged for follow-up). Deferral decisions are append-only preserved across engine recomputation. Seed scenario DEMO-CASE-005↔006 demonstrates this end-to-end and is pinned by regression tests.

---

**Q4. How is a human review decision kept safe when the engine recalcs?**

**Short:** Recommendations recomputing never touch recorded decisions. The pair's human verdict, rationale, evidence fingerprint and rule version are retained until a *human* changes them.

**Technical:** `relationship_reviews` is append-only history; `POST /relationships/recompute` re-evaluates *unreviewed* pairs only (PENDING_REVIEW or none). For reviewed pairs, recompute updates nothing human — verified by `test_human_decision_preserved_across_recompute`: a CONFIRMED pair re-seeded with altered data still returns the recorded CONFIRMED + rationale, and the evidence_hash remains the fingerprint of the decision.

---

**Q5. Show me your role security actually enforced server-side, not just hidden buttons.**

**Short:** Every endpoint declares its allowed roles with one `require_roles(...)` dependency; tests and live direct-API probes exercise it with all four demo accounts.

**Technical:** Live probe results (2026-11-03, direct HTTP, UI bypassed): REVIEWER → 403 on case create/mutate/demo-reset; READ_ONLY_MANAGER → 403 on case mutate, alert acknowledge, recompute; BUREAU_OFFICER → 403 on relationship review; authorised paths return 200 only for their roles. `test_workflow.py::test_role_enforcement` codifies the matrix in CI. Tokens are signed + expiring; passwords PBKDF2-hashed; admins cannot see plaintext passwords.

---

**Q6. What database do you run in production — and prove it?**

**Short and honest:** The system is *engine-portable* and both engines run the full test suite here in the sandbox: 101/101 pass on SQLite (default dev path) AND 101/101 on PostgreSQL 16.2 (pgserver-bundled). The one honest limitation: a real Windows-side PostgreSQL install (TCP) is documented as NOT VERIFIED — our PG verification used a local unix-socket server.

**Technical:** `INSTITRACE_DATABASE_URL` env selects the engine; Alembic migrations run against both (`alembic current` → `c5d6e7f8a103` head, zero drift); SQLAlchemy handles dialect specifics (window/normalized code is portable; only SQLite gets the `PRAGMA foreign_keys=ON` hook). Report at `docs/test-report.md` records both runs verbatim.

---

**Q7. Can the demo be reset/reproduced for a fair evaluation?**

**Short:** Yes — `python -m app.seed --reset` rebuilds the exact synthetic dataset (15 institutions, 40 cases, 36 assessments, 27–29 alerts) with a fixed random seed and pinned dates; the demo script runs identically off this deterministic seed every time.

**Technical:** Seed uses `INSTITRACE_SEED_PIN_DAYS` (default pinned to a specific day so ageing/alert thresholds don't drift with wall-clock), generates 40 cases across bureaus with scripted overlap scenarios (A: confirmable pair; B: false-positive pair; C: insufficient-evidence pair; D/E/F/G: lifecycle + escalation variants). `--reset` is explicit opt-in; production use never seeds.

---

**Q8. How do you handle a mis-disposed or wrongly coordinated case — is history lost?**

**Short:** Never. Business history (case actions, transfers, disposals) and audit history are separate append-only stores. Transfers don't erase provenance; DISPOSED is terminal and cannot be re-opened.

**Technical:** `case_actions` rows record every status change with actor + timestamp + remarks, separate from `audit_events` (login, reset, alert ack, review) whose router exposes no mutation endpoints at all. `VALID_TRANSITIONS` enforces the legal state machine — DISPOSED→anything = 422. Transfer keeps the original institution row and creates a `transfer_records` entry; the audit saw both. Regression: `test_transfer_*`, `test_disposed_is_terminal`, `test_audit_endpoint_is_read_only`.

---

**Q9. What does "no duplicate alerts on recompute" actually guarantee?**

**Short:** Running the alert engine one time or a hundred times produces the same alert set — acknowledging an alert tomorrow doesn't surface a fresh identical alert after re-evaluation.

**Technical:** Every alert carries a unique `dedupe_key` (e.g. `PAIR:5:7`, `CASE:31:OVERDUE`); evaluation is an upsert on that key — new evidence updates the existing row instead of inserting a copy. DB constraint enforces uniqueness; `test_repeat_recompute_creates_no_duplicates` runs the evaluator twice and asserts identical alert IDs and counts. PSI lifecycle (OPEN→ACKNOWLEDGED→RESOLVED) is likewise transition-guarded (`/psi-alert-lifecycle` tests ×8).

---

**Q10. How do your numbers and reports stay truthful?**

**Short:** Every dashboard figure is computed live from the DB and every metric carries its definition on the page; the report CSVs are generated from the same queries, verified row-for-row.

**Technical:** `test_dashboard_summary_matches_database` recomputes the summary in raw SQL and compares; ageing buckets sum exactly equals `non-disposed` rows in the DB (verified live: 29 = 29); CSV export header + filter provenance lines are asserted (`test_csv_export_structure_and_filters`) and formula-injection (`=`, `+`, `-`, `@` leading cells) is escaped. All reports are deterministic with the pinned seed.

---

**Q11. What is your biggest honest limitation?**

**Short:** Three, and we put them in writing: (1) email/SMS dispatch is simulated (in-app alerts only — SIH scope allows this); (2) real AICTE SSO/AD authentication is demo-grade (documented); (3) the quarterly analytics *view* derives from monthly data rather than a separate chart. All three are in `docs/known-limitations.md` — we prefer honest NOT VERIFIED labels over invented verification.

**Technical:** In all three cases the *data* keeps the contract (alert rows carry the event + delivery-state columns for future dispatchers; auth tokens are real signed JWT-style tokens with expiry; month granularity in trends is quarter-composable), so closing each gap is an iteration, not a redesign.

---

**Q12. Could an officer quietly bury an overdue case by disposing it?**

**Short:** No — disposal requires remarks, is recorded with actor + timestamp in append-only history, escalated cases show their escalation record, and a disposal that doesn't resolve the underlying evidence leaves that pair's coordination alert open.

**Technical:** `DISPOSED` transition validates remarks presence; every disposal writes both a `case_actions` row and an audit event; an institution with disposed-but-flagged pairs still surfaces the relationship assessment (status is case-status-independent). The Nov‑2024 guideline rationale (21-day target, appellate escalation) is mirrored in our escalation-alert pipeline (`OVERDUE` → `ESCALATION_REQUIRED`).

---

**Q13. Why did you hard-require dates/rules like YYYY-MM-DD in narratives? Isn't that brittle with real complaint text?**

**Short:** We deliberately require structured, verifiable fields (incident reference codes vs incident dates parsed from a standard shape). When free text lacks the structured pattern, the engine correctly *abstains* rather than guesses — a demo narrative is one place we trade recall for precision, because false coordination is worse.

**Technical:** Narrative parsers (`text_utils`) extract (a) AICTE incident refs (`INC-\d{4}-\d+`), (b) proceedings refs, (c) dates in strict ISO shape *with an incident-cue word nearby* — preventing receipt/disposal dates from being misread as incident dates. Case-insensitive phrasing ("Incident dated" vs "incident dated") is handled. This is a portfolio placeholder: production NLP is a documented extension that *feeds* these structured slots, never bypasses the abstention gate.

---

**Q14. What does your 101-test backend suite actually protect?**

**Short:** The matching rules, the alert lifecycle, role authorization at HTTP level, state-machine legality, CSV/export correctness, decision preservation, auth session lifecycle — i.e., everything an honest evaluator would try to break on stage.

**Technical:** Suites: matching R1–R7 scenario + unit (18), alert lifecycle + PSI (5+8), workflow/roles/transitions (workflow ≈ 12), deadlines with pinned clock (6), review-decision lifecycle (4), matching-scenario regression (8), API reliability incl. our new defect-B regression (12), misc. Frontend adds 27 vitest tests (API client + auth-session lifecycle + components + defect-D regression). Every fix this campaign added a failing-then-passing regression test — none removed.

---

**Q15. Is it multi-bureau ready for AICTE specifically?**

**Short:** Yes — the seeded bureaus are the AICTE shapes (Regulation Bureau, PGRC, EVC-equivalent), cases carry `bureau_id`, alerts link bureaus, and the dashboard aggregates by bureau workload.

**Technical:** Extend/add a bureau = one row; institution-to-bureau overlap detection is DB-generic; the portal's "Bureau workload" panel groups by `bureaus.name`. Reports table (institution-wise, bureau-wise, region-wise, status-wise, ageing, disposal, overlaps) is what an AICTE nodal officer actually consumes; CSV exports carry the filter provenance in the header block for auditability.

---

**Q16. Will your UI soul survive the demo — antialiased fonts aside, what changed visually for SIH?**

**Short:** The portal was redesigned to the *government* house-style: Gazette-style masthead, deep-navy/saffron/India-green tricolour accent, compact e-governance chrome, dense data tables, and the "Open Government Data"-style utility links a citizen expects on an Indian government portal header.

**Technical:** Hand-authored CSS scale variables + `styles.css` semantic tokens; no component-library dump. Login exposes the four demo roles as one-click chips *because this is a demo* (flagged on-screen as synthetic demo data). Colour contrast ≥ WCAG AA on body copy; alert severity has non-colour indicators too.

---

**Q17. If you had 24 more hours, what one thing ships, and what one thing do you *not* touch?**

**Short:** Ship: email/SMS dispatch adapter behind the existing alert-row contract (data already carries everything needed). Not touch: matching thresholds and any human decision recorded by a reviewer — both are correctness anchors; we enumerated this as an explicit constraint in our change policy.

**Technical:** Dispatch adapter = one `alert_dispatch` service consuming the same rows the PSI lifecycle already produces (no schema change). Threshold changes are *migration-gated, evidence-versioned, and require a migration + dataset re-baseline + reviewer re-attestation* — you can't quietly raise match rates by sliding a number. This is why the demo dataset, the engine threshold, and the recorded human decisions are all part of the same frozen release artifact (source + tests + docs + ZIP checksum).
