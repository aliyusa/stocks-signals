"""phase 6: active strategy per user

Revision ID: c9e2a7d4f1b6
Revises: b3d5f1a2c7e8
Create Date: 2026-10-06 10:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "c9e2a7d4f1b6"
down_revision = "b3d5f1a2c7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("active_strategy_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_users_active_strategy", "users", "strategies", ["active_strategy_id"], ["id"],
                          ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_users_active_strategy", "users", type_="foreignkey")
    op.drop_column("users", "active_strategy_id")
