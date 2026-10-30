# Rule-Based Matching Engine (v1.0.0)

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
| `R1_SHARED_INCIDENT_REFERENCE` | 1.0.0 | Both cases cite the same `INC-YYYY-NNN` ref (or identical `source_record_ref`) | +3 (strong) |
| `R2_SHARED_PROCEEDING_REFERENCE` | 1.0.0 | Both cases cite the same `PROC-YYYY-NNN` ref | +2 |
| `R3_INCIDENT_DATE_COMPATIBILITY` | 1.0.0 | Both records carry explicit incident dates | ≤14 days apart ⇒ +1; >60 days apart ⇒ conflict |
| `R4_EXPLICIT_CASE_CROSS_REFERENCE` | 1.0.0 | One case text references the other case ID | drives `PROCEDURAL_LINK` (alone) |
| `R5_DETAIL_CORROBORATION` | 1.0.0 | Same category AND token-set overlap ≥ 0.5 | +1 (weak, **never sufficient alone**) |
| `R6_DISTINCT_INCIDENT_REFERENCES` | 1.0.0 | Both cite incident refs but share none | conflict recorded |

## Decision table (engine v1.x)

Let `support` = total positive weight, `conflicts` = number of contradiction flags.

| Condition | Outcome |
| --- | --- |
| R4 fired and no shared refs (R1/R2) | `PROCEDURAL_LINK` |
| `support ≥ 3` and `conflicts = 0` | `POTENTIAL_SAME_INCIDENT` |
| `support = 0` and `conflicts = 0` and missing items exist | `INSUFFICIENT_EVIDENCE` |
| otherwise | `NO_RELATIONSHIP_ESTABLISHED` (evidence lists explain the tension) |

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
10. **Idempotence**: `pair_key` and alert `dedupe_key` uniqueness prevent duplicates on rerun
    (`test_repeat_recompute_creates_no_duplicates`).

## Thresholds (prototype defaults)

| Constant | Value | Rationale |
| --- | --- | --- |
| `DATE_COMPATIBLE_WINDOW_DAYS` | 14 | same episode reported within a fortnight |
| `DATE_CONFLICT_WINDOW_DAYS` | 60 | dates >2 months apart suggest distinct episodes |
| `TEXT_CORROBORATION_THRESHOLD` | 0.5 | Jaccard overlap of content tokens |
| `SAME_INCIDENT_MIN_SUPPORT` | 3 | requires at least one strong shared reference |

These are demo-tuned constants, documented and versioned — not official AICTE parameters.
