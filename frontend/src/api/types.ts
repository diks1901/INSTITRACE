// Typed API contract mirroring backend/app/schemas.py
export type CaseStatus =
  | 'PENDING'
  | 'UNDER_PROCESS'
  | 'DISPOSED'
  | 'TRANSFERRED'
  | 'ESCALATED';

export type Priority = 'LOW' | 'MEDIUM' | 'HIGH';

export type AlertType =
  | 'CROSS_BUREAU_COORDINATION'
  | 'POTENTIAL_SAME_INCIDENT'
  | 'PENDING_REMINDER'
  | 'APPROACHING_DEADLINE'
  | 'OVERDUE'
  | 'ESCALATION_REQUIRED';

export type AlertStatus = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED';

export type RelationshipType =
  | 'POTENTIAL_SAME_INCIDENT'
  | 'PROCEDURAL_LINK'
  | 'NO_RELATIONSHIP_ESTABLISHED'
  | 'INSUFFICIENT_EVIDENCE';

export type AssessmentStatus = 'PENDING_REVIEW' | 'CONFIRMED' | 'REJECTED' | 'DEFERRED';

export type Role = 'ADMIN' | 'BUREAU_OFFICER' | 'REVIEWER' | 'READ_ONLY_MANAGER';

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface InstitutionOut {
  id: number;
  permanent_id: string;
  name: string;
  address: string;
  region: string;
  state: string;
  district: string | null;
  institution_type: string | null;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface InstitutionSummary {
  id: number;
  permanent_id: string;
  name: string;
  region: string;
  state: string;
}

export interface BureauOut {
  id: number;
  code: string;
  name: string;
}

export interface CaseOut {
  id: number;
  case_id: string;
  institution_id: number;
  receipt_date: string;
  category: string;
  subject: string;
  description: string;
  status: CaseStatus;
  bureau_id: number;
  officer_name: string;
  priority: Priority;
  last_action_summary: string | null;
  last_action_at: string | null;
  next_action: string | null;
  next_action_due_date: string | null;
  expected_disposal_date: string | null;
  actual_disposal_date: string | null;
  source_record_ref: string | null;
  created_at: string;
  updated_at: string;
  institution: InstitutionSummary;
  bureau: BureauOut;
}

export interface CaseActionOut {
  id: number;
  action_type: string;
  summary: string;
  actor: string;
  from_status: string | null;
  to_status: string | null;
  acted_at: string;
}

export interface TransferRecordOut {
  id: number;
  from_bureau_id: number;
  to_bureau_id: number;
  from_officer: string;
  to_officer: string;
  reason: string;
  actor: string;
  transferred_at: string;
}

export interface CaseDetailOut extends CaseOut {
  actions: CaseActionOut[];
  transfers: TransferRecordOut[];
}

export interface EvidenceItem {
  rule?: string;
  rule_version?: string;
  detail?: string;
  weight?: number;
  item?: string;
}

export interface CaseRef {
  id: number;
  case_id: string;
  status: CaseStatus;
  bureau_id: number;
  subject: string;
  category: string;
}

export interface Assessment {
  id: number;
  source_case_id: number;
  candidate_case_id: number;
  institution_id: number | null;
  relationship_type: RelationshipType;
  supporting_evidence: EvidenceItem[];
  conflicting_evidence: EvidenceItem[];
  missing_evidence: EvidenceItem[];
  rules_fired: string[];
  score: number | null;
  rule_version: string;
  evidence_hash: string | null;
  reviewed_evidence_hash: string | null;
  evidence_snapshot: {
    relationship_type: RelationshipType;
    reviewed_at: string;
    [key: string]: unknown;
  } | null;
  requires_rereview: boolean;
  status: AssessmentStatus;
  reviewer_identity: string | null;
  reviewer_rationale: string | null;
  reviewed_at: string | null;
  last_recomputed_at: string | null;
  created_at: string;
  source_case: CaseRef | null;
  candidate_case: CaseRef | null;
}

export interface AlertOut {
  id: number;
  alert_type: AlertType;
  institution_id: number | null;
  case_ids: string[];
  title: string;
  description: string;
  occurrence: number;
  status: AlertStatus;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  created_at: string;
}

export interface AuditEventOut {
  id: number;
  actor: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  summary: string;
  rationale: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  event_meta: Record<string, unknown> | null;
  created_at: string;
}

export interface DashboardSummary {
  total_cases: number;
  pending: number;
  under_process: number;
  disposed: number;
  transferred: number;
  escalated: number;
  overdue_active: number;
  approaching_deadline: number;
  open_coordination_alerts: number;
  pending_incident_reviews: number;
  deadline_warning_days: number;
  definitions: Record<string, string>;
}

export interface BureauWorkload {
  bureau_id: number;
  code: string;
  name: string;
  total_cases: number;
  active_cases: number;
}

export interface TrendMonth {
  month: string;
  receipts: number;
  disposals: number;
}

export interface MetaInfo {
  app: string;
  app_version: string;
  rule_engine_version: string;
  database_mode: string;
  deadline_warning_days: number;
  escalation_overdue_days: number;
  statuses: CaseStatus[];
  alert_types: AlertType[];
  alert_statuses: AlertStatus[];
  assessment_statuses: AssessmentStatus[];
  relationship_types: RelationshipType[];
  priorities: Priority[];
  bureaus: BureauOut[];
  demo_data_notice: string;
}

export interface ReportData {
  title: string;
  definition: string;
  columns: string[];
  rows: Record<string, unknown>[];
}

export interface CurrentUser {
  username: string;
  display_name: string;
  role: Role;
}
