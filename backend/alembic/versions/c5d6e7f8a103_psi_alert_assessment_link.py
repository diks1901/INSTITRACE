"""informational same-incident alerts link their assessment + evidence hash

Adds nullable `assessment_id` (FK) and `evidence_hash` columns to
coordination_alerts so POTENTIAL_SAME_INCIDENT alerts point at the assessment
and evidence version that raised them. No data changes; NULL for existing
operational alerts.

Revision ID: c5d6e7f8a103
Revises: b3c4d5e6f002
Create Date: 2026-10-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a103"
down_revision: Union[str, None] = "b3c4d5e6f002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("coordination_alerts") as batch:
        batch.add_column(sa.Column("assessment_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("evidence_hash", sa.String(length=64), nullable=True))
        batch.create_index("ix_alerts_assessment_id", ["assessment_id"])
        batch.create_foreign_key(
            "fk_alerts_assessment", "relationship_assessments", ["assessment_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("coordination_alerts") as batch:
        batch.drop_constraint("fk_alerts_assessment", type_="foreignkey")
        batch.drop_index("ix_alerts_assessment_id")
        batch.drop_column("evidence_hash")
        batch.drop_column("assessment_id")
