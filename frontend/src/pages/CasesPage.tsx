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

  const filters = {
    q: params.get('q') ?? '',
    institution_q: params.get('institution_q') ?? '',
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
        <div className="filters">
          <div>
            <label htmlFor="case-q">Case ID / subject</label>
            <input id="case-q" value={filters.q} onChange={(e) => update('q', e.target.value)} placeholder="DEMO-CASE-001" />
          </div>
          <div>
            <label htmlFor="case-inst">Institution</label>
            <input
              id="case-inst"
              value={filters.institution_q}
              onChange={(e) => update('institution_q', e.target.value)}
              placeholder="name or permanent ID"
            />
          </div>
          <div>
            <label htmlFor="case-bureau">Bureau/Cell</label>
            <select id="case-bureau" value={filters.bureau_id} onChange={(e) => update('bureau_id', e.target.value)}>
              <option value="">All</option>
              {(meta?.bureaus ?? []).map((b: BureauOut) => (
                <option key={b.id} value={b.id}>
                  {b.code}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="case-region">Region</label>
            <select id="case-region" value={filters.region} onChange={(e) => update('region', e.target.value)}>
              <option value="">All</option>
              {REGIONS.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="case-category">Category</label>
            <select id="case-category" value={filters.category} onChange={(e) => update('category', e.target.value)}>
              <option value="">All</option>
              {ALL_CATEGORIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="case-status">Status</label>
            <select id="case-status" value={filters.status} onChange={(e) => update('status', e.target.value)}>
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
            <input id="case-from" type="date" value={filters.receipt_from} onChange={(e) => update('receipt_from', e.target.value)} />
          </div>
          <div>
            <label htmlFor="case-to">Received to</label>
            <input id="case-to" type="date" value={filters.receipt_to} onChange={(e) => update('receipt_to', e.target.value)} />
          </div>
          <div>
            <label htmlFor="case-deadline">Deadline state</label>
            <select
              id="case-deadline"
              value={filters.overdue ? 'overdue' : filters.approaching ? 'approaching' : ''}
              onChange={(e) => {
                update('overdue', '');
                update('approaching', '');
                if (e.target.value) update(e.target.value, 'true');
              }}
            >
              <option value="">All</option>
              <option value="overdue">Overdue</option>
              <option value="approaching">Approaching deadline</option>
            </select>
          </div>
          <div>
            <label htmlFor="case-review">Review state</label>
            <select id="case-review" value={filters.review_state} onChange={(e) => update('review_state', e.target.value)}>
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
              value={`${filters.sort}:${filters.sort_dir}`}
              onChange={(e) => {
                const [s, d] = e.target.value.split(':');
                const next = new URLSearchParams(params);
                next.set('sort', s);
                next.set('sort_dir', d);
                setParams(next);
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
          {activeFilterCount > 0 && (
            <>
              <button className="secondary" onClick={() => setParams(new URLSearchParams())}>
                Reset {activeFilterCount} filter{activeFilterCount === 1 ? '' : 's'}
              </button>
            </>
          )}
        </div>

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
