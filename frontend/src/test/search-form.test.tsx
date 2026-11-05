import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CaseSearchForm } from '../pages/CasesPage';

const baseFilters: Record<string, string> = {
  q: '', case_id: '', institution_q: '', permanent_id: '',
  bureau_id: '', region: '', category: '', status: '',
  receipt_from: '', receipt_to: '', overdue: '', approaching: '',
  review_state: '', sort: 'receipt_date', sort_dir: 'desc', page: '1',
};
const bureaus = [
  { id: 1, code: 'RB', name: 'Regulation Bureau', description: '', active: true },
  { id: 2, code: 'PGRC', name: 'Public Grievance Redressal Cell', description: '', active: true },
];
const regions = ['Northern', 'Southern'];

function setup(over: Partial<Parameters<typeof CaseSearchForm>[0]> = {}) {
  const onSubmit = vi.fn();
  const onClear = vi.fn();
  const onRemoveChip = vi.fn();
  render(
    <CaseSearchForm
      filters={over.filters ?? baseFilters}
      bureaus={bureaus}
      regions={regions}
      categories={['Infrastructure', 'Fees & Refund']}
      activeCount={over.activeCount ?? 0}
      onSubmit={onSubmit}
      onClear={onClear}
      onRemoveChip={onRemoveChip}
    />,
  );
  return { onSubmit, onClear, onRemoveChip };
}

describe('CaseSearchForm', () => {
  it('renders all mandated search fields', () => {
    setup();
    expect(screen.getByLabelText(/ID or subject/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Case ID \(exact\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Institution name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Permanent ID \(exact\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Bureau/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Region/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Complaint category/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Case status/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Received from/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Received to/i)).toBeInTheDocument();
  });

  it('applies combined filters via the Search button into URL params', () => {
    const { onSubmit } = setup();
    fireEvent.change(screen.getByLabelText(/Case ID \(exact\)/i), { target: { value: 'DEMO-CASE-022' } });
    fireEvent.change(screen.getByLabelText(/Bureau/), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText(/Case status/i), { target: { value: 'PENDING' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    const next = onSubmit.mock.calls[0][0] as URLSearchParams;
    expect(next.get('case_id')).toBe('DEMO-CASE-022');
    expect(next.get('bureau_id')).toBe('2');
    expect(next.get('status')).toBe('PENDING');
    expect(next.get('q')).toBeNull();
  });

  it('submits on Enter from a text field (keyboard access)', () => {
    const { onSubmit } = setup();
    fireEvent.change(screen.getByLabelText(/Institution name/i), { target: { value: 'Sunrise' } });
    fireEvent.submit(screen.getByTestId('case-search-form'));
    const next = onSubmit.mock.calls[0][0] as URLSearchParams;
    expect(next.get('institution_q')).toBe('Sunrise');
  });

  it('Clear filters resets to the unfiltered registry', () => {
    const { onClear } = setup({
      filters: { ...baseFilters, q: 'CASE-00' },
      activeCount: 1,
    });
    const btn = screen.getByRole('button', { name: /clear filters/i });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('shows active-filter chips and lets each chip be removed', () => {
    const { onRemoveChip } = setup({
      filters: { ...baseFilters, q: 'CASE-00', bureau_id: '1', status: 'ESCALATED' },
      activeCount: 3,
    });
    expect(screen.getByText(/Case ID \/ subject: CASE-00/)).toBeInTheDocument();
    expect(screen.getByText(/Bureau\/Cell: RB/)).toBeInTheDocument();
    expect(screen.getByText(/Status: Escalated/i)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Remove filter Bureau/Cell'));
    expect(onRemoveChip).toHaveBeenCalledWith('bureau_id');
  });

  it('darkens the Clear button when nothing is active', () => {
    setup();
    expect(screen.getByRole('button', { name: /clear filters/i })).toBeDisabled();
  });

  it('drops empty draft fields from the submitted params', () => {
    const { onSubmit } = setup();
    fireEvent.submit(screen.getByTestId('case-search-form'));
    const next = onSubmit.mock.calls[0][0] as URLSearchParams;
    expect([...next.keys()].length).toBeLessThanOrEqual(2); // only sort/sort_dir allowed
    expect(next.get('sort')).toBe('receipt_date');
  });
});
