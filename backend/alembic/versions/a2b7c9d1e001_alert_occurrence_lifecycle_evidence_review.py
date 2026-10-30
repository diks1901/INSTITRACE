"""alert occurrence lifecycle + evidence-versioned review

- coordination_alerts: replace dedupe-key uniqueness with (logical_key,
  occurrence) so a recurring condition opens a NEW occurrence while resolved
  rows remain intact history.
- new alert_condition_state table tracking condition presence across runs.
- relationship_assessments: evidence hash/snapshot + requires_rereview flag.

Revision ID: a2b7c9d1e001
Revises: 69e0eedb34ac
Create Date: 2026-10-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2b7c9d1e001"
down_revision: Union[str, None] = "69e0eedb34ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- coordination_alerts: occurrence lifecycle -----------------------
    with op.batch_alter_table("coordination_alerts") as batch:
        batch.add_column(sa.Column("logical_key", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("occurrence", sa.Integer(), nullable=True))
    op.execute("UPDATE coordination_alerts SET logical_key = dedupe_key WHERE logical_key IS NULL")
    op.execute("UPDATE coordination_alerts SET occurrence = 1 WHERE occurrence IS NULL")
    with op.batch_alter_table("coordination_alerts") as batch:
        batch.alter_column("logical_key", existing_type=sa.String(length=255), nullable=False)
        batch.alter_column("occurrence", existing_type=sa.Integer(), nullable=False)
        batch.drop_constraint("uq_alert_dedupe", type_="unique")
        batch.create_unique_constraint("uq_alert_occurrence", ["logical_key", "occurrence"])
        batch.create_index("ix_alerts_logical_key", ["logical_key"])

    op.create_table(
        "alert_condition_state",
        sa.Column("logical_key", sa.String(length=255), nullable=False),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("logical_key"),
    )
    # CRITICAL backfill (FIX 1): pre-existing alert rows mean their conditions
    # already have history. Without this, the first recomputation on a legacy
    # database would try to recreate occurrence 1 for a condition whose
    # occurrence 1 already exists -> UNIQUE constraint failure, or silently
    # resurrect a human-resolved condition.
    #   occurrences := highest occurrence seen for the key (legacy rows are 1)
    #   present     := the key currently has an ACTIVE alert row (so the
    #                  evaluator reuses it instead of colliding on occurrence
    #                  1). Keys whose rows are all RESOLVED start as absent,
    #                  so a genuinely returning condition opens the NEXT
    #                  occurrence (occurrences+1) without any duplicate.
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

    # --- relationship_assessments: evidence-versioned review -------------
    with op.batch_alter_table("relationship_assessments") as batch:
        batch.add_column(sa.Column("evidence_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("reviewed_evidence_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("evidence_snapshot", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("requires_rereview", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.create_index("ix_relationship_assessments_evidence_hash", ["evidence_hash"])


def downgrade() -> None:
    with op.batch_alter_table("relationship_assessments") as batch:
        batch.drop_index("ix_relationship_assessments_evidence_hash")
        batch.drop_column("requires_rereview")
        batch.drop_column("evidence_snapshot")
        batch.drop_column("reviewed_evidence_hash")
        batch.drop_column("evidence_hash")

    op.drop_table("alert_condition_state")

    with op.batch_alter_table("coordination_alerts") as batch:
        batch.drop_index("ix_alerts_logical_key")
        batch.drop_constraint("uq_alert_occurrence", type_="unique")
        batch.create_unique_constraint("uq_alert_dedupe", ["dedupe_key"])
        batch.drop_column("occurrence")
        batch.drop_column("logical_key")
