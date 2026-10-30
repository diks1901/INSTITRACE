import { ReactNode } from 'react';
import {
  AlertStatus,
  AlertType,
  AssessmentStatus,
  CaseStatus,
  RelationshipType,
} from '../api/types';

export const STATUS_LABELS: Record<CaseStatus, string> = {
  PENDING: 'Pending',
  UNDER_PROCESS: 'Under Process',
  DISPOSED: 'Disposed',
  TRANSFERRED: 'Transferred',
  ESCALATED: 'Escalated',
};

export const ALERT_LABELS: Record<AlertType, string> = {
  CROSS_BUREAU_COORDINATION: 'Cross-Bureau Coordination',
  POTENTIAL_SAME_INCIDENT: 'Potential Same Incident',
  PENDING_REMINDER: 'Pending Reminder',
  APPROACHING_DEADLINE: 'Deadline Approaching',
  OVERDUE: 'Overdue',
  ESCALATION_REQUIRED: 'Escalation Required',
};

export const ALERT_STATUS_LABELS: Record<AlertStatus, string> = {
  OPEN: 'Open',
  ACKNOWLEDGED: 'Acknowledged',
  RESOLVED: 'Resolved',
};

export const REL_LABELS: Record<RelationshipType, string> = {
  POTENTIAL_SAME_INCIDENT: 'Potential Same Incident',
  PROCEDURAL_LINK: 'Procedural Link',
  NO_RELATIONSHIP_ESTABLISHED: 'No Relationship Established',
  INSUFFICIENT_EVIDENCE: 'Insufficient Evidence',
};

export const REVIEW_LABELS: Record<AssessmentStatus, string> = {
  PENDING_REVIEW: 'Pending Review',
  CONFIRMED: 'Confirmed (human)',
  REJECTED: 'Rejected (human)',
  DEFERRED: 'Deferred (human)',
};

export function StatusBadge({ status }: { status: CaseStatus }) {
  return <span className={`badge status-${status}`}>{STATUS_LABELS[status] ?? status}</span>;
}

export function AlertTypeBadge({ type }: { type: AlertType }) {
  return <span className={`badge atype-${type}`}>{ALERT_LABELS[type] ?? type}</span>;
}

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  return <span className={`badge alert-${status}`}>{ALERT_STATUS_LABELS[status] ?? status}</span>;
}

export function RelBadge({ type }: { type: RelationshipType }) {
  return <span className={`badge rel-${type}`}>{REL_LABELS[type] ?? type}</span>;
}

export function ReviewBadge({ status }: { status: AssessmentStatus }) {
  return <span className={`badge review-${status}`}>{REVIEW_LABELS[status] ?? status}</span>;
}

export function OccurrenceBadge({ occurrence }: { occurrence: number }) {
  if (!occurrence || occurrence <= 1) return null;
  return (
    <span
      className="badge occurrence"
      title="This condition was resolved before and recurred; this alert is a new occurrence. Earlier occurrences remain in the resolved history."
    >
      Recurrence #{occurrence}
    </span>
  );
}

export function RereviewBadge() {
  return (
    <span
      className="badge rereview"
      title={"The evidence changed after a human decision was recorded. That decision is preserved but no longer covers the current evidence - re-review required. The original evidence snapshot is kept on the record and in the audit trail."}
    >
      Outdated decision — re-review
    </span>
  );
}

export function DemoBadge() {
  return (
    <span className="badge demo" title="Synthetic demo data - not a real AICTE record">
      DEMO DATA
    </span>
  );
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty-state">
      <p style={{ fontWeight: 600, marginBottom: 4 }}>{title}</p>
      {hint && <p style={{ margin: 0 }}>{hint}</p>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="notice error" role="alert">
      <strong>Something went wrong:</strong> {message}
      {onRetry && (
        <button className="secondary" style={{ marginLeft: 12 }} onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex-between">
          <h3>{title}</h3>
          <button className="secondary" onClick={onClose} aria-label="Close dialog">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Pager({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pager">
      <span>
        Page {page} of {pages} · {total} record{total === 1 ? '' : 's'}
      </span>
      <button className="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ← Prev
      </button>
      <button className="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next →
      </button>
    </div>
  );
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return value.slice(0, 10);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  return value.replace('T', ' ').slice(0, 16);
}
