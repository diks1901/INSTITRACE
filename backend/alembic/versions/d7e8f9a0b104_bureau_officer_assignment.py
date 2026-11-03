"""bureau assignment for BUREAU_OFFICER demo users

Adds nullable `bureau_id` (FK -> bureaus.id) to demo_users and backfills the
synthetic `officer.rb` account to the Regulation Bureau (code "RB"). Existing
rows are untouched (other roles remain unscoped, NULL). Fully backwards
compatible: nullable column, no drops, no rewrites.

Revision ID: d7e8f9a0b104
Revises: c5d6e7f8a103
Create Date: 2026-11-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7e8f9a0b104"
down_revision: Union[str, None] = "c5d6e7f8a103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("demo_users") as batch:
        batch.add_column(
            sa.Column("bureau_id", sa.Integer(), nullable=True)
        )
        batch.create_foreign_key(
            "fk_demo_users_bureau_id", "bureaus", ["bureau_id"], ["id"]
        )
        batch.create_index("ix_demo_users_bureau_id", ["bureau_id"])
    # Backfill the seeded RB officer only if the RB bureau row exists (it is
    # created by seed_demo; empty databases simply skip the backfill).
    op.execute(
        "UPDATE demo_users SET bureau_id = "
        "(SELECT id FROM bureaus WHERE code = 'RB') "
        "WHERE username = 'officer.rb' AND role = 'BUREAU_OFFICER'"
    )


def downgrade() -> None:
    with op.batch_alter_table("demo_users") as batch:
        batch.drop_index("ix_demo_users_bureau_id")
        batch.drop_constraint("fk_demo_users_bureau_id", type_="foreignkey")
        batch.drop_column("bureau_id")
