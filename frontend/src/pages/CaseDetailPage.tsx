import { FormEvent, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import {
  AlertOut,
  Assessment,
  CaseDetailOut,
  CaseStatus,
  MetaInfo,
} from '../api/types';
import { useAuth } from '../auth/AuthContext';
import {
  AlertStatusBadge,
  AlertTypeBadge,
  EmptyState,
  ErrorState,
  Loading,
  Modal,
  RelBadge,
  ReviewBadge,
  STATUS_LABELS,
  StatusBadge,
  formatDate,
  formatDateTime,
} from '../components/primitives';

interface DetailResponse {
  case: CaseDetailOut;
  assessments: Assessment[];
  alerts: AlertOut[];
}

const VALID_TRANSITIONS: Record<CaseStatus, CaseStatus[]> = {
  PENDING: ['UNDER_PROCESS', 'DISPOSED', 'TRANSFERRED', 'ESCALATED'],
  UNDER_PROCESS: ['DISPOSED', 'TRANSFERRED', 'ESCALATED'],
  ESCALATED: ['UNDER_PROCESS', 'DISPOSED', 'TRANSFERRED'],
  TRANSFERRED: ['PENDING', 'UNDER_PROCESS'],
  DISPOSED: [],
};

type DialogKind = 'status' | 'transfer' | 'escalate' | 'remark' | 'next' | 'assign' | null;

export default function CaseDetailPage() {
  const { id } = useParams();
  const { canWriteCases } = useAuth();
  const [data, setData] = useState<DetailResponse | null>(null);
  const [meta, setMeta] = useState<MetaInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogKind>(null);

  async function load() {
    setError(null);
    try {
      const [d, m] = await Promise.all([
        api.get<DetailResponse>(`/cases/${id}`),
        api.get<MetaInfo>('/meta'),
      ]);
      setData(d);
      setMeta(m);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load case');
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data || !meta) return <Loading label="Loading case detail…" />;

  const c = data.case;
  const transitions = VALID_TRANSITIONS[c.status];

  return (
    <div>
      <div className="flex-between">
        <h3 style={{ marginTop: 0 }} className="mono">
          {c.case_id}
        </h3>
        <StatusBadge status={c.status} />
      </div>

      {canWriteCases && transitions.length > 0 && (
        <div className="button-row" role="toolbar" aria-label="Case actions">
          <button onClick={() => setDialog('status')}>Update status</button>
          <button className="secondary" onClick={() => setDialog('assign')}>
            Change officer
          </button>
          <button className="warn" onClick={() => setDialog('transfer')}>
            Transfer bureau
          </button>
          {c.status !== 'ESCALATED' && (
            <button className="danger" onClick={() => setDialog('escalate')}>
              Escalate
            </button>
          )}
          <button className="secondary" onClick={() => setDialog('next')}>
            Set next action
          </button>
          <button className="secondary" onClick={() => setDialog('remark')}>
            Add remark
          </button>
        </div>
      )}
      {c.status === 'DISPOSED' && (
        <div className="notice info">This case has been disposed. Disposal is terminal; the record and its history are preserved.</div>
      )}

      <div className="grid two">
        <div className="card">
          <h3>Case metadata</h3>
          <dl className="kv">
            <dt>Subject</dt>
            <dd>{c.subject}</dd>
            <dt>Category</dt>
            <dd>{c.category}</dd>
            <dt>Institution</dt>
            <dd>
              <Link to={`/institutions/${c.institution.id}`}>
                {c.institution.name} ({c.institution.permanent_id})
              </Link>
            </dd>
            <dt>Bureau/Cell</dt>
            <dd>
              {c.bureau.code} — {c.bureau.name}
            </dd>
            <dt>Officer</dt>
            <dd>{c.officer_name || '—'}</dd>
            <dt>Priority</dt>
            <dd>{c.priority}</dd>
            <dt>Receipt date</dt>
            <dd>{formatDate(c.receipt_date)}</dd>
            <dt>Expected disposal</dt>
            <dd>{formatDate(c.expected_disposal_date)}</dd>
            <dt>Actual disposal</dt>
            <dd>{formatDate(c.actual_disposal_date)}</dd>
            <dt>Source record ref</dt>
            <dd className="mono">{c.source_record_ref ?? '—'}</dd>
            <dt>Last action</dt>
            <dd>
              {c.last_action_summary ?? '—'} <br />
              <span className="small">{formatDateTime(c.last_action_at)}</span>
            </dd>
            <dt>Next action</dt>
            <dd>
              {c.next_action ?? '—'} <br />
              <span className="small">due {formatDate(c.next_action_due_date)}</span>
            </dd>
          </dl>
        </div>
        <div className="card">
          <h3>Description</h3>
          <p style={{ lineHeight: 1.55 }}>{c.description || <em>No description recorded.</em>}</p>
          <h3>Alerts linked to this case</h3>
          {data.alerts.length === 0 ? (
            <EmptyState title="No alerts for this case" />
          ) : (
            <ul style={{ paddingLeft: 18, margin: 0 }}>
              {data.alerts.map((a) => (
                <li key={a.id} style={{ marginBottom: 8 }}>
                  <AlertTypeBadge type={a.alert_type} /> <AlertStatusBadge status={a.status} />
                  <div className="small">{a.title}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {data.assessments.length > 0 && (
        <div className="card">
          <h3>Relationship assessments involving this case</h3>
          <table className="data">
            <thead>
              <tr>
                <th>Other case</th>
                <th>Engine recommendation</th>
                <th>Human review</th>
                <th>Reviewed by</th>
              </tr>
            </thead>
            <tbody>
              {data.assessments.map((a) => {
                const other = a.source_case?.id === c.id ? a.candidate_case : a.source_case;
                return (
                  <tr key={a.id}>
                    <td className="mono">
                      {other ? <Link to={`/cases/${other.id}`}>{other.case_id}</Link> : '—'}
                    </td>
                    <td>
                      <RelBadge type={a.relationship_type} />{' '}
                      <span className="small">v{a.rule_version}</span>
                    </td>
                    <td>
                      <ReviewBadge status={a.status} />
                    </td>
                    <td>{a.reviewer_identity ?? '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {c.transfers.length > 0 && (
        <div className="card">
          <h3>Transfer history</h3>
          <table className="data">
            <thead>
              <tr>
                <th>When</th>
                <th>From</th>
                <th>To</th>
                <th>Reason</th>
                <th>Actor</th>
              </tr>
            </thead>
            <tbody>
              {c.transfers.map((t) => (
                <tr key={t.id}>
                  <td>{formatDateTime(t.transferred_at)}</td>
                  <td>
                    {meta.bureaus.find((b) => b.id === t.from_bureau_id)?.code ?? t.from_bureau_id} (
                    {t.from_officer})
                  </td>
                  <td>
                    {meta.bureaus.find((b) => b.id === t.to_bureau_id)?.code ?? t.to_bureau_id} (
                    {t.to_officer})
                  </td>
                  <td>{t.reason}</td>
                  <td>{t.actor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h3>Chronological action history</h3>
        {c.actions.length === 0 ? (
          <EmptyState title="No actions recorded" />
        ) : (
          <ul className="timeline">
            {c.actions.map((a) => (
              <li key={a.id}>
                <div>
                  <strong>{a.action_type}</strong>{' '}
                  {a.from_status && a.to_status && (
                    <span className="small">
                      ({STATUS_LABELS[a.from_status as CaseStatus] ?? a.from_status} →{' '}
                      {STATUS_LABELS[a.to_status as CaseStatus] ?? a.to_status})
                    </span>
                  )}
                </div>
                <div>{a.summary}</div>
                <div className="actor">
                  by {a.actor} · <span className="when">{formatDateTime(a.acted_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {dialog === 'status' && (
        <ActionDialog title="Update status" onClose={() => setDialog(null)}>
          <StatusForm
            current={c.status}
            allowed={transitions}
            onSubmit={async (body) => {
              await api.post(`/cases/${c.id}/status`, body);
              setDialog(null);
              void load();
            }}
          />
        </ActionDialog>
      )}
      {dialog === 'transfer' && (
        <ActionDialog title="Transfer case to another Bureau/Cell" onClose={() => setDialog(null)}>
          <TransferForm
            meta={meta}
            currentBureauId={c.bureau_id}
            onSubmit={async (body) => {
              await api.post(`/cases/${c.id}/transfer`, body);
              setDialog(null);
              void load();
            }}
          />
        </ActionDialog>
      )}
      {dialog === 'escalate' && (
        <ActionDialog title="Escalate case" onClose={() => setDialog(null)}>
          <SimpleReasonForm
            label="Escalation reason"
            minLength={5}
            submitLabel="Escalate"
            tone="danger"
            onSubmit={async (reason) => {
              await api.post(`/cases/${c.id}/escalate`, { reason });
              setDialog(null);
              void load();
            }}
          />
        </ActionDialog>
      )}
      {dialog === 'remark' && (
        <ActionDialog title="Add action / remark" onClose={() => setDialog(null)}>
          <SimpleReasonForm
            label="Action summary"
            minLength={3}
            submitLabel="Add remark"
            onSubmit={async (summary) => {
              await api.post(`/cases/${c.id}/actions`, { summary, action_type: 'REMARK' });
              setDialog(null);
              void load();
            }}
          />
        </ActionDialog>
      )}
      {dialog === 'assign' && (
        <ActionDialog title="Change assigned officer" onClose={() => setDialog(null)}>
          <AssignForm
            onSubmit={async (body) => {
              await api.post(`/cases/${c.id}/assign`, body);
              setDialog(null);
              void load();
            }}
          />
        </ActionDialog>
      )}
      {dialog === 'next' && (
        <ActionDialog title="Set next action / expected disposal" onClose={() => setDialog(null)}>
          <NextActionForm
            current={{ next_action: c.next_action, next_action_due_date: c.next_action_due_date, expected_disposal_date: c.expected_disposal_date }}
            onSubmit={async (body) => {
              await api.post(`/cases/${c.id}/next-action`, body);
              setDialog(null);
              void load();
            }}
          />
        </ActionDialog>
      )}
    </div>
  );
}

function ActionDialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <Modal title={title} onClose={onClose}>
      {children}
    </Modal>
  );
}

function useDialogSubmit<T>() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(action: (body: T) => Promise<void>, body: T) {
    setBusy(true);
    setError(null);
    try {
      await action(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed');
      setBusy(false);
    }
  }
  return { busy, error, run };
}

function StatusForm({
  current,
  allowed,
  onSubmit,
}: {
  current: CaseStatus;
  allowed: CaseStatus[];
  onSubmit: (body: { to_status: CaseStatus; summary: string; rationale: string }) => Promise<void>;
}) {
  const [to, setTo] = useState<CaseStatus>(allowed[0]);
  const [summary, setSummary] = useState('');
  const [rationale, setRationale] = useState('');
  const { busy, error, run } = useDialogSubmit<Parameters<typeof onSubmit>[0]>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (summary.trim().length < 3) {
      setSummary('');
      return;
    }
    await run(onSubmit, { to_status: to, summary, rationale });
  }

  return (
    <form onSubmit={submit}>
      {error && <div className="notice error">{error}</div>}
      <p className="small">
        Current status: <StatusBadge status={current} />
      </p>
      <div className="form-grid">
        <div>
          <label htmlFor="s-to">New status</label>
          <select id="s-to" value={to} onChange={(e) => setTo(e.target.value as CaseStatus)}>
            {allowed.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label htmlFor="s-summary">Action summary *</label>
          <input
            id="s-summary"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder={to === 'DISPOSED' ? 'Disposal order / outcome' : 'What was done'}
            required
            minLength={3}
          />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label htmlFor="s-rationale">Rationale (recorded in audit trail)</label>
          <textarea id="s-rationale" rows={2} value={rationale} onChange={(e) => setRationale(e.target.value)} />
        </div>
      </div>
      {to === 'DISPOSED' && (
        <p className="notice warn">Disposal is terminal. The case record and full history are preserved, and a disposal date is recorded.</p>
      )}
      <div className="button-row">
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Confirm status change'}
        </button>
      </div>
    </form>
  );
}

function TransferForm({
  meta,
  currentBureauId,
  onSubmit,
}: {
  meta: MetaInfo;
  currentBureauId: number;
  onSubmit: (body: { to_bureau_id: number; to_officer_name: string; reason: string }) => Promise<void>;
}) {
  const targets = meta.bureaus.filter((b) => b.id !== currentBureauId);
  const [toBureau, setToBureau] = useState(String(targets[0]?.id ?? ''));
  const [officer, setOfficer] = useState('');
  const [reason, setReason] = useState('');
  const { busy, error, run } = useDialogSubmit<Parameters<typeof onSubmit>[0]>();

  async function submit(e: FormEvent) {
    e.preventDefault();
    await run(onSubmit, { to_bureau_id: Number(toBureau), to_officer_name: officer, reason });
  }

  return (
    <form onSubmit={submit}>
      {error && <div className="notice error">{error}</div>}
      <p className="small">
        Transferring preserves the full history and marks the case TRANSFERRED — it is never
        silently disposed. The receiving bureau re-accepts the case.
      </p>
      <div className="form-grid">
        <div>
          <label htmlFor="t-bureau">To Bureau/Cell</label>
          <select id="t-bureau" value={toBureau} onChange={(e) => setToBureau(e.target.value)}>
            {targets.map((b) => (
              <option key={b.id} value={b.id}>
                {b.code} — {b.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="t-officer">Receiving officer *</label>
          <input id="t-officer" value={officer} onChange={(e) => setOfficer(e.target.value)} required minLength={2} />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label htmlFor="t-reason">Transfer reason *</label>
          <textarea id="t-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} required minLength={5} />
        </div>
      </div>
      <div className="button-row">
        <button type="submit" className="warn" disabled={busy}>
          {busy ? 'Transferring…' : 'Confirm transfer'}
        </button>
      </div>
    </form>
  );
}

function SimpleReasonForm({
  label,
  minLength,
  submitLabel,
  tone,
  onSubmit,
}: {
  label: string;
  minLength: number;
  submitLabel: string;
  tone?: 'danger';
  onSubmit: (text: string) => Promise<void>;
}) {
  const [text, setText] = useState('');
  const { busy, error, run } = useDialogSubmit<string>();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void run(onSubmit, text);
      }}
    >
      {error && <div className="notice error">{error}</div>}
      <label htmlFor="reason-input">{label}</label>
      <textarea
        id="reason-input"
        rows={3}
        style={{ width: '100%', marginTop: 6 }}
        value={text}
        onChange={(e) => setText(e.target.value)}
        required
        minLength={minLength}
      />
      <div className="button-row">
        <button type="submit" className={tone ?? ''} disabled={busy}>
          {busy ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  );
}

function AssignForm({
  onSubmit,
}: {
  onSubmit: (body: { officer_name: string; summary: string }) => Promise<void>;
}) {
  const [officer, setOfficer] = useState('');
  const [summary, setSummary] = useState('');
  const { busy, error, run } = useDialogSubmit<Parameters<typeof onSubmit>[0]>();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void run(onSubmit, { officer_name: officer, summary });
      }}
    >
      {error && <div className="notice error">{error}</div>}
      <div className="form-grid">
        <div>
          <label htmlFor="a-officer">New officer name *</label>
          <input id="a-officer" value={officer} onChange={(e) => setOfficer(e.target.value)} required minLength={2} />
        </div>
        <div>
          <label htmlFor="a-summary">Summary *</label>
          <input id="a-summary" value={summary} onChange={(e) => setSummary(e.target.value)} required minLength={3} />
        </div>
      </div>
      <div className="button-row">
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Change officer'}
        </button>
      </div>
    </form>
  );
}

function NextActionForm({
  current,
  onSubmit,
}: {
  current: {
    next_action: string | null;
    next_action_due_date: string | null;
    expected_disposal_date: string | null;
  };
  onSubmit: (body: {
    next_action: string;
    next_action_due_date: string | null;
    expected_disposal_date: string | null;
  }) => Promise<void>;
}) {
  const [nextAction, setNextAction] = useState(current.next_action ?? '');
  const [due, setDue] = useState(current.next_action_due_date ?? '');
  const [expected, setExpected] = useState(current.expected_disposal_date ?? '');
  const { busy, error, run } = useDialogSubmit<Parameters<typeof onSubmit>[0]>();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void run(onSubmit, {
          next_action: nextAction,
          next_action_due_date: due || null,
          expected_disposal_date: expected || null,
        });
      }}
    >
      {error && <div className="notice error">{error}</div>}
      <div className="form-grid">
        <div style={{ gridColumn: '1 / -1' }}>
          <label htmlFor="n-action">Next action *</label>
          <input id="n-action" value={nextAction} onChange={(e) => setNextAction(e.target.value)} required minLength={3} />
        </div>
        <div>
          <label htmlFor="n-due">Next action due date</label>
          <input id="n-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        </div>
        <div>
          <label htmlFor="n-exp">Expected disposal date</label>
          <input id="n-exp" type="date" value={expected} onChange={(e) => setExpected(e.target.value)} />
        </div>
      </div>
      <div className="button-row">
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Update next action'}
        </button>
      </div>
    </form>
  );
}
