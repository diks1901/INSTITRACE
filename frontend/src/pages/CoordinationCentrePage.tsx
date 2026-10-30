import { FormEvent, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, buildQuery } from '../api/client';
import { AlertOut, Assessment, AssessmentStatus, MetaInfo, Page } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import {
  AlertStatusBadge,
  AlertTypeBadge,
  EmptyState,
  ErrorState,
  Loading,
  Modal,
  Pager,
  RelBadge,
  ReviewBadge,
  formatDateTime,
} from '../components/primitives';

const TABS = [
  { id: 'alerts', label: 'Cross-Bureau Alerts' },
  { id: 'deadlines', label: 'Deadline & Ops Alerts' },
  { id: 'reviews', label: 'Pending Incident Reviews' },
  { id: 'ambiguous', label: 'Ambiguous / Insufficient Evidence' },
  { id: 'confirmed', label: 'Confirmed' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'deferred', label: 'Deferred' },
  { id: 'resolved', label: 'Resolved Alerts' },
];

export default function CoordinationCentrePage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'alerts';
  const { canReview, canAdmin } = useAuth();
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  async function recompute() {
    setBusy(true);
    setNotice(null);
    try {
      const match = await api.post<{
        assessments_created: number;
        assessments_updated: number;
        alerts_created: number;
        human_decisions_preserved: number;
      }>('/relationships/recompute');
      const alerts = await api.post<{ alerts_created: number; alerts_auto_resolved: number }>(
        '/alerts/refresh',
      );
      setNotice(
        `Recomputation complete: ${match.assessments_created} new assessment(s), ` +
          `${match.assessments_updated} refreshed, ${match.human_decisions_preserved} human decision(s) ` +
          `preserved; ${alerts.alerts_created} new alert(s), ${alerts.alerts_auto_resolved} auto-resolved.`,
      );
      setReloadKey((k) => k + 1);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Recompute failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex-between">
        <h3 style={{ marginTop: 0 }}>Overlap &amp; Coordination Centre</h3>
        {(canReview || canAdmin) && (
          <button className="secondary" onClick={recompute} disabled={busy}>
            {busy ? 'Recomputing…' : '↻ Recompute rules & alerts'}
          </button>
        )}
      </div>
      <div className="notice info">
        <strong>Cross-bureau alerts</strong> flag institutions with active cases in multiple
        bureaus — an <em>institution-level</em> coordination signal only. <strong>Incident
        assessments</strong> are explainable rule-engine recommendations about the underlying
        incident; they become decisions only after human review. One never silently implies the
        other.
      </div>
      {notice && <div className="notice info">{notice}</div>}
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? 'active' : ''}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set('tab', t.id);
              next.delete('page');
              setParams(next);
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <TabContent tab={tab} reloadKey={reloadKey} />
    </div>
  );
}

function TabContent({ tab, reloadKey }: { tab: string; reloadKey: number }) {
  switch (tab) {
    case 'alerts':
      return <AlertsTab types="CROSS_BUREAU_COORDINATION,POTENTIAL_SAME_INCIDENT" statuses="OPEN,ACKNOWLEDGED" reloadKey={reloadKey} />;
    case 'deadlines':
      return (
        <AlertsTab
          types="PENDING_REMINDER,APPROACHING_DEADLINE,OVERDUE,ESCALATION_REQUIRED"
          statuses="OPEN,ACKNOWLEDGED"
          reloadKey={reloadKey}
        />
      );
    case 'resolved':
      return <AlertsTab types="" statuses="RESOLVED" reloadKey={reloadKey} showResolved />;
    case 'reviews':
      return <AssessmentsTab status="PENDING_REVIEW" reloadKey={reloadKey} />;
    case 'ambiguous':
      return <AssessmentsTab status="PENDING_REVIEW" relType="INSUFFICIENT_EVIDENCE" reloadKey={reloadKey} />;
    case 'confirmed':
      return <AssessmentsTab status="CONFIRMED" reloadKey={reloadKey} />;
    case 'rejected':
      return <AssessmentsTab status="REJECTED" reloadKey={reloadKey} />;
    case 'deferred':
      return <AssessmentsTab status="DEFERRED" reloadKey={reloadKey} />;
    default:
      return null;
  }
}

