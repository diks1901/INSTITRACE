import { FormEvent, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, buildQuery } from '../api/client';
import { InstitutionOut, Page } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import {
  DemoBadge,
  EmptyState,
  ErrorState,
  Loading,
  Modal,
  Pager,
} from '../components/primitives';

const REGIONS = ['Northern', 'Southern', 'Eastern', 'Western', 'Central', 'North-Eastern'];

export default function InstitutionsPage() {
  const { canAdmin } = useAuth();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<Page<InstitutionOut> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const q = params.get('q') ?? '';
  const region = params.get('region') ?? '';
  const state = params.get('state') ?? '';
  const page = Number(params.get('page') ?? '1');

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(
        await api.get<Page<InstitutionOut>>(
          `/institutions${buildQuery({ q, region, state, page, page_size: 15 })}`,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load institutions');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, region, state, page]);

  function update(patch: Record<string, string>) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!('page' in patch)) next.delete('page');
    setParams(next);
  }

  return (
    <div>
      <div className="flex-between">
        <h3 style={{ marginTop: 0 }}>Institution Directory</h3>
        {canAdmin && <button onClick={() => setShowForm(true)}>+ New institution</button>}
      </div>
      <div className="card">
        <div className="filters">
          <div>
            <label htmlFor="inst-q">Search name / permanent ID</label>
            <input
              id="inst-q"
              value={q}
              placeholder="e.g. Sunrise or DEMO-INS-001"
              onChange={(e) => update({ q: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="inst-region">Region</label>
            <select id="inst-region" value={region} onChange={(e) => update({ region: e.target.value })}>
              <option value="">All regions</option>
              {REGIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="inst-state">State</label>
            <input id="inst-state" value={state} onChange={(e) => update({ state: e.target.value })} />
          </div>
          {(q || region || state) && (
            <button className="secondary" onClick={() => setParams(new URLSearchParams())}>
              Reset filters
            </button>
          )}
          {(q || region || state) && (
            <span className="small">
              Active filters: {[q && `q="${q}"`, region && `region=${region}`, state && `state=${state}`]
                .filter(Boolean)
                .join(', ')}
            </span>
          )}
        </div>
        {loading ? (
          <Loading />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState title="No institutions match" hint="Adjust or reset the filters above." />
        ) : (
          <>
            <table className="data">
              <thead>
                <tr>
                  <th>Permanent ID</th>
                  <th>Institution</th>
                  <th>Region / State</th>
                  <th>District</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((inst) => (
                  <tr key={inst.id}>
                    <td className="mono">
                      <Link to={`/institutions/${inst.id}`}>{inst.permanent_id}</Link>
                    </td>
                    <td>
                      <Link to={`/institutions/${inst.id}`}>{inst.name}</Link>{' '}
                      {inst.is_demo && <DemoBadge />}
                    </td>
                    <td>
                      {inst.region} · {inst.state}
                    </td>
                    <td>{inst.district ?? '—'}</td>
                    <td>{inst.institution_type ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => update({ page: String(p) })} />
          </>
        )}
      </div>
      {showForm && (
        <InstitutionForm
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            void load();
          }}
        />
      )}
    </div>
  );
}

export function InstitutionForm({
  initial,
  onClose,
  onSaved,
}: {
  initial?: InstitutionOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    permanent_id: initial?.permanent_id ?? '',
    name: initial?.name ?? '',
    address: initial?.address ?? '',
    region: initial?.region ?? 'Northern',
    state: initial?.state ?? '',
    district: initial?.district ?? '',
    institution_type: initial?.institution_type ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (form.permanent_id.trim().length < 3) errs.permanent_id = 'Permanent ID must be at least 3 characters.';
    if (form.name.trim().length < 3) errs.name = 'Name must be at least 3 characters.';
    if (form.state.trim().length < 2) errs.state = 'State is required.';
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setBusy(true);
    setError(null);
    try {
      const payload = {
        ...form,
        district: form.district || null,
        institution_type: form.institution_type || null,
      };
      if (initial) {
        await api.patch(`/institutions/${initial.id}`, payload);
      } else {
        await api.post('/institutions', payload);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={initial ? `Edit ${initial.name}` : 'New synthetic institution'} onClose={onClose}>
      {error && <div className="notice error">{error}</div>}
      <form onSubmit={submit} className="form-grid">
        <div>
          <label htmlFor="f-pid">AICTE Permanent ID *</label>
          <input
            id="f-pid"
            value={form.permanent_id}
            disabled={!!initial}
            onChange={(e) => setForm({ ...form, permanent_id: e.target.value })}
            placeholder="DEMO-INS-0xx"
          />
          {fieldErrors.permanent_id && <div className="field-error">{fieldErrors.permanent_id}</div>}
        </div>
        <div>
          <label htmlFor="f-name">Institution name *</label>
          <input id="f-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          {fieldErrors.name && <div className="field-error">{fieldErrors.name}</div>}
        </div>
        <div>
          <label htmlFor="f-region">Region *</label>
          <select id="f-region" value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })}>
            {REGIONS.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="f-state">State *</label>
          <input id="f-state" value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} />
          {fieldErrors.state && <div className="field-error">{fieldErrors.state}</div>}
        </div>
        <div>
          <label htmlFor="f-district">District</label>
          <input id="f-district" value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value })} />
        </div>
        <div>
          <label htmlFor="f-type">Institution type</label>
          <input id="f-type" value={form.institution_type} onChange={(e) => setForm({ ...form, institution_type: e.target.value })} />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label htmlFor="f-address">Address</label>
          <input id="f-address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
        </div>
        <div className="button-row" style={{ gridColumn: '1 / -1' }}>
          <button type="submit" disabled={busy}>
            {busy ? 'Saving…' : initial ? 'Save changes' : 'Create institution'}
          </button>
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
