# Demo Script — 3–5 minute judge flow

Prerequisites: backend on :8000, frontend on :5173, synthetic data seeded (see README).
Sign in as `admin` / `InstiTrace#Demo1`.

## Step 1 — Establish the problem (Dashboard, ~30 s)

Open **Dashboard**. Point out: 40 synthetic cases across RB / PGRC / EVC, status distribution,
bureau workload bars, the **Open cross-bureau alerts** metric and **Incident reviews awaiting**.
Say: *"Every number here is computed live from the database — the definitions are listed at the
bottom of this page."*

## Step 2 — Institution view (~30 s)

Open **Institutions → Sunrise Institute of Technology (DEMO-INS-001)**. Show the consolidated
case history, the open cross-bureau alert count and pending relationship reviews for this one
institution.

## Step 3 — Cross-bureau coordination (~45 s)

Open **DEMO-CASE-001** (RB) and **DEMO-CASE-002** (PGRC) from that institution. Then open
**Coordination Centre → Cross-Bureau Alerts**: *"Potential Cross-Bureau Coordination Required -
Sunrise Institute of Technology"*. Read the alert text: it says the same institution is handled
by multiple bureaus — and explicitly does **not** claim the cases are duplicates.

## Step 4 — Same-incident reasoning (~45 s)

Go to **Confirmed** tab. Open the DEMO-CASE-001 ↔ DEMO-CASE-002 assessment. Show evidence:
`R1_SHARED_INCIDENT_REFERENCE` (both cite INC-2025-0042), compatible incident dates,
corroborating details, the recorded reviewer confirmation and rationale.

## Step 5 — False-positive safeguard (~30 s)

**Rejected** tab → DEMO-CASE-003 ↔ DEMO-CASE-004 (same institution: Lakeview). Show the
cross-bureau alert exists *for the institution* while the incident assessment recorded
**conflicting evidence** (distinct incident references, dates months apart) and a human
rejection. Institution-level alert; incident-level rejection. Two concepts, never conflated.

## Step 6 — Uncertainty (~45 s)

**Pending Incident Reviews** / **Ambiguous** tab → DEMO-CASE-005 ↔ DEMO-CASE-006
(Riverbend). Show `INSUFFICIENT_EVIDENCE` with the **missing information** list. Live action:
click **Review… → Defer — need more information**, type *"Need original complainant statement"*.
Then click **↻ Recompute rules & alerts** and point out: *"0 new assessments, 0 duplicate
alerts, 3 human decisions preserved."*

## Step 7 — Accountability (~45 s)

Open **DEMO-CASE-013** (PGRC, approaching deadline). Transfer it to EVC with officer + reason.
Show: status becomes **Transferred** (not disposed), transfer history table has from/to,
timeline gained a TRANSFER entry. Then **Audit Trail** → filter `DEMO-CASE-013` → the
`CASE_TRANSFERRED` audit event with before/after state and the acting user.

## Step 8 — Operational usefulness (~45 s)

**Coordination Centre → Deadline & Ops Alerts**: the overdue case (DEMO-CASE-012, also flagged
*Escalation required*), the approaching-deadline case (DEMO-CASE-013), and a pending reminder.
Acknowledge one alert; resolve one with a note. Then **Reports & Exports** → *Bureau-wise
workload* → **Export CSV**, and *Pending-case ageing*. Mention: disposed cases with past
deadlines correctly produce no overdue alert (DEMO-CASE-014).

## Closing line

*"One institution view. Separate case records. Evidence-backed suggestions. Coordinated human
decisions. Complete traceability. Everything you saw runs offline on synthetic data, and the
same endpoints are documented in Swagger at /docs."*