function AlertsTab({
  types,
  statuses,
  reloadKey,
  showResolved = false,
}: {
  types: string;
  statuses: string;
  reloadKey: number;
  showResolved?: boolean;
}) {
  const { canReview, canWriteCases } = useAuth();
  const canAct = canReview || canWriteCases;
  const [items, setItems] = useState<AlertOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolveTarget, setResolveTarget] = useState<AlertOut | null>(null);
  const [ackTarget, setAckTarget] = useState<AlertOut | null>(null);

  async function loadAll(): Promise<AlertOut[]> {
    const typeList = types ? types.split(',') : [];
    const statusList = statuses.split(',');
    if (typeList.length === 0) {
      const acc: AlertOut[] = [];
      for (const s of statusList) {
        const page = await api.get<Page<AlertOut>>(
          `/alerts${buildQuery({ status: s, page_size: 200 })}`,
        );
        acc.push(...page.items);
      }
      return acc;
    }
    const acc: AlertOut[] = [];
    for (const t of typeList) {
      for (const s of statusList) {
        const page = await api.get<Page<AlertOut>>(
          `/alerts${buildQuery({ alert_type: t, status: s, page_size: 200 })}`,
        );
        acc.push(...page.items);
      }
    }
    const seen = new Set<number>();
    return acc.filter((a) => (seen.has(a.id) ? false : (seen.add(a.id), true)));
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const all = await loadAll();
      all.sort((a, b) => b.created_at.localeCompare(a.created_at));
      setItems(all);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load alerts');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [types, statuses, reloadKey]);

  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (items.length === 0)
    return <EmptyState title="No alerts in this view" hint="Run the alert refresh to re-evaluate." />;

  return (
    <div>
      {items.map((a) => (
        <div className="card" key={a.id}>
          <div className="flex-between">
            <div>
              <AlertTypeBadge type={a.alert_type} /> <AlertStatusBadge status={a.status} />
              <h4 style={{ margin: '8px 0 6px' }}>{a.title}</h4>
            </div>
            {canAct && a.status === 'OPEN' && !showResolved && (
              <div className="button-row">
                <button className="secondary" onClick={() => setAckTarget(a)}>
                  Acknowledge
                </button>
                <button className="ok" onClick={() => setResolveTarget(a)}>
                  Resolve…
                </button>
              </div>
            )}
            {canAct && a.status === 'ACKNOWLEDGED' && !showResolved && (
              <div className="button-row">
                <button className="ok" onClick={() => setResolveTarget(a)}>
                  Resolve…
                </button>
              </div>
            )}
          </div>
          <p style={{ margin: '4px 0 8px', lineHeight: 1.5 }}>{a.description}</p>
          <div className="chip-list">
            {a.case_ids.map((cid) => (
              <span key={cid} className="chip">
                {cid}
              </span>
            ))}
          </div>
          <p className="small" style={{ marginTop: 8 }}>
            Raised {formatDateTime(a.created_at)}
            {a.acknowledged_by && ` · acknowledged by ${a.acknowledged_by} ${formatDateTime(a.acknowledged_at)}`}
            {a.resolved_by && ` · resolved by ${a.resolved_by} ${formatDateTime(a.resolved_at)}`}
          </p>
          {a.resolution_note && (
            <div className="notice info" style={{ marginBottom: 0 }}>
              <strong>Resolution note:</strong> {a.resolution_note}
            </div>
          )}
        </div>
      ))}

      {ackTarget && (
        <Modal title="Acknowledge alert" onClose={() => setAckTarget(null)}>
          <NoteForm
            label="Acknowledgement note (optional)"
            submitLabel="Acknowledge"
            onSubmit={async (note) => {
              await api.post(`/alerts/${ackTarget.id}/acknowledge`, { note: note || null });
              setAckTarget(null);
              void load();
            }}
          />
        </Modal>
      )}
      {resolveTarget && (
        <Modal title="Resolve alert" onClose={() => setResolveTarget(null)}>
          <NoteForm
            label="Resolution note (required - min 5 characters)"
            required
            submitLabel="Resolve alert"
            onSubmit={async (note) => {
              await api.post(`/alerts/${resolveTarget.id}/resolve`, { resolution_note: note });
              setResolveTarget(null);
              void load();
            }}
          />
        </Modal>
      )}
    </div>
  );
}

