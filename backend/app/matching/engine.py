"""INSTITRACE explainable rule-based matching engine.

Design contract (see docs/matching-engine.md):
  * Same institution does NOT mean same incident.
  * Similar wording alone does NOT establish an incident relationship.
  * Missing evidence is NOT negative evidence.
  * "No relationship established from available evidence" != "No relationship exists."
  * Automated output is a RECOMMENDATION for human review - it never merges,
    closes or disposes complaints.

Rules (stable names, engine version stamped on every assessment):
  R1_SHARED_INCIDENT_REFERENCE   v1  weight +3
  R2_SHARED_PROCEEDING_REFERENCE v1  weight +2
  R3_INCIDENT_DATE_COMPATIBILITY v1  weight +1 / conflict flag
  R4_EXPLICIT_CASE_CROSS_REFERENCE v1 procedural link hint
  R5_DETAIL_CORROBORATION        v1  weight +1 (weak, never sufficient alone)
  R6_DISTINCT_INCIDENT_REFERENCES v1 conflict flag
"""
from dataclasses import dataclass, field
from datetime import date

from ..models import ComplaintCase, RelationshipType
from . import text_utils as tu

# Decision thresholds for engine version 1.x
DATE_COMPATIBLE_WINDOW_DAYS = 14
DATE_CONFLICT_WINDOW_DAYS = 60
TEXT_CORROBORATION_THRESHOLD = 0.5
SAME_INCIDENT_MIN_SUPPORT = 3


@dataclass
class CaseFacts:
    case_pk: int
    case_id: str
    institution_id: int
    bureau_id: int
    status: str
    category: str
    incident_references: set[str]
    proceeding_references: set[str]
    incident_dates: set[date]
    cross_case_references: set[str]
    token_set: set[str]
    source_record_ref: str | None
    has_minimal_detail: bool


@dataclass
class PairAssessment:
    relationship_type: RelationshipType
    supporting_evidence: list[dict] = field(default_factory=list)
    conflicting_evidence: list[dict] = field(default_factory=list)
    missing_evidence: list[dict] = field(default_factory=list)
    rules_fired: list[str] = field(default_factory=list)
    score: int | None = None


def extract_facts(case: ComplaintCase) -> CaseFacts:
    text = f"{case.subject}\n{case.description}"
    refs = tu.incident_refs(text)
    procs = tu.proceeding_refs(text)
    token_set = tu.tokens(text)
    return CaseFacts(
        case_pk=case.id,
        case_id=case.case_id,
        institution_id=case.institution_id,
        bureau_id=case.bureau_id,
        status=case.status.value,
        category=case.category,
        incident_references=refs,
        proceeding_references=procs,
        incident_dates=tu.incident_dates(text),
        cross_case_references=tu.case_refs(text),
        token_set=token_set,
        source_record_ref=case.source_record_ref,
        has_minimal_detail=bool(token_set) and len(case.description or "") >= 40,
    )


def _ev(rule: str, version: str, detail: str, weight: int | None = None) -> dict:
    item = {"rule": rule, "rule_version": version, "detail": detail}
    if weight is not None:
        item["weight"] = weight
    return item


