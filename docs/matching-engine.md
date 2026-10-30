# Rule-Based Matching Engine (v1.1.0)

`backend/app/matching/engine.py` — deterministic, explainable, offline. No LLMs, no paid APIs,
no external services. Every produced assessment is stamped with the engine version and lists the
exact rules that fired.

## Why rules instead of "AI"

The problem statement allows "explainable rule-based or AI-assisted identification". We chose a
fully deterministic rule engine because a hackathon demo must be **reproducible offline**, and a
regulator-facing tool must be able to **show its reasons**. A heuristic agreement score is exposed
but is explicitly **not** a probability; no calibration or validation exists to support one.

## Outcomes

| Outcome | Meaning | Where stored |
| --- | --- | --- |
| `POTENTIAL_SAME_INCIDENT` | Evidence supports one underlying incident — recommendation only, never auto-acts | `relationship_assessments` |
| `PROCEDURAL_LINK` | Cases are connected procedurally (appeal/continuation/cross-reference), not necessarily one incident | `relationship_assessments` |
| `NO_RELATIONSHIP_ESTABLISHED` | Available evidence does not establish a relationship (**not** proof none exists) | `relationship_assessments` |
| `INSUFFICIENT_EVIDENCE` | Records too thin to conclude anything — explicit abstention | `relationship_assessments` |
| `CROSS_BUREAU_COORDINATION` | Institution-level: active cases of one institution in ≥2 bureaus. **Says nothing about incidents** | `coordination_alerts` |

## Rules

| Rule (stable name) | Ver | Condition | Weight / effect |
| --- | --- | --- | --- |
| `R1_SHARED_INCIDENT_REFERENCE` | 1.1.0 | Both cases cite the same explicit incident reference `INC-YYYY-NNN` parsed from text | +3 (strong) |
| `R2_SHARED_PROCEEDING_REFERENCE` | 1.1.0 | Both cases cite the same `PROC-YYYY-NNN` ref | +2 |
| `R3_INCIDENT_DATE_COMPATIBILITY` | 1.1.0 | Both records carry explicit incident dates | ≤14 days apart ⇒ +1; >60 days apart ⇒ conflict |
| `R4_EXPLICIT_CASE_CROSS_REFERENCE` | 1.1.0 | One case text references the other case ID | drives `PROCEDURAL_LINK` (alone) |
| `R5_DETAIL_CORROBORATION` | 1.1.0 | Same category AND token-set overlap ≥ 0.5 | +1 (weak, **never sufficient alone**) |
| `R6_DISTINCT_INCIDENT_REFERENCES` | 1.1.0 | Both cite incident refs but share none | conflict recorded |
| `R7_SHARED_SOURCE_RECORD_PROVENANCE` | 1.1.0 | Identical `source_record_ref` (same uploaded/source record — *provenance*, not an incident) | **0 weight**; drives `PROCEDURAL_LINK` only |

> **v1.1.0 change (evidence-type correctness):** in v1.0.0 an identical `source_record_ref`
> counted as an "incident reference" inside R1, so mere provenance (both complaints imported
> from the same source record) could reach the `POTENTIAL_SAME_INCIDENT` threshold. That
> conflated two different concepts: a *source-record reference* says where a record came from;
> an *incident reference* says what happened. v1.1.0 separates them: provenance is recorded as
> typed evidence (`SOURCE_RECORD_PROVENANCE`) with zero weight and, on its own, yields
> `PROCEDURAL_LINK`. Regression tests: `test_shared_source_record_ref_is_procedural_never_psi`,
> `test_shared_source_ref_plus_similar_text_still_not_psi`,
> `test_different_source_record_refs_not_procedural` (all in `backend/tests/test_matching.py`).

## Decision table (engine v1.1.0)

Let `support` = total positive weight, `conflicts` = number of contradiction flags.

