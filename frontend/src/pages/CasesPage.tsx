import './search.css';
import { FormEvent, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, buildQuery } from '../api/client';
import { BureauOut, CaseOut, InstitutionOut, MetaInfo, Page } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import {
  EmptyState,
  ErrorState,
  Loading,
  Modal,
  Pager,
  STATUS_LABELS,
  StatusBadge,
  formatDate,
} from '../components/primitives';

const PAGE_SIZE = 15;

export default function CasesPage() {
  const { canWriteCases } = useAuth();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<Page<CaseOut> | null>(null);
  const [meta, setMeta] = useState<MetaInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  // Applied filters come from the URL (source of truth, shareable);
  // the search panel edits a local draft and applies via Search / Enter.
  const filters = {
    q: params.get('q') ?? '',
    case_id: params.get('case_id') ?? '',
    institution_q: params.get('institution_q') ?? '',
    permanent_id: params.get('permanent_id') ?? '',
    bureau_id: params.get('bureau_id') ?? '',
    region: params.get('region') ?? '',
    category: params.get('category') ?? '',
    status: params.get('status') ?? '',
    receipt_from: params.get('receipt_from') ?? '',
    receipt_to: params.get('receipt_to') ?? '',
    overdue: params.get('overdue') ?? '',
    approaching: params.get('approaching') ?? '',
    review_state: params.get('review_state') ?? '',
    sort: params.get('sort') ?? 'receipt_date',
    sort_dir: params.get('sort_dir') ?? 'desc',
    page: params.get('page') ?? '1',
  };

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [pageData, metaData] = await Promise.all([
        api.get<Page<CaseOut>>(`/cases${buildQuery({ ...filters, page_size: PAGE_SIZE })}`),
        api.get<MetaInfo>('/meta'),
      ]);
      setData(pageData);
      setMeta(metaData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cases');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('page');
    setParams(next);
  }

  const activeFilterCount = Object.entries(filters).filter(
    ([k, v]) => v && !['page', 'sort', 'sort_dir'].includes(k),
  ).length;

  const ALL_CATEGORIES = [
    'Fees & Refund', 'Admission & Enrollment', 'Examination & Results', 'Faculty & Staff',
    'Infrastructure', 'Recognition & Approval', 'Scholarship', 'Ragging & Safety',
    'Document Verification', 'Others',
  ];
  const REGIONS = ['Northern', 'Southern', 'Eastern', 'Western', 'Central', 'North-Eastern'];

  return (
    <div>
      <div className="flex-between">
        <h3 style={{ marginTop: 0 }}>Complaint / Case Registry</h3>
        {canWriteCases && <button onClick={() => setShowCreate(true)}>+ Register complaint</button>}
      </div>
      <div className="card">
        <CaseSearchForm
          filters={filters}
          bureaus={meta?.bureaus ?? []}
          regions={REGIONS}
          categories={ALL_CATEGORIES}
          activeCount={activeFilterCount}
          onSubmit={(next) => setParams(next)}
          onClear={() => setParams(new URLSearchParams())}
          onRemoveChip={(key) => {
            const next = new URLSearchParams(params);
            next.delete(key);
            if (key === 'overdue') next.delete('approaching');
            if (key === 'approaching') next.delete('overdue');
            next.delete('page');
            setParams(next);
          }}
        />

        {loading ? (
          <Loading />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState title="No cases match the current filters" hint="Try widening the date range or resetting filters." />
        ) : (
          <>
            <table className="data">
              <thead>
                <tr>
                  <th>Case ID</th>
                  <th>Subject</th>
                  <th>Institution</th>
                  <th>Status</th>
                  <th>Bureau</th>
                  <th>Officer</th>
                  <th>Received</th>
                  <th>Expected disposal</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id}>
                    <td className="mono">
                      <Link to={`/cases/${c.id}`}>{c.case_id}</Link>
                    </td>
                    <td>
                      <Link to={`/cases/${c.id}`}>{c.subject}</Link>
                    </td>
                    <td>
                      <Link to={`/institutions/${c.institution.id}`}>{c.institution.name}</Link>
                    </td>
                    <td>
                      <StatusBadge status={c.status} />
                    </td>
                    <td>{c.bureau.code}</td>
                    <td>{c.officer_name}</td>
                    <td>{formatDate(c.receipt_date)}</td>
                    <td>{formatDate(c.expected_disposal_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager
              page={data.page}
              pageSize={data.page_size}
              total={data.total}
              onPage={(p) => update('page', String(p))}
            />
          </>
        )}
      </div>
      {showCreate && meta && (
        <CreateCaseModal
          meta={meta}
          categories={ALL_CATEGORIES}
          onClose={() => setShowCreate(false)}
          onSaved={() => {
            setShowCreate(false);
            void load();
          }}
        />
      )}
    </div>
  );
}

function CreateCaseModal({
  meta,
  categories,
  onClose,
  onSaved,
}: {
  meta: MetaInfo;
  categories: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [institutions, setInstitutions] = useState<InstitutionOut[]>([]);
  const [form, setForm] = useState({
    case_id: '',
    institution_id: '',
    receipt_date: new Date().toISOString().slice(0, 10),
    category: categories[0],
    subject: '',
    description: '',
    bureau_id: String(meta.bureaus[0]?.id ?? ''),
    officer_name: '',
    priority: 'MEDIUM',
    expected_disposal_date: '',
    source_record_ref: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<{ items: InstitutionOut[] }>('/institutions?page_size=200')
      .then((d) => setInstitutions(d.items))
      .catch(() => setInstitutions([]));
  }, []);

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (form.case_id.trim().length < 3) errs.case_id = 'Case ID must be at least 3 characters.';
    if (!form.institution_id) errs.institution_id = 'Select an institution.';
    if (form.subject.trim().length < 3) errs.subject = 'Subject is required (min 3 characters).';
    if (form.expected_disposal_date && form.expected_disposal_date < form.receipt_date)
      errs.expected_disposal_date = 'Expected disposal cannot be before the receipt date.';
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setBusy(true);
    setError(null);
    try {
      await api.post('/cases', {
        ...form,
        institution_id: Number(form.institution_id),
        bureau_id: Number(form.bureau_id),
        expected_disposal_date: form.expected_disposal_date || null,
        source_record_ref: form.source_record_ref || null,
        officer_name: form.officer_name,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create case');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Register complaint (synthetic demo record)" onClose={onClose}>
      {error && <div className="notice error">{error}</div>}
      <form onSubmit={submit} className="form-grid">
        <div>
          <label htmlFor="c-id">Case ID *</label>
          <input id="c-id" value={form.case_id} onChange={(e) => setForm({ ...form, case_id: e.target.value })} placeholder="DEMO-CASE-0xx" />
          {fieldErrors.case_id && <div className="field-error">{fieldErrors.case_id}</div>}
        </div>
        <div>
          <label htmlFor="c-inst">Institution *</label>
          <select id="c-inst" value={form.institution_id} onChange={(e) => setForm({ ...form, institution_id: e.target.value })}>
            <option value="">Select…</option>
            {institutions.map((i) => (
              <option key={i.id} value={i.id}>
                {i.permanent_id} — {i.name}
              </option>
            ))}
          </select>
          {fieldErrors.institution_id && <div className="field-error">{fieldErrors.institution_id}</div>}
        </div>
        <div>
          <label htmlFor="c-receipt">Receipt date *</label>
          <input id="c-receipt" type="date" value={form.receipt_date} onChange={(e) => setForm({ ...form, receipt_date: e.target.value })} />
        </div>
        <div>
          <label htmlFor="c-cat">Category *</label>
          <select id="c-cat" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label htmlFor="c-subject">Subject *</label>
          <input id="c-subject" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} />
          {fieldErrors.subject && <div className="field-error">{fieldErrors.subject}</div>}
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label htmlFor="c-desc">Description</label>
          <textarea id="c-desc" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div>
          <label htmlFor="c-bureau">Bureau/Cell *</label>
          <select id="c-bureau" value={form.bureau_id} onChange={(e) => setForm({ ...form, bureau_id: e.target.value })}>
            {meta.bureaus.map((b) => (
              <option key={b.id} value={b.id}>
                {b.code} — {b.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="c-officer">Officer</label>
          <input id="c-officer" value={form.officer_name} onChange={(e) => setForm({ ...form, officer_name: e.target.value })} />
        </div>
        <div>
          <label htmlFor="c-priority">Priority</label>
          <select id="c-priority" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
            {meta.priorities.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="c-exp">Expected disposal date</label>
          <input id="c-exp" type="date" value={form.expected_disposal_date} onChange={(e) => setForm({ ...form, expected_disposal_date: e.target.value })} />
          {fieldErrors.expected_disposal_date && <div className="field-error">{fieldErrors.expected_disposal_date}</div>}
        </div>
        <div>
          <label htmlFor="c-src">Source record reference</label>
          <input id="c-src" value={form.source_record_ref} onChange={(e) => setForm({ ...form, source_record_ref: e.target.value })} placeholder="SRC-…" />
        </div>
        <div className="button-row" style={{ gridColumn: '1 / -1' }}>
          <button type="submit" disabled={busy}>
            {busy ? 'Registering…' : 'Register complaint'}
          </button>
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}

const FILTER_LABELS: Record<string, string> = {
  q: 'Case ID / subject',
  case_id: 'Case ID (exact)',
  institution_q: 'Institution',
  permanent_id: 'Permanent ID',
  bureau_id: 'Bureau/Cell',
  region: 'Region',
  category: 'Category',
  status: 'Status',
  receipt_from: 'Received from',
  receipt_to: 'Received to',
  overdue: 'Overdue',
  approaching: 'Approaching deadline',
  review_state: 'Review state',
};

export function CaseSearchForm({
  filters,
  bureaus,
  regions,
  categories,
  activeCount,
  onSubmit,
  onClear,
  onRemoveChip,
}: {
  filters: Record<string, string>;
  bureaus: BureauOut[];
  regions: string[];
  categories: string[];
  activeCount: number;
  onSubmit: (next: URLSearchParams) => void;
  onClear: () => void;
  onRemoveChip: (key: string) => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>(filters);
  // Keep the draft in sync with applied URL params (e.g. chip removals).
  useEffect(() => {
    setDraft(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters)]);

  function set(key: string, value: string) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const next = new URLSearchParams();
    for (const [k, v] of Object.entries(draft)) {
      if (v && !['page'].includes(k)) next.set(k, v);
    }
    onSubmit(next);
  }

  function chipText(key: string, value: string): string {
    let v = value;
    if (key === 'bureau_id') v = bureaus.find((b) => String(b.id) === value)?.code ?? `ID ${value}`;
    if (key === 'status') v = (STATUS_LABELS as Record<string, string>)[value] ?? value;
    if (key === 'overdue') v = value === 'true' ? 'Yes' : value;
    if (key === 'approaching') v = value === 'true' ? 'Yes' : value;
    if (key === 'review_state') v = value.replace('_', ' ').toLowerCase();
    return `${FILTER_LABELS[key] ?? key}: ${v}`;
  }

  const chips = Object.entries(filters).filter(
    ([k, v]) => v && !['page', 'sort', 'sort_dir'].includes(k),
  );

  return (
    <form className="search-panel" onSubmit={submit} data-testid="case-search-form">
      <div className="search-header">
        <h4 style={{ margin: 0 }}>Search cases</h4>
        <span className="small" style={{ color: 'var(--ink-soft)' }}>
          Searches the full registry on the server — not just the rows on screen.
        </span>
      </div>
      <div className="search-grid">
        <div>
          <label htmlFor="case-q">Case / Complaint ID or subject</label>
          <input id="case-q" value={draft.q} onChange={(e) => set('q', e.target.value)} placeholder="e.g. DEMO-CASE-001 or CASE-00" />
        </div>
        <div>
          <label htmlFor="case-exact-id">Case ID (exact)</label>
          <input id="case-exact-id" value={draft.case_id} onChange={(e) => set('case_id', e.target.value)} placeholder="DEMO-CASE-001" />
        </div>
        <div>
          <label htmlFor="case-inst">Institution name</label>
          <input id="case-inst" value={draft.institution_q} onChange={(e) => set('institution_q', e.target.value)} placeholder="partial name, e.g. Sunrise" />
        </div>
        <div>
          <label htmlFor="case-pid">AICTE Permanent ID (exact)</label>
          <input id="case-pid" value={draft.permanent_id} onChange={(e) => set('permanent_id', e.target.value)} placeholder="DEMO-INS-001" />
        </div>
        <div>
          <label htmlFor="case-bureau">Bureau/Cell</label>
          <select id="case-bureau" value={draft.bureau_id} onChange={(e) => set('bureau_id', e.target.value)}>
            <option value="">All</option>
            {bureaus.map((b) => (
              <option key={b.id} value={b.id}>
                {b.code} — {b.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="case-region">Region</label>
          <select id="case-region" value={draft.region} onChange={(e) => set('region', e.target.value)}>
            <option value="">All</option>
            {regions.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="case-category">Complaint category</label>
          <select id="case-category" value={draft.category} onChange={(e) => set('category', e.target.value)}>
            <option value="">All</option>
            {categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="case-status">Case status</label>
          <select id="case-status" value={draft.status} onChange={(e) => set('status', e.target.value)}>
            <option value="">All</option>
            {Object.entries(STATUS_LABELS).map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="case-from">Received from</label>
          <input id="case-from" type="date" value={draft.receipt_from} onChange={(e) => set('receipt_from', e.target.value)} />
        </div>
        <div>
          <label htmlFor="case-to">Received to</label>
          <input id="case-to" type="date" value={draft.receipt_to} onChange={(e) => set('receipt_to', e.target.value)} />
        </div>
        <div>
          <label htmlFor="case-deadline">Deadline state</label>
          <select
            id="case-deadline"
            value={draft.overdue ? 'overdue' : draft.approaching ? 'approaching' : ''}
            onChange={(e) =>
              setDraft((d) => ({
                ...d,
                overdue: e.target.value === 'overdue' ? 'true' : '',
                approaching: e.target.value === 'approaching' ? 'true' : '',
              }))
            }
          >
            <option value="">All</option>
            <option value="overdue">Overdue</option>
            <option value="approaching">Approaching deadline</option>
          </select>
        </div>
        <div>
          <label htmlFor="case-review">Review state</label>
          <select id="case-review" value={draft.review_state} onChange={(e) => set('review_state', e.target.value)}>
            <option value="">All</option>
            <option value="PENDING_REVIEW">Pending review</option>
            <option value="CONFIRMED">Confirmed</option>
            <option value="REJECTED">Rejected</option>
            <option value="DEFERRED">Deferred</option>
          </select>
        </div>
        <div>
          <label htmlFor="case-sort">Sort</label>
          <select
            id="case-sort"
            value={`${draft.sort}:${draft.sort_dir}`}
            onChange={(e) => {
              const [sv, d] = e.target.value.split(':');
              setDraft((dd) => ({ ...dd, sort: sv, sort_dir: d }));
            }}
          >
            <option value="receipt_date:desc">Newest received</option>
            <option value="receipt_date:asc">Oldest received</option>
            <option value="expected_disposal_date:asc">Expected disposal ↑</option>
            <option value="expected_disposal_date:desc">Expected disposal ↓</option>
            <option value="case_id:asc">Case ID ↑</option>
            <option value="status:asc">Status ↑</option>
          </select>
        </div>
      </div>
      <div className="search-actions">
        <button type="submit">Search</button>
        <button type="button" className="secondary" onClick={onClear} disabled={chips.length === 0}>
          Clear filters
        </button>
        {activeCount > 0 && (
          <span className="small" style={{ color: 'var(--ink-soft)', alignSelf: 'center' }}>
            {activeCount} active filter{activeCount === 1 ? '' : 's'}
          </span>
        )}
      </div>
      {chips.length > 0 && (
        <div className="search-chips" role="list" aria-label="Active filters">
          {chips.map(([k, v]) => (
            <span key={k} className="chip chip-filter" role="listitem">
              {chipText(k, v)}
              <button
                type="button"
                className="chip-x"
                aria-label={`Remove filter ${FILTER_LABELS[k] ?? k}`}
                onClick={() => onRemoveChip(k)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </form>
  );
}
