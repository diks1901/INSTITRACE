"""Deterministic text utilities for the rule-based matching engine.

No external services, no ML models, fully offline and reproducible.
"""
import re
from datetime import date

INCIDENT_REF_RE = re.compile(r"\bINC-\d{4}-\d{3,}\b")
PROCEEDING_REF_RE = re.compile(r"\bPROC-\d{4}-\d{3,}\b")
CASE_ID_RE = re.compile(r"\bDEMO-CASE-\d{3,}\b")
INCIDENT_DATE_RE = re.compile(r"(?:incident dated|incident on|occurred on)\s+(\d{4}-\d{2}-\d{2})")

STOPWORDS = {
    " complaint", "about", "regarding", "institution", "college", "students",
    "faculty", "case", "from", "with", "that", "this", "have", "been", "were",
    "they", "them", "their", "there", "also", "into", "filed", "received",
    "dated", "incident", "occurred", "alleged", "allegation", "against",
    "under", "bureau", "cell", "submitted", "report", "action", "request",
    "requested", "please", "kindly", "grievance", "stated", "mentioned",
}


def incident_refs(text: str) -> set[str]:
    return set(INCIDENT_REF_RE.findall(text or ""))


def proceeding_refs(text: str) -> set[str]:
    return set(PROCEEDING_REF_RE.findall(text or ""))


def case_refs(text: str) -> set[str]:
    return set(CASE_ID_RE.findall(text or ""))


def incident_dates(text: str) -> set[date]:
    out = set()
    for match in INCIDENT_DATE_RE.findall(text or ""):
        try:
            y, m, d = (int(p) for p in match.split("-"))
            out.add(date(y, m, d))
        except ValueError:  # pragma: no cover - defensive
            continue
    return out


def tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-z]{4,}", (text or "").lower())
    return {t for t in raw if t not in STOPWORDS and not INCIDENT_REF_RE.match(t.upper())}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
