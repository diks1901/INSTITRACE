import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { AlertOut, Assessment, CaseOut, InstitutionOut } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import {
  AlertStatusBadge,
  AlertTypeBadge,
  DemoBadge,
  EmptyState,
  ErrorState,
  Loading,
  RelBadge,
  ReviewBadge,
  StatusBadge,
  formatDate,
} from '../components/primitives';
import { InstitutionForm } from './InstitutionsPage';

interface DetailResponse {
  institution: InstitutionOut;
  cases: CaseOut[];
  alerts: AlertOut[];
  assessments: Assessment[];
  summary: {
    total_cases: number;
    active_cases: number;
    open_coordination_alerts: number;
    pending_reviews: number;
  };
}

export default function InstitutionDetailPage() {
  const { id } = useParams();
  const { canAdmin } = useAuth();
  const [data, setData] = useState<DetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showEdit, setShowEdit] = useState(false);

  async function load() {
    setError(null);
    try {
      setData(await api.get<DetailResponse>(`/institutions/${id}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load institution');
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <Loading label="Loading institution profile…" />;

  const { institution: inst, cases, alerts, assessments, summary } = data;

  return (
    <div>
      <div className="flex-between">
        <h3 style={{ marginTop: 0 }}>
          {inst.name} <DemoBadge />
        </h3>
        {canAdmin && (
          <button className="secondary" onClick={() => setShowEdit(true)}>
            Edit institution
          </button>
        )}
      </div>

      <div className="card">
        <dl className="kv">
          <dt>AICTE Permanent ID</dt>
          <dd className="mono">{inst.permanent_id}</dd>
          <dt>Address</dt>
          <dd>{inst.address || '—'}</dd>
          <dt>Region / State / District</dt>
          <dd>
            {inst.region} · {inst.state} · {inst.district ?? '—'}
          </dd>
          <dt>Institution type</dt>
          <dd>{inst.institution_type ?? '—'}</dd>
          <dt>Consolidated history</dt>
          <dd>
            {summary.total_cases} case(s) · {summary.active_cases} active
          </dd>
          <dt>Cross-bureau alerts</dt>
          <dd>{summary.open_coordination_alerts} open</dd>
          <dt>Relationship reviews</dt>
          <dd>{summary.pending_reviews} awaiting review</dd>
        </dl>
      </div>

      <div className="card">
        <h3>Consolidated case history</h3>
        {cases.length === 0 ? (
          <EmptyState title="No cases registered for this institution" />
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Case ID</th>
                <th>Subject</th>
                <th>Category</th>
                <th>Status</th>
                <th>Bureau</th>
                <th>Received</th>
                <th>Expected disposal</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id}>
                  <td className="mono">
                    <Link to={`/cases/${c.id}`}>{c.case_id}</Link>
                  </td>
                  <td>{c.subject}</td>
                  <td>{c.category}</td>
                  <td>
                    <StatusBadge status={c.status} />
                  </td>
                  <td>{c.bureau.code}</td>
                  <td>{formatDate(c.receipt_date)}</td>
                  <td>{formatDate(c.expected_disposal_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="grid two">
        <div className="card">
          <h3>Alerts for this institution</h3>
          {alerts.length === 0 ? (
            <EmptyState title="No alerts" />
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Cases</th>
                  <th>Raised</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <AlertTypeBadge type={a.alert_type} />
                    </td>
                    <td>
                      <AlertStatusBadge status={a.status} />
                    </td>
                    <td className="mono">{a.case_ids.join(', ')}</td>
                    <td>{formatDate(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="card">
          <h3>Relationship assessments involving this institution</h3>
          {assessments.length === 0 ? (
            <EmptyState title="No assessments" />
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Pair</th>
                  <th>Recommendation</th>
                  <th>Review</th>
                </tr>
              </thead>
              <tbody>
                {assessments.map((a) => {
                  const src = cases.find((c) => c.id === a.source_case_id);
                  const cand = cases.find((c) => c.id === a.candidate_case_id);
                  return (
                    <tr key={a.id}>
                      <td className="mono">
                        {src ? (
                          <Link to={`/cases/${src.id}`}>{src.case_id}</Link>
                        ) : (
                          `#${a.source_case_id}`
                        )}{' '}
                        ↔{' '}
                        {cand ? (
                          <Link to={`/cases/${cand.id}`}>{cand.case_id}</Link>
                        ) : (
                          `#${a.candidate_case_id}`
                        )}{' '}
                        <Link to="/coordination" className="small">
                          review
                        </Link>
                      </td>
                      <td>
                        <RelBadge type={a.relationship_type} />
                      </td>
                      <td>
                        <ReviewBadge status={a.status} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showEdit && (
        <InstitutionForm
          initial={inst}
          onClose={() => setShowEdit(false)}
          onSaved={() => {
            setShowEdit(false);
            void load();
          }}
        />
      )}
    </div>
  );
}
