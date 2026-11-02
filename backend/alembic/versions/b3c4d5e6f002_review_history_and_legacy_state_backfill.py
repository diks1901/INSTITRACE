"""review history table + idempotent legacy alert-state backfill

- new relationship_reviews table: append-only history of human review
  decisions (decision, reviewer, rationale, timestamp, evidence snapshot,
  evidence hash, rule-engine version). Never updated or deleted.
- re-applies the alert_condition_state backfill IDEMPOTENTLY so databases
  that already ran a2b7c9d1e001 before the backfill existed get repaired
  (WHERE NOT IN makes this a no-op on databases that are already correct).

Revision ID: b3c4d5e6f002
Revises: a2b7c9d1e001
Create Date: 2026-10-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f002"
down_revision: Union[str, None] = "a2b7c9d1e001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "relationship_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reviewer_identity", sa.String(length=128), nullable=False),
        sa.Column("reviewer_rationale", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=True),
        sa.Column("evidence_hash", sa.String(length=64), nullable=True),
        sa.Column("rule_version", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["relationship_assessments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_relationship_reviews_assessment_id", "relationship_reviews", ["assessment_id"]
    )
    op.create_index(
        "ix_relationship_reviews_decision", "relationship_reviews", ["decision"]
    )

    # Idempotent legacy backfill (same rule as a2b7c9d1e001): databases that
    # applied a2b7c9d1e001 before the backfill existed have an empty
    # alert_condition_state; repair any missing keys here.
    op.execute(sa.text(
        """
        INSERT INTO alert_condition_state
            (logical_key, alert_type, present, occurrences, updated_at)
        SELECT a.logical_key,
               MAX(a.alert_type),
               (MAX(CASE WHEN a.status != 'RESOLVED' THEN 1 ELSE 0 END) <> 0),
               MAX(a.occurrence),
               CURRENT_TIMESTAMP
        FROM coordination_alerts a
        WHERE a.logical_key NOT IN (
            SELECT logical_key FROM alert_condition_state
        )
        GROUP BY a.logical_key
        """
    ))


def downgrade() -> None:
    op.drop_index("ix_relationship_reviews_decision", table_name="relationship_reviews")
    op.drop_index("ix_relationship_reviews_assessment_id", table_name="relationship_reviews")
    op.drop_table("relationship_reviews")
    # The alert_condition_state backfill is intentionally NOT reversed: it is
    # derived, repair-safe data and rolling it back could reintroduce the
    # occurrence collision defect.