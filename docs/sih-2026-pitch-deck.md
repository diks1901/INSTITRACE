# SIH 2026 Pitch Deck — INSTITRACE (6 slides)

Team **SONARA** · ID **197721** · Problem Statement **SIH26264** · AICTE · Software / Smart Automation

Each slide below lists the on-slide headline, the visual, and the one-liner the
presenter says. Slides are designed to be readable at a glance; the talking points
stay in the demo script (`docs/demo-script.md`).

---

## Slide 1 — Title

**Text**
- **INSTITRACE** — Institutional Complaint Traceability & Cross‑Bureau Coordination
- Smart India Hackathon 2026 · PS SIH26264 · Team SONARA
- "One institution. Every complaint. Every bureau. One traceable picture."

**Visual**: INSTITRACE logo mark over the government‑style portal header (deep navy / tricolour accent strip).
**Say**: "When one college tops two different AICTE bureaus' complaint lists, nobody sees the overlap today. INSTITRACE makes that overlap impossible to miss — and explainable."

---

## Slide 2 — Problem

**Text**
- Complaints about the *same institution* fragment across bureaus: Regulation Bureau (RB), PGRC, and others receive, log, and dispose complaints in silos.
- Nobody has a consolidated, timeline‑true history per institution.
- Duplicate effort — or worse, *conflicting action* — on what is really one incident.
- Deadlines get missed while the left hand does not know the right hand's case.

**Visual**: three disconnected flow boxes (RB / PGRC / other) each dumping unlinked case files, with a ⚠ between them.
**Say**: "The failure is not effort — it is *visibility*. Officers work hard; the system does not connect their work."

---

## Slide 3 — Solution

**Text**
- **Consolidated institution profile** — every case, every bureau, one audit‑backed timeline.
- **Cross‑bureau coordination alerts** — the moment a second bureau touches the same institution, both sides are told.
- **Explainable same‑incident reasoning** — rules R1–R7 produce *evidence lists*, not black‑box scores; the engine abstains when evidence is thin.
- **Human‑in‑the‑loop decisions** — a reviewer confirms, rejects, or defers with rationale; that decision survives re‑computation forever.

**Visual**: the INSTITRACE screenshot of an institution detail page with the case table + evidence panel inset.
**Say**: "The engine never *decides* anything alone. It drafts; the officer decides; and the reason is recorded, versioned, and fingerprinted."

---

## Slide 4 — Architecture & Safeguards

**Text**
- React + TypeScript portal · FastAPI + SQLAlchemy API · SQLite (dev) / PostgreSQL (production), Alembic migrations.
- **14 domain safeguards**, e.g.:
  - institution overlap ≠ same incident (two separate concepts, never conflated);
  - matching thresholds are fixed, versioned (`rule_version`, evidence hash) — a decision's fingerprint is auditable;
  - append‑only review history; DISPOSED is terminal; audits are read‑only by design;
  - role separation enforced in the API, not just the UI (ADMIN / BUREAU_OFFICER / REVIEWER / READ‑ONLY MANAGER).
- **Defence‑grade QA**: 87 backend + 27 frontend automated tests passing on *both* SQLite and PostgreSQL.

**Visual**: layered architecture diagram (UI → API → services → DB) with a shield column listing the safeguards.
**Say**: "Every safeguard is backed by a failing‑before, passing‑after regression test — the count is on the slide, and it is reproducible."

---

## Slide 5 — Demo Flow (what we will show)

**Text** (3–4 minutes, 6 steps):
1. Dashboard — live metrics computed from the DB (definitions on the page).
2. Institution detail (DEMO‑INS‑001) — consolidated history across bureaus.
3. Cross‑Bureau alert — institution‑level overlap notice, *not* a duplicate claim.
4. Confirmed pair (001 ↔ 002) — R1 shared incident‑ref + R2 proceeding-ref + R3 compatible dates; reviewer confirmation + rationale recorded.
5. **Safeguard pair** (003 ↔ 004) — same institution, but dates months apart (202‑day conflict) and distinct incident refs → engine abstains, reviewer rejects. False‑positive protection, visible.
6. Insufficient‑evidence pair (005 ↔ 006) — engine says "we don't know yet", reviewer defers.

**Visual**: 6‑dot journey strip across the slide bottom, each dot a screenshot thumbnail.
**Say**: "The demo deliberately shows one success, one *rejected* match, and one *abstention* — a real system must handle all three."

---

## Slide 6 — Prior Art, Impact & Roadmap

**Text**
- **Prior art**: CPGRAMS is citizen‑grievance tracking for ministries; it auto‑routes and tracks, but does not detect *cross‑bureau same‑incident* overlap inside one responsive institution domain. AICTE‑specific peers for SIH26264 correlate by keywords; INSTITRACE's evidence‑and‑abstention rule engine + human review + decision preservation is the differentiator (full comparison: `docs/prior-art.md`).
- **Impact for AICTE**: fewer duplicate investigations, no silent conflicting actions, auditable officer accountability, workload‑aware escalation.
- **Roadmap**: production SSO + real AICTE auth; PostgreSQL HA deployment; email/SMS dispatch; quarterly analytics view; NextGen‑style voice/multilingual intake (aligned with the CPGRAMS interoperability roadmap).
- "Compliant by construction: no blockchain, no LLM black boxes, no auto‑merging of cases."

**Visual**: left panel "As‑is" (fragmented) vs right panel "With INSTITRACE" (traced), plus the roadmap timeline.
**Say**: "We built the boring, correct, auditable thing — because grievance systems fail people when they guess. Ours states its evidence, and when evidence is thin, it says so."

---

## Speaker notes & hand‑off

- Full 3–5 minute narration: **`docs/demo-script.md`**.
- 17 prepared judge questions with short + technical answers: **`docs/judge-qa.md`**.
- All figures quoted on slide 4 come from the reproducible test run: **`docs/test-report.md`**.
- Prior‑art sources and the CPGRAMS feature comparison with citations: **`docs/prior-art.md`**.
