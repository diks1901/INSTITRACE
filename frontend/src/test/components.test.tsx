import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  ALERT_LABELS,
  AlertStatusBadge,
  AlertTypeBadge,
  DemoBadge,
  EmptyState,
  OccurrenceBadge,
  REL_LABELS,
  RelBadge,
  RereviewBadge,
  ReviewBadge,
  STATUS_LABELS,
  StatusBadge,
} from '../components/primitives';
import { InstitutionForm } from '../pages/InstitutionsPage';

describe('status & review labels', () => {
  it('renders human-readable status badges', () => {
    render(<StatusBadge status="UNDER_PROCESS" />);
    expect(screen.getByText('Under Process')).toBeInTheDocument();
  });

  it('keeps automated recommendation and human review labels distinct', () => {
    render(
      <div>
        <RelBadge type="POTENTIAL_SAME_INCIDENT" />
        <ReviewBadge status="CONFIRMED" />
      </div>,
    );
    expect(screen.getByText('Potential Same Incident')).toBeInTheDocument();
    expect(screen.getByText('Confirmed (human)')).toBeInTheDocument();
    expect(REL_LABELS.INSUFFICIENT_EVIDENCE).toBe('Insufficient Evidence');
  });

  it('marks synthetic data clearly', () => {
    render(<DemoBadge />);
    expect(screen.getByText('DEMO DATA')).toBeInTheDocument();
  });

  it('shows meaningful empty states', () => {
    render(<EmptyState title="No cases match" hint="Reset filters" />);
    expect(screen.getByText('No cases match')).toBeInTheDocument();
    expect(screen.getByText('Reset filters')).toBeInTheDocument();
  });
});

describe('InstitutionForm client-side validation', () => {
  it('shows field errors and blocks submission on invalid input', () => {
    const onSaved = vi.fn();
    render(<InstitutionForm onClose={() => {}} onSaved={onSaved} />);
    fireEvent.click(screen.getByText('Create institution'));
    expect(screen.getByText('Permanent ID must be at least 3 characters.')).toBeInTheDocument();
    expect(screen.getByText('Name must be at least 3 characters.')).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });
});

describe('occurrence & re-review badges', () => {
  it('hides the recurrence badge for first occurrences and shows it for recurrences', () => {
    const { container, rerender } = render(<OccurrenceBadge occurrence={1} />);
    expect(container.querySelector('.badge.occurrence')).toBeNull();
    rerender(<OccurrenceBadge occurrence={2} />);
    expect(screen.getByText('Recurrence #2')).toBeInTheDocument();
  });

  it('labels outdated decisions unmistakably', () => {
    render(<RereviewBadge />);
    expect(screen.getByText(/Outdated decision/i)).toBeInTheDocument();
  });
});

describe('alert badges are visually distinct from relationship outcomes', () => {
  it('uses dedicated atype-* classes and every alert type has a label', () => {
    const { container } = render(<AlertTypeBadge type="CROSS_BUREAU_COORDINATION" />);
    const el = container.querySelector('.badge')!;
    expect(el.className).toContain('atype-CROSS_BUREAU_COORDINATION');
    expect(ALERT_LABELS).toHaveProperty('PENDING_REMINDER');
    expect(ALERT_LABELS).toHaveProperty('APPROACHING_DEADLINE');
    expect(ALERT_LABELS).toHaveProperty('OVERDUE');
    expect(ALERT_LABELS).toHaveProperty('ESCALATION_REQUIRED');
  });

  it('alert lifecycle badges cover OPEN / ACKNOWLEDGED / RESOLVED', () => {
    render(
      <div>
        <AlertStatusBadge status="OPEN" />
        <AlertStatusBadge status="ACKNOWLEDGED" />
        <AlertStatusBadge status="RESOLVED" />
      </div>,
    );
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText('Acknowledged')).toBeInTheDocument();
    expect(screen.getByText('Resolved')).toBeInTheDocument();
  });
});

describe('navigation structure', () => {
  it('STATUS_LABELS covers all five mandated statuses', () => {
    expect(Object.keys(STATUS_LABELS).sort()).toEqual(
      ['DISPOSED', 'ESCALATED', 'PENDING', 'TRANSFERRED', 'UNDER_PROCESS'].sort(),
    );
  });
});
