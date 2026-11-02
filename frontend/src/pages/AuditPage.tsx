import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, buildQuery } from '../api/client';
import { AuditEventOut, Page } from '../api/types';
import {
  EmptyState,
  ErrorState,
  Loading,
  Pager,
  formatDateTime,
} from '../components/primitives';

const EVENT_TYPES = [
  'CASE_CREATED', 'CASE_UPDATED', 'CASE_STATUS_CHANGED', 'CASE_TRANSFERRED',
  'CASE_ASSIGNMENT_CHANGED', 'CASE_ACTION_ADDED', 'CASE_NEXT_ACTION_UPDATED',
  'ASSESSMENT_CREATED', 'ASSESSMENT_REVIEWED', 'ASSESSMENT_RECOMPUTED',
  'ALERT_ACKNOWLEDGED', 'ALERT_RESOLVED', 'ALERTS_REFRESHED',
  'INSTITUTION_CREATED', 'INSTITUTION_UPDATED', 'DEMO_RESET_REQUESTED',
];

export default function AuditPage() {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<Page<AuditEventOut> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const eventType = params.get('event_type') ?? '';
  const entityId = params.get('entity_id') ?? '';
  const actor = params.get('actor') ?? '';
  const page = Number(params.get('page') ?? '1');

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(
        await api.get<Page<AuditEventOut>>(
          `/audit-events${buildQuery({ event_type: eventType, entity_id: entityId, actor, page, page_size: 30 })}`,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load audit events');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventType, entityId, actor, page]);

  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('page');
    setParams(next);
  }

  return (
    <div>
      <h3 style={{ marginTop: 0 }}>Audit Trail</h3>
      <div className="notice info">
        Append-only record of significant changes and decisions. The application API exposes no
        edit or delete route for audit events. Credentials and personal data are never logged.
      </div>
      <div className="card">
        <div className="filters">
          <div>
            <label htmlFor="a-event">Event type</label>
            <select id="a-event" value={eventType} onChange={(e) => update('event_type', e.target.value)}>
              <option value="">All event types</option>
              {EVENT_TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="a-entity">Entity ID (e.g. case ID)</label>
            <input id="a-entity" value={entityId} onChange={(e) => update('entity_id', e.target.value)} placeholder="DEMO-CASE-001" />
          </div>
          <div>
            <label htmlFor="a-actor">Actor</label>
            <input id="a-actor" value={actor} onChange={(e) => update('actor', e.target.value)} placeholder="admin" />
          </div>
          {(eventType || entityId || actor) && (
            <button className="secondary" onClick={() => setParams(new URLSearchParams())}>
              Reset filters
            </button>
          )}
        </div>
        {loading ? (
          <Loading />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState title="No audit events match" />
        ) : (
          <>
            <table className="data">
              <thead>
                <tr>
                  <th>When (UTC)</th>
                  <th>Event</th>
                  <th>Entity</th>
                  <th>Actor</th>
                  <th>Summary / rationale</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((e) => (
                  <tr key={e.id}>
                    <td className="mono">{formatDateTime(e.created_at)}</td>
                    <td>
                      <span className="rule-tag">{e.event_type}</span>
                    </td>
                    <td className="mono">
                      {e.entity_type} / {e.entity_id}
                    </td>
                    <td>{e.actor}</td>
                    <td>
                      {e.summary}
                      {e.rationale && (
                        <div className="small">
                          <em>{e.rationale}</em>
                        </div>
                      )}
                      {(e.before_state || e.after_state) && (
                        <button className="secondary" style={{ fontSize: 11, padding: '2px 8px' }} onClick={() => setExpanded(expanded === e.id ? null : e.id)}>
                          {expanded === e.id ? 'hide state ▲' : 'state ▼'}
                        </button>
                      )}
                      {expanded === e.id && (
                        <div className="grid two" style={{ marginTop: 6 }}>
                          <pre className="small mono" style={{ whiteSpace: 'pre-wrap' }}>
                            {JSON.stringify(e.before_state, null, 2)}
                          </pre>
                          <pre className="small mono" style={{ whiteSpace: 'pre-wrap' }}>
                            {JSON.stringify(e.after_state, null, 2)}
                          </pre>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => update('page', String(p))} />
          </>
        )}
      </div>
    </div>
  );
}
