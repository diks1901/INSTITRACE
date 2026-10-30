import { useEffect, useState } from 'react';
import { api, buildQuery, getToken } from '../api/client';
import { ReportData } from '../api/types';
import { EmptyState, ErrorState, Loading } from '../components/primitives';

const REPORTS = [
  { id: 'institutions', label: 'Institution-wise cases', filterable: true },
  { id: 'bureaus', label: 'Bureau-wise workload', filterable: false },
  { id: 'regions', label: 'Region-wise cases', filterable: false },
  { id: 'statuses', label: 'Status-wise distribution', filterable: false },
  { id: 'ageing', label: 'Pending-case ageing', filterable: false },
  { id: 'disposal', label: 'Disposal rate', filterable: false },
  { id: 'overlaps', label: 'Cross-bureau overlap & relationships', filterable: false },
];

const REGIONS = ['Northern', 'Southern', 'Eastern', 'Western', 'Central', 'North-Eastern'];

export default function ReportsPage() {
  const [report, setReport] = useState('institutions');
  const [region, setRegion] = useState('');
  const [state, setState] = useState('');
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const def = REPORTS.find((r) => r.id === report)!;

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(
        await api.get<ReportData>(
          `/reports/${report}${buildQuery({ region: region || null, state: state || null })}`,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load report');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report, region, state]);

  async function exportCsv() {
    const url = `/api/v1/reports/export.csv${buildQuery({
      report,
      region: region || null,
      state: state || null,
    })}`;
    const resp = await fetch(url, {
      headers: { Authorization: `Bearer ${getToken() ?? ''}` },
    });
    if (!resp.ok) {
      setError(`CSV export failed with status ${resp.status}`);
      return;
    }
    const blob = await resp.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `institrace-${report}-report.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  return (
    <div>
      <h3 style={{ marginTop: 0 }}>Reports &amp; Analytics</h3>
      <div className="card">
        <div className="filters">
          <div>
            <label htmlFor="r-report">Report</label>
            <select id="r-report" value={report} onChange={(e) => setReport(e.target.value)}>
              {REPORTS.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          {def.filterable && (
            <>
              <div>
                <label htmlFor="r-region">Region</label>
                <select id="r-region" value={region} onChange={(e) => setRegion(e.target.value)}>
                  <option value="">All regions</option>
                  {REGIONS.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="r-state">State</label>
                <input id="r-state" value={state} onChange={(e) => setState(e.target.value)} />
              </div>
            </>
          )}
          <button className="secondary" onClick={exportCsv}>
            ⬇ Export CSV (respects filters)
          </button>
        </div>
        {loading ? (
          <Loading label="Computing report from database…" />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : !data ? (
          <EmptyState title="No report loaded" />
        ) : (
          <>
            <div className="notice info">
              <strong>{data.title}.</strong> {data.definition}
            </div>
            {data.rows.length === 0 ? (
              <EmptyState title="No rows for the selected filters" />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="data">
                  <thead>
                    <tr>
                      {data.columns.map((c) => (
                        <th key={c}>{c.replace(/_/g, ' ')}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row, idx) => (
                      <tr key={idx}>
                        {data.columns.map((c) => (
                          <td key={c}>{row[c] === null || row[c] === undefined ? '—' : String(row[c])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
        <p className="small" style={{ marginTop: 12 }}>
          CSV exports include the report definition, generation timestamp, and applied filters as
          metadata rows. Cells beginning with =, +, - or @ are prefixed with an apostrophe to
          prevent spreadsheet formula injection. Synthetic demo data only — no operational
          savings or performance improvements are claimed.
        </p>
      </div>
    </div>
  );
}