| Condition | Outcome |
| --- | --- |
| R4 fired and no shared incident/proceeding refs (R1/R2) | `PROCEDURAL_LINK` |
| R7 fired (shared source record) and no shared incident/proceeding refs (R1/R2) | `PROCEDURAL_LINK` |
| `support ≥ 3` and `conflicts = 0` | `POTENTIAL_SAME_INCIDENT` |
| `support = 0` and `conflicts = 0` and missing items exist | `INSUFFICIENT_EVIDENCE` |
| otherwise | `NO_RELATIONSHIP_ESTABLISHED` (evidence lists explain the tension) |

Every evidence item is typed (`INCIDENT_REFERENCE`, `PROCEEDING_REFERENCE`,
`DATE_COMPATIBILITY`, `TEXT_CORROBORATION`, `CASE_CROSS_REFERENCE`,
`SOURCE_RECORD_PROVENANCE`) so the UI and API consumers can see *which kind of evidence*
drove the recommendation.

Pairs across **different institutions are never assessed** — similar wording between different
institutions produces no relationship record at all (fixture Scenario E).

## Safeguards (all covered by tests in `backend/tests/`)

1. **Same institution ≠ same incident.** Institution equality only scopes *which pairs are
   eligible for assessment*; it contributes zero supporting weight.
2. **Similar text alone can never reach the threshold** (`test_text_similarity_alone_insufficient`):
   R5 alone yields support 1 < 3.
3. **Different case IDs never prove different incidents** — hence assessments, not auto-merging.
4. **Appeals/continuations** are `PROCEDURAL_LINK`, not duplicates (R4).
5. **Missing evidence is not negative evidence**: absent refs are recorded under
   `missing_evidence` and produce abstention, contributing no negative weight.
6. **Stale/thin data weakens conclusions**: sparse records force `INSUFFICIENT_EVIDENCE`.
7. **"No relationship established from available evidence"** wording is used deliberately —
   it never claims a relationship is impossible.
8. **Automated output never mutates cases**: assessments/alerts are recommendations displayed
   alongside — separately labeled from — human decisions.
9. **Human decisions persist across recomputation** (`test_human_decision_preserved_across_recompute`):
   recompute refreshes automated fields only; reviewer, rationale, decision and timestamp remain,
   and prior versions stay visible in the audit trail.
10. **Idempotence**: assessment `pair_key` uniqueness and the alert lifecycle (one ACTIVE alert
    per condition key) prevent duplicates on rerun
    (`test_repeat_recompute_creates_no_duplicates`).
11. **Provenance ≠ incident**: a shared `source_record_ref` is recorded as typed provenance
    evidence with zero support weight and can only produce a `PROCEDURAL_LINK` — never a
    same-incident recommendation (v1.1.0, see the rule table note).
12. **Evidence-versioned review**: every review decision is pinned to the exact evidence hash +
    snapshot the reviewer saw (`relationship_assessments.reviewed_evidence_hash`,
    `evidence_snapshot`). If a later recomputation changes that material evidence, the preserved
    decision is flagged `requires_rereview` ("Outdated decision — re-review" in the UI) with an
    `ASSESSMENT_EVIDENCE_CHANGED` audit event — never silently erased, never displayed as
    covering new evidence (`backend/tests/test_evidence_review.py`).
13. **Alert recurrence**: alerts track condition *occurrences*
    (`coordination_alerts.logical_key` + `occurrence`, `alert_condition_state`). When a resolved
    condition disappears and later recurs, a **new active alert occurrence** is opened while the
    resolved row remains as history; repeated evaluations never duplicate the active occurrence
    (`backend/tests/test_alert_lifecycle.py`). A human who resolves an alert while the condition
    is still active suppresses silent respawning for as long as the condition persists.

## Thresholds (prototype defaults)

| Constant | Value | Rationale |
| --- | --- | --- |
| `DATE_COMPATIBLE_WINDOW_DAYS` | 14 | same episode reported within a fortnight |
| `DATE_CONFLICT_WINDOW_DAYS` | 60 | dates >2 months apart suggest distinct episodes |
| `TEXT_CORROBORATION_THRESHOLD` | 0.5 | Jaccard overlap of content tokens |
| `SAME_INCIDENT_MIN_SUPPORT` | 3 | requires at least one strong shared reference |

These are demo-tuned constants, documented and versioned — not official AICTE parameters.
