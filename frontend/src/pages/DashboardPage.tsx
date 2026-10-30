import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api/client';
import { BureauWorkload, DashboardSummary, TrendMonth } from '../api/types';
import { EmptyState, ErrorState, Loading } from '../components/primitives';

const PIE_COLORS: Record<string, string> = {
  Pending: '#7f8ea3',
  'Under Process': '#2f7fc1',
  Disposed: '#1e7d4f',
  Transferred: '#5b48a4',
  Escalated: '#b3261e',
};

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [workload, setWorkload] = useState<BureauWorkload[]>([]);
  const [trends, setTrends] = useState<TrendMonth[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [s, w, t] = await Promise.all([
        api.get<DashboardSummary>('/dashboard/summary'),
        api.get<BureauWorkload[]>('/dashboard/bureau-workload'),
        api.get<{ monthly: TrendMonth[] }>('/dashboard/trends?months=12'),
      ]);
      setSummary(s);
      setWorkload(w);
      setTrends(t.monthly);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) return <Loading label="Loading dashboard metrics…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!summary) return <EmptyState title="No data" />;

  const metrics = [
    { label: 'Total cases', value: summary.total_cases, tone: '', link: '/cases' },
    { label: 'Pending', value: summary.pending, tone: '', link: '/cases?status=PENDING' },
    { label: 'Under process', value: summary.under_process, tone: 'tone-info', link: '/cases?status=UNDER_PROCESS' },
    { label: 'Disposed', value: summary.disposed, tone: 'tone-ok', link: '/cases?status=DISPOSED' },
    { label: 'Transferred', value: summary.transferred, tone: '', link: '/cases?status=TRANSFERRED' },
    { label: 'Escalated', value: summary.escalated, tone: 'tone-bad', link: '/cases?status=ESCALATED' },
    { label: 'Overdue active', value: summary.overdue_active, tone: 'tone-bad', link: '/cases?overdue=true' },
    {
      label: `Deadline in ≤${summary.deadline_warning_days} days*`,
      value: summary.approaching_deadline,
      tone: 'tone-warn',
      link: '/cases?approaching=true',
    },
    { label: 'Open cross-bureau alerts', value: summary.open_coordination_alerts, tone: 'tone-warn', link: '/coordination?tab=alerts' },
    { label: 'Incident reviews awaiting', value: summary.pending_incident_reviews, tone: 'tone-info', link: '/coordination?tab=reviews' },
  ];

  const pieData = [
    { name: 'Pending', value: summary.pending },
    { name: 'Under Process', value: summary.under_process },
    { name: 'Disposed', value: summary.disposed },
    { name: 'Transferred', value: summary.transferred },
    { name: 'Escalated', value: summary.escalated },
  ].filter((d) => d.value > 0);

  return (
    <div>
      <div className="notice info">
        Metrics below are computed live from the database. * Deadline warnings use the prototype
        threshold of {summary.deadline_warning_days} day(s) — a demo configuration, not an official
        AICTE SLA. Definitions are listed at the bottom.
      </div>

      <div className="grid metrics">
        {metrics.map((m) => (
          <Link to={m.link} key={m.label} style={{ textDecoration: 'none', color: 'inherit' }}>
            <div className={`metric ${m.tone}`}>
              <div className="value">{m.value}</div>
              <div className="label">{m.label}</div>
            </div>
          </Link>
        ))}
      </div>

      <div className="grid two" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>Status distribution</h3>
          {pieData.length === 0 ? (
            <EmptyState title="No cases yet" />
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={85} label>
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={PIE_COLORS[entry.name] ?? '#7f8ea3'} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="card">
          <h3>Bureau workload (active / total)</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={workload}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="code" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="active_cases" name="Active" fill="#b3261e" />
              <Bar dataKey="total_cases" name="Total" fill="#2f7fc1" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <h3>Monthly receipts vs disposals (last 12 months)</h3>
        <ResponsiveContainer width="100%" height={230}>
          <LineChart data={trends}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" fontSize={11} />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="receipts" name="Receipts" stroke="#2f7fc1" />
            <Line type="monotone" dataKey="disposals" name="Disposals" stroke="#1e7d4f" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <h3>Metric definitions</h3>
        <dl className="kv">
          {Object.entries(summary.definitions).map(([key, def]) => (
            <div key={key} style={{ display: 'contents' }}>
              <dt className="mono">{key}</dt>
              <dd>{def}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
