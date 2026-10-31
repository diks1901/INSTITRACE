import { useEffect, useState } from 'react';
import { api, getToken } from '../api/client';
import { MetaInfo } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { ErrorState, Loading } from '../components/primitives';

export default function SettingsPage() {
  const { canAdmin, user } = useAuth();
  const [meta, setMeta] = useState<MetaInfo | null>(null);
  const [health, setHealth] = useState<{ status: string; database: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [resetResult, setResetResult] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const [m, h] = await Promise.all([
        api.get<MetaInfo>('/meta'),
        api.get<{ status: string; database: string }>('/health'),
      ]);
      setMeta(m);
      setHealth(h);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function demoReset() {
    if (
      !window.confirm(
        'Demo reset wipes ALL current data and reseeds the synthetic dataset. Continue?',
      )
    )
      return;
    setResetting(true);
    setResetResult(null);
    try {
      const resp = await fetch('/api/v1/admin/demo-reset', {
        method: 'POST',
        headers: { Authorization: `Bearer ${getToken() ?? ''}` },
      });
      if (!resp.ok) throw new Error(`Reset failed (${resp.status})`);
      setResetResult('Demo data reset complete. Dashboard, cases and alerts were reseeded.');
      await load();
    } catch (err) {
      setResetResult(err instanceof Error ? err.message : 'Reset failed');
    } finally {
      setResetting(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!meta) return <Loading />;

  return (
    <div>
      <h3 style={{ marginTop: 0 }}>Settings &amp; System Status</h3>
      <div className="grid two">
        <div className="card">
          <h3>Application</h3>
          <dl className="kv">
            <dt>Application version</dt>
            <dd className="mono">{meta.app_version}</dd>
            <dt>Rule-engine version</dt>
            <dd className="mono">{meta.rule_engine_version}</dd>
            <dt>Database mode</dt>
            <dd className="mono">
              {meta.database_mode} ({health?.database === 'reachable' ? 'reachable' : 'unreachable'})
            </dd>
            <dt>Deadline warning window</dt>
            <dd>{meta.deadline_warning_days} day(s) — prototype default, not an official AICTE SLA</dd>
            <dt>Escalation overdue threshold</dt>
            <dd>{meta.escalation_overdue_days} day(s) — prototype default</dd>
            <dt>Current user</dt>
            <dd>
              {user?.display_name} ({user?.role})
            </dd>
          </dl>
        </div>
        <div className="card">
          <h3>Reference configuration</h3>
          <dl className="kv">
            <dt>Bureaus / Cells</dt>
            <dd>
              {meta.bureaus.map((b) => (
                <div key={b.id}>
                  <span className="chip">{b.code}</span> {b.name}
                </div>
              ))}
            </dd>
            <dt>Case statuses</dt>
            <dd>{meta.statuses.join(' · ')}</dd>
            <dt>Alert types</dt>
            <dd>{meta.alert_types.join(' · ')}</dd>
            <dt>Assessment outcomes</dt>
            <dd>{meta.relationship_types.join(' · ')}</dd>
            <dt>Review states</dt>
            <dd>{meta.assessment_statuses.join(' · ')}</dd>
          </dl>
        </div>
      </div>

      <div className="card">
        <h3>Demo-data disclosure</h3>
        <p>{meta.demo_data_notice}</p>
        <ul>
          <li>All institutions (DEMO-INS-xxx), cases (DEMO-CASE-xxx) and users are synthetic.</li>
          <li>Authentication is a labelled local demo mode — not production security, and not real AICTE authentication.</li>
          <li>No external services (email/SMS/AI APIs) are used; everything runs offline.</li>
        </ul>
      </div>

      {canAdmin && (
        <div className="card">
          <h3>Demo maintenance (ADMIN)</h3>
          <p className="small">
            Explicitly reset the demo database: all current rows are wiped and the deterministic
            synthetic dataset is reseeded. This cannot be undone.
          </p>
          <button className="danger" onClick={demoReset} disabled={resetting}>
            {resetting ? 'Resetting…' : 'Reset demo data'}
          </button>
          {resetResult && <div className="notice info" style={{ marginTop: 10 }}>{resetResult}</div>}
        </div>
      )}

      <div className="card">
        <h3>Local diagnostics</h3>
        <dl className="kv">
          <dt>API base path</dt>
          <dd className="mono">/api/v1 (proxied by the dev server)</dd>
          <dt>API documentation</dt>
          <dd className="mono">backend /docs (Swagger UI)</dd>
          <dt>Health check</dt>
          <dd className="mono">GET /api/v1/health → {health ? health.status : '…'}</dd>
        </dl>
      </div>
    </div>
  );
}