def evaluate_pair(
    case_a: ComplaintCase, case_b: ComplaintCase, rule_version: str
) -> PairAssessment | None:
    """Evaluate two cases for an incident/procedural relationship.

    Returns None when the cases concern DIFFERENT institutions: cross-
    institution pairs are not assessed at all (similar wording across
    institutions never yields a stored relationship).
    """
    if case_a.id == case_b.id:
        raise ValueError("A case cannot be assessed against itself")
    if case_a.institution_id != case_b.institution_id:
        return None

    a = extract_facts(case_a)
    b = extract_facts(case_b)
    support: list[dict] = []
    conflicts: list[dict] = []
    missing: list[dict] = []
    fired: list[str] = []
    score = 0

    # --- R4: explicit cross-reference to the other case id -----------------
    r4_hit = a.case_id in b.cross_case_references or b.case_id in a.cross_case_references

    # --- R1: shared incident reference (strong) -----------------------------
    shared_inc = (a.incident_references & b.incident_references) or (
        a.source_record_ref
        and b.source_record_ref
        and {a.source_record_ref} & {b.source_record_ref}
    )
    if shared_inc:
        fired.append("R1_SHARED_INCIDENT_REFERENCE")
        support.append(
            _ev(
                "R1_SHARED_INCIDENT_REFERENCE",
                rule_version,
                f"Both cases cite the same incident reference(s): {sorted(shared_inc)}.",
                weight=3,
            )
        )
        score += 3

    # --- R2: shared proceeding reference (medium) ---------------------------
    shared_proc = a.proceeding_references & b.proceeding_references
    if shared_proc:
        fired.append("R2_SHARED_PROCEEDING_REFERENCE")
        support.append(
            _ev(
                "R2_SHARED_PROCEEDING_REFERENCE",
                rule_version,
                f"Both cases cite the same proceeding reference(s): {sorted(shared_proc)}.",
                weight=2,
            )
        )
        score += 2

    # --- R3: incident date compatibility ------------------------------------
    if a.incident_dates and b.incident_dates:
        delta = min(abs((da - db).days) for da in a.incident_dates for db in b.incident_dates)
        fired.append("R3_INCIDENT_DATE_COMPATIBILITY")
        if delta <= DATE_COMPATIBLE_WINDOW_DAYS:
            support.append(
                _ev(
                    "R3_INCIDENT_DATE_COMPATIBILITY",
                    rule_version,
                    f"Incident dates are within {delta} day(s) of each other.",
                    weight=1,
                )
            )
            score += 1
        elif delta > DATE_CONFLICT_WINDOW_DAYS:
            conflicts.append(
                _ev(
                    "R3_INCIDENT_DATE_COMPATIBILITY",
                    rule_version,
                    f"Incident dates differ by {delta} days (beyond {DATE_CONFLICT_WINDOW_DAYS}-day window).",
                )
            )
            score -= 2

    # --- R6: distinct incident references (conflict) ------------------------
    if a.incident_references and b.incident_references and not shared_inc:
        fired.append("R6_DISTINCT_INCIDENT_REFERENCES")
        conflicts.append(
            _ev(
                "R6_DISTINCT_INCIDENT_REFERENCES",
                rule_version,
                "Both cases cite incident references but share none "
                f"({sorted(a.incident_references)} vs {sorted(b.incident_references)}).",
            )
        )
        score -= 2

    # --- R5: detail corroboration (weak - never sufficient alone) -----------
    sim = tu.jaccard(a.token_set, b.token_set)
    if a.category == b.category and sim >= TEXT_CORROBORATION_THRESHOLD:
        fired.append("R5_DETAIL_CORROBORATION")
        support.append(
            _ev(
                "R5_DETAIL_CORROBORATION",
                rule_version,
                f"Same category ({a.category}) with consistent incident details "
                f"(token overlap {sim:.2f}). Corroborating only - not sufficient alone.",
                weight=1,
            )
        )
        score += 1

    # --- missing evidence inventory -----------------------------------------
    if not a.incident_references or not b.incident_references:
        missing.append(
            {
                "item": "INCIDENT_REFERENCE",
                "detail": "At least one case record has no explicit incident reference "
                "(e.g. INC-YYYY-NNN). Absence is not treated as negative evidence.",
            }
        )
    if not a.incident_dates or not b.incident_dates:
        missing.append(
            {
                "item": "INCIDENT_DATE",
                "detail": "At least one case record has no explicit incident date.",
            }
        )
    if not a.has_minimal_detail or not b.has_minimal_detail:
        missing.append(
            {
                "item": "INCIDENT_DETAILS",
                "detail": "At least one case record has sparse free-text detail, "
                "limiting corroboration.",
            }
        )

    # --- R4 outcome ----------------------------------------------------------
    if r4_hit and not shared_inc and not shared_proc:
        fired.append("R4_EXPLICIT_CASE_CROSS_REFERENCE")
        support.append(
            _ev(
                "R4_EXPLICIT_CASE_CROSS_REFERENCE",
                rule_version,
                "One case record explicitly references the other case ID "
                "(procedural continuation / appeal pattern).",
                weight=1,
            )
        )
        return PairAssessment(
            relationship_type=RelationshipType.PROCEDURAL_LINK,
            supporting_evidence=support,
            conflicting_evidence=conflicts,
            missing_evidence=missing,
            rules_fired=fired,
            score=score or 1,
        )

    # --- decision table ------------------------------------------------------
    if score >= SAME_INCIDENT_MIN_SUPPORT and not conflicts:
        return PairAssessment(
            relationship_type=RelationshipType.POTENTIAL_SAME_INCIDENT,
            supporting_evidence=support,
            conflicting_evidence=conflicts,
            missing_evidence=missing,
            rules_fired=fired,
            score=score,
        )

    if not support and not conflicts and missing:
        # Not enough information to say anything - abstain explicitly.
        return PairAssessment(
            relationship_type=RelationshipType.INSUFFICIENT_EVIDENCE,
            supporting_evidence=support,
            conflicting_evidence=conflicts,
            missing_evidence=missing,
            rules_fired=fired,
            score=None,
        )

    # Positive evidence is contradicted, or evidence exists but is too weak.
    # "No relationship established from available evidence" - the available
    # evidence does NOT prove the relationship is false.
    return PairAssessment(
        relationship_type=RelationshipType.NO_RELATIONSHIP_ESTABLISHED,
        supporting_evidence=support,
        conflicting_evidence=conflicts,
        missing_evidence=missing,
        rules_fired=fired,
        score=score if score != 0 else None,
    )


def pair_key(case_id_a: str, case_id_b: str) -> str:
    """Stable, order-independent key for a case pair."""
    a, b = sorted([case_id_a, case_id_b])
    return f"{a}|{b}"
