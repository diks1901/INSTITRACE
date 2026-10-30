# INSTITRACE Database Schema

Managed by Alembic migrations (`backend/alembic/versions/`). Initial schema migration:
`69e0eedb34ac_initial_schema.py`. Apply with `alembic upgrade head` from `backend/`
(or simply run `python -m app.seed`, which migrates first).

Portable types and constraints only — no PostgreSQL-only behavior in business logic. Foreign
keys are enforced on SQLite via `PRAGMA foreign_keys=ON` (PostgreSQL enforces them natively).

## ER diagram

```mermaid
erDiagram
    bureaus ||--o{ complaint_cases : "currently assigned to"
    institutions ||--o{ complaint_cases : "concerns"
    complaint_cases ||--o{ case_actions : "business history"
    complaint_cases ||--o{ transfer_records : "bureau moves"
    complaint_cases ||--o{ relationship_assessments : "source side"
    complaint_cases ||--o{ relationship_assessments : "candidate side"
    institutions ||--o{ relationship_assessments : "context"
    institutions ||--o{ coordination_alerts : "context"

    bureaus {
        int id PK
        string code UK "RB | PGRC | EVC"
        string name
        text description
        bool active
    }
    institutions {
        int id PK
        string permanent_id UK "e.g. DEMO-INS-001"
        string name
        text address
        string region
        string state
        string district
        string institution_type
        bool is_demo "always true for seed data"
        datetime created_at
        datetime updated_at
    }
    complaint_cases {
        int id PK
        string case_id UK "e.g. DEMO-CASE-001"
        int institution_id FK
        int bureau_id FK
        date receipt_date
        string category
        string subject
        text description
        string status "PENDING|UNDER_PROCESS|DISPOSED|TRANSFERRED|ESCALATED"
        string priority "LOW|MEDIUM|HIGH"
        string officer_name
        string last_action_summary
        datetime last_action_at
        string next_action
        date next_action_due_date
        date expected_disposal_date
        date actual_disposal_date
        string source_record_ref "preserved source identifier"
        datetime created_at
        datetime updated_at
    }
    case_actions {
        int id PK
        int case_id FK
        string action_type "CREATED|STATUS_CHANGE|TRANSFER|ASSIGNMENT_CHANGE|REMARK|NEXT_ACTION_SET"
        text summary
        string actor
        string from_status
        string to_status
        datetime acted_at
    }
    transfer_records {
        int id PK
        int case_id FK
        int from_bureau_id FK
        int to_bureau_id FK
        string from_officer
        string to_officer
        text reason
        string actor
        datetime transferred_at
    }
    relationship_assessments {
        int id PK
        string pair_key UK "CASE-A|CASE-B (sorted)"
        int source_case_id FK
        int candidate_case_id FK
        int institution_id FK "null-safe"
        string relationship_type "engine outcome"
        json supporting_evidence
        json conflicting_evidence
        json missing_evidence
        json rules_fired
        int score "heuristic agreement count - NOT a probability"
        string rule_version
        string status "PENDING_REVIEW|CONFIRMED|REJECTED|DEFERRED"
        string reviewer_identity
        text reviewer_rationale
        datetime reviewed_at
        datetime last_recomputed_at
        datetime created_at
    }
    coordination_alerts {
        int id PK
        string alert_type
        int institution_id FK "nullable"
        json case_ids
        string title
        text description
        string dedupe_key UK "prevents duplicates on recompute"
        string status "OPEN|ACKNOWLEDGED|RESOLVED"
        string acknowledged_by
        datetime acknowledged_at
        string resolved_by
        datetime resolved_at
        text resolution_note
        datetime created_at
    }
    audit_events {
        int id PK
        string actor
        string event_type
        string entity_type
        string entity_id
        text summary
        text rationale
        json before_state
        json after_state
        json event_meta
        datetime created_at
    }
    demo_users {
        int id PK
        string username UK
        string display_name
        string role "ADMIN|BUREAU_OFFICER|REVIEWER|READ_ONLY_MANAGER"
        string password_hash "salted PBKDF2"
        string password_salt
        bool active
    }
```

## Constraints and indexes

- **Uniqueness**: `institutions.permanent_id`, `complaint_cases.case_id`,
  `demo_users.username`, `relationship_assessments.pair_key`, `coordination_alerts.dedupe_key`.
- **Foreign keys**: cases → institutions/bureaus; histories → cases; assessments → both cases
  and institution; alerts → institution. Case history and transfers cascade with their case.
- **Indexes**: `permanent_id`, `case_id`, `institution_id`, `bureau_id`, `status`,
  `expected_disposal_date`, alert `(type, status)`, assessment `(status, relationship_type)`,
  audit `(entity_type, entity_id)`, audit `created_at`.
- **Audit append-only**: `audit_events` has no update/delete API routes; the interface is
  read-only by construction.

## Relationship assessment evidence model

Structured JSON is used **only** for evidence metadata (rule identifier, version, human-readable
detail, weight). The relational structure (cases, institution, statuses, review fields) lives in
proper typed columns — the evidence payload is the explainable payload of the rule engine, not a
data model hiding place.

## Status machine

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> UNDER_PROCESS
    PENDING --> DISPOSED
    PENDING --> TRANSFERRED
    PENDING --> ESCALATED
    UNDER_PROCESS --> DISPOSED
    UNDER_PROCESS --> TRANSFERRED
    UNDER_PROCESS --> ESCALATED
    ESCALATED --> UNDER_PROCESS
    ESCALATED --> DISPOSED
    ESCALATED --> TRANSFERRED
    TRANSFERRED --> PENDING : receiving bureau re-accepts
    TRANSFERRED --> UNDER_PROCESS : receiving bureau re-accepts
    DISPOSED --> [*]
```

`DISPOSED` is terminal. A transfer **never** disposes a case or erases history; the transfer is
recorded in `transfer_records` and `case_actions`, and the case waits for re-acceptance.
