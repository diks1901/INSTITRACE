"""Audit trail recording. Events are appended via this helper only; the API
exposes read access but no edit/delete routes."""
from ..models import AuditEvent


def record_audit(
    db,
    *,
    actor: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    summary: str = "",
    rationale: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    meta: dict | None = None,
    from_clock=None,
) -> AuditEvent:
    event = AuditEvent(
        actor=actor,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        summary=summary,
        rationale=rationale,
        before_state=before,
        after_state=after,
        event_meta=meta,
    )
    if from_clock is not None:  # pragma: no cover - test aid only
        event.created_at = from_clock()
    db.add(event)
    return event