function NoteForm({
  label,
  required,
  submitLabel,
  onSubmit,
}: {
  label: string;
  required?: boolean;
  submitLabel: string;
  onSubmit: (note: string) => Promise<void>;
}) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      onSubmit={async (e: FormEvent) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await onSubmit(note.trim());
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Failed');
          setBusy(false);
        }
      }}
    >
      {error && <div className="notice error">{error}</div>}
      <label htmlFor="note-field">{label}</label>
      <textarea
        id="note-field"
        rows={3}
        style={{ width: '100%', marginTop: 6 }}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        required={required}
        minLength={required ? 5 : 0}
      />
      <div className="button-row">
        <button type="submit" className="ok" disabled={busy}>
          {busy ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  );
}

function AssessmentsTab({
  status,
  relType,
  reloadKey,
}: {
  status: AssessmentStatus;
  relType?: string;
  reloadKey: number;
}) {
  const { canReview } = useAuth();
  const [data, setData] = useState<Page<Assessment> | null>(null);
  const [bureauCodes, setBureauCodes] = useState<Map<number, string>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [reviewTarget, setReviewTarget] = useState<Assessment | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    api
      .get<MetaInfo>('/meta')
      .then((m) => setBureauCodes(new Map(m.bureaus.map((b) => [b.id, b.code]))))
      .catch(() => setBureauCodes(new Map()));
  }, []);

  async function load(p = page) {
    setLoading(true);
    setError(null);
    try {
      setData(
        await api.get<Page<Assessment>>(
          `/relationships${buildQuery({ status, relationship_type: relType, page: p, page_size: 10 })}`,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load assessments');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(1);
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, relType, reloadKey]);

  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data || data.items.length === 0)
    return <EmptyState title="No assessments in this view" hint="Run a recomputation after adding cases." />;

  return (
    <div>
      {data.items.map((a) => (
        <div className="card" key={a.id}>
          <div className="flex-between">
            <div>
              <RelBadge type={a.relationship_type} /> <ReviewBadge status={a.status} />{' '}
              <span className="small mono">rules v{a.rule_version}</span>
              {a.score !== null && a.score !== undefined && (
                <span className="small"> · evidence score {a.score} (heuristic, not a probability)</span>
              )}
            </div>
            {canReview && a.status === 'PENDING_REVIEW' && (
              <button onClick={() => setReviewTarget(a)}>Review…</button>
            )}
          </div>
          <p style={{ margin: '10px 0 6px' }}>
            <span className="chip">
              {a.source_case ? (
                <Link to={`/cases/${a.source_case.id}`}>{a.source_case.case_id}</Link>
              ) : (
                a.source_case_id
              )}
            </span>{' '}
            ↔{' '}
            <span className="chip">
              {a.candidate_case ? (
                <Link to={`/cases/${a.candidate_case.id}`}>{a.candidate_case.case_id}</Link>
              ) : (
                a.candidate_case_id
              )}
            </span>
            {a.source_case && a.candidate_case && (
              <span className="small" style={{ marginLeft: 8 }}>
                Bureaus: {bureauCodes.get(a.source_case.bureau_id) ?? a.source_case.bureau_id} vs{' '}
                {bureauCodes.get(a.candidate_case.bureau_id) ?? a.candidate_case.bureau_id} ·
                Statuses: {a.source_case.status} / {a.candidate_case.status}
              </span>
            )}
          </p>
          <button className="secondary" onClick={() => setExpanded(expanded === a.id ? null : a.id)}>
            {expanded === a.id ? 'Hide evidence ▲' : 'Show evidence ▼'}
          </button>
          {expanded === a.id && (
            <div className="grid two" style={{ marginTop: 12 }}>
              <div>
                <strong>Supporting evidence</strong>
                {a.supporting_evidence.length === 0 ? (
                  <p className="small">None recorded.</p>
                ) : (
                  <ul className="evidence-list">
                    {a.supporting_evidence.map((ev, i) => (
                      <li key={i}>
                        {ev.rule && <span className="rule-tag">{ev.rule}</span>}
                        {ev.detail}
                      </li>
                    ))}
                  </ul>
                )}
                <strong>Missing information</strong>
                {a.missing_evidence.length === 0 ? (
                  <p className="small">None flagged.</p>
                ) : (
                  <ul className="evidence-list">
                    {a.missing_evidence.map((ev, i) => (
                      <li key={i}>{ev.detail}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <strong>Conflicting / contradictory evidence</strong>
                {a.conflicting_evidence.length === 0 ? (
                  <p className="small">None recorded.</p>
                ) : (
                  <ul className="evidence-list">
                    {a.conflicting_evidence.map((ev, i) => (
                      <li key={i}>
                        {ev.rule && <span className="rule-tag">{ev.rule}</span>}
                        {ev.detail}
                      </li>
                    ))}
                  </ul>
                )}
                {a.rules_fired.length > 0 && (
                  <p className="small">
                    Rules fired: {a.rules_fired.map((r) => <span key={r} className="rule-tag">{r}</span>)}
                  </p>
                )}
                {a.reviewer_identity && (
                  <div className="notice info" style={{ marginTop: 8 }}>
                    <strong>Reviewer decision:</strong> {a.reviewer_identity} · {formatDateTime(a.reviewed_at)}
                    <br />
                    <em>{a.reviewer_rationale}</em>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      ))}
      <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => { setPage(p); void load(p); }} />
      {reviewTarget && (
        <Modal title="Record review decision" onClose={() => setReviewTarget(null)}>
          <ReviewForm
            assessment={reviewTarget}
            onDone={() => {
              setReviewTarget(null);
              void load();
            }}
          />
        </Modal>
      )}
    </div>
  );
}

function ReviewForm({ assessment, onDone }: { assessment: Assessment; onDone: () => void }) {
  const [decision, setDecision] = useState<'CONFIRMED' | 'REJECTED' | 'DEFERRED'>('CONFIRMED');
  const [rationale, setRationale] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post(`/relationships/${assessment.id}/review`, { decision, rationale });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Review failed');
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      {error && <div className="notice error">{error}</div>}
      <p className="small">
        The automated recommendation is <strong><RelBadge type={assessment.relationship_type} /></strong>.
        Your decision is recorded separately, survives recomputation and enters the audit trail.
        Confirming a relationship never merges or closes either complaint.
      </p>
      <div className="form-grid">
        <div>
          <label htmlFor="r-decision">Decision</label>
          <select id="r-decision" value={decision} onChange={(e) => setDecision(e.target.value as typeof decision)}>
            <option value="CONFIRMED">Confirm relationship</option>
            <option value="REJECTED">Reject relationship</option>
            <option value="DEFERRED">Defer — need more information</option>
          </select>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label htmlFor="r-rationale">Reviewer rationale * (min 5 characters)</label>
          <textarea id="r-rationale" rows={3} value={rationale} onChange={(e) => setRationale(e.target.value)} required minLength={5} />
        </div>
      </div>
      <div className="button-row">
        <button type="submit" disabled={busy}>
          {busy ? 'Recording…' : 'Record decision'}
        </button>
      </div>
    </form>
  );
}


