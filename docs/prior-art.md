# Prior-Art Comparison — INSTITRACE vs existing grievance platforms

Prepared for SIH 2026 judgement (PS SIH26264, Team SONARA). All statements about
third-party systems are cited. Statements about INSTITRACE are grounded in this
repository (cite paths shown).

## 1. CPGRAMS (Government flagship, pgportal.gov.in)

CPGRAMS is the Union government's citizen-facing grievance platform connecting all
ministries, states and UTs [1]. Published functional scope:

- one-time citizen registration, complaint filing via portal / app (UMANG) / CSCs,
  with unique registration ID for status tracking [1, 2];
- auto-routing / categorisation: mapping complaints to the last-mile Grievance
  Redressal Officer (GRO) and automatic forwarding to the responsible authority [1, 2];
- 21‑day disposal target under the Aug‑2024 guidelines; appellate escalation to a
  Nodal Appellate Authority within 30 days [1];
- AI/ML for real-time analysis, pattern recognition and systemic-issue identification;
  advanced dashboards and analytics [1, 3];
- NextGen CPGRAMS roadmap: voice registration, chatbot, omni-channel intake,
  22‑language support, AI-enabled validation of *redressal quality*, and detection of
  closures-by-transfer without effective resolution [2];
- scale: 27 lakh grievances/year (2024), avg disposal 15 days (2025), 1.09 lakh GROs
  mapped [1].

### What INSTITRACE adds over the CPGRAMS pattern for the AICTE domain

| Capability | CPGRAMS (public description) | INSTITRACE |
| --- | --- | --- |
| Petition routing | Auto-route complaint → responsible GRO | Bureau assignment + institution-linked consolidation (`app/models complaint_cases.institution_id`, `InstitutionDetailPage`) |
| Overlap awareness | Not published — routing-dup detection happens at intake | **Cross-bureau coordination alert** when ≥2 bureaus hold open cases on one institution (`alert_service.evaluate_alerts`, `CROSS_BUREAU_COORDINATION`) |
| Same-incident reasoning | Not published as an explainable feature | **R1–R7 rule engine** that emits named rules + supporting/conflicting/missing evidence lists and *abstains* (INSUFFICIENT_EVIDENCE) when uncertain (`app/matching/engine.py`) |
| False-positive safety | N/A at published scope | Institution overlap is explicitly NOT same-incident; both surfaced simultaneously with distinct labels (`CoordinationCentrePage` + review dialog) |
| Decision audit | Monthly performance reports at ministry level [1] | Per-decision reviewer rationale, append-only, evidence fingerprint + rule-version, preserved across recomputation (`test_human_decision_preserved_across_recompute`) |
| Redressal-quality validation | NextGen roadmap item (not yet live) | Shipped: escalation alert on **disposal‑by‑transfer** pattern detection is a roadmap peer; PSI lifecycle alerts + audit trail live now |

**Honest line:** CPGRAMS is production, pan-India, citizen-facing for ministries;
INSTITRACE is an AICTE-interior prototype (regulator-side case *intelligence*). We do
not claim to replace CPGRAMS; we solve the coordination problem *inside* one
regulator, which CPGRAMS's published scope does not address.

## 2. Peer SIH 2026 teams (public repos, PS SIH26264)

Public GitHub shows several SIH26264 prototypes. Verified capabilities from their READMEs:

- **InSolver** [4]: canonical AICTE permanent-ID institutional identity; keyword & hybrid
  routing suggestions; cross-cell overlap correlation with **confidence scores**, and an
  explicit "no automatic merge" stance similar to ours.
- **AICTE Sangam** [5]: single-window dashboard; institution-level overlap pop-up on
  complaint entry (`same college, different bureau`). Focuses on the dashboard-view
  (consolidation) rather than incident-level reasoning.
- **AICTE CaseConnect** [6]: complaint monitoring, cross-bureau coordination, and
  *explainable* overlap detection with resolution tracking (closest peer to INSTITRACE).

### INSTITRACE differentiators vs the peer field

1. **Abstention as a first-class outcome.** INSTITRACE never forces a verdict. Thin
   evidence → `INSUFFICIENT_EVIDENCE` + explicit missing-evidence list → human defer
   path. None of the peer READMEs documents an explicit abstain/defer flow.
2. **Decision preservation under recomputation.** A reviewer's confirm/reject/defer
   with rationale survives every re-run of the matching engine — with evidence hash +
   rule version (pair DEMO-CASE-005↔006 DEFERRED is pinned in the seed and by test).
3. **Deterministic rules with named evidence.** No ML black box: R1–R7 each fire or
   don't, with human-readable evidence lines (see `docs/matching-engine.md`).
4. **Dual-engine verified.** 87 backend tests pass on SQLite AND PostgreSQL 16 (pgserver
   harness), zero schema drift (`docs/test-report.md`).
5. **Append-only audit separation.** Two history layers: case *business* history vs
   immutable audit events; the audit router exposes no mutation routes at all.

## 3. Honest positioning in the prior-art landscape

- **NOT novel at the intake layer.** Citizen registration, unique IDs, routing,
  dashboards, ageing reports — well-established (CPGRAMS 7.0 universalisation, 2022 [1]).
- **Novel for the SIH26264 domain:** (a) separating *institution overlap* from
  *same-incident* evidence-based linking while surfacing both; (b) the abstention +
  documented-defer contract; (c) per-decision evidence fingerprint preservation across
  recomputation. To our knowledge (public peer repos + published CPGRAMS docs) this
  combination is not deployed in any competitor.
- **Deliberately conservative:** no LLM-generated rationale (avoids hallucination in a
  legal-adjacent process); no auto-merge (avoids irreversible data loss); no blockchain
  (no benefit over signed audit logs at this scale).

## Sources

1. PIB Backgrounder, *Centralised Public Grievance Redress and Monitoring System
   (CPGRAMS)*, posted 09 Aug 2026 — https://www.pib.gov.in/PressReleasePage.aspx?PRID=2296724
2. PIB document companion PDF (doc202689948801) — NextGen CPGRAMS feature list —
   https://static.pib.gov.in/WriteReadData/specificdocs/documents/2026/aug/doc202689948801.pdf
3. PIB India on X (PIB article 2087175545801084948) — citizen-facing CPGRAMS capabilities.
4. `abulaasvh/InSolver` (README) — https://github.com/abulaasvh/InSolver
5. `Sumit-Dss/sih_62` "AICTE Sangam" (README) — https://github.com/Sumit-Dss/sih_62
6. `namit27y-dotcom/aicte-caseconnect` (README) — https://github.com/namit27y-dotcom/aicte-caseconnect

*Citation policy: third-party features are described only as published/promoted by
their own sources; we do not assert un-features ("X does not do Y") for any system that
is behind authentication — those rows are marked "not published" rather than "absent".*
