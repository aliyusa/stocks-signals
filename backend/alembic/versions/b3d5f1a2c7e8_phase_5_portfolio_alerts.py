"""phase 5: closed positions and alert state

Revision ID: b3d5f1a2c7e8
Revises: 7a1c3e9d4b20
Create Date: 2026-10-02 10:00:00
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b3d5f1a2c7e8"
down_revision = "7a1c3e9d4b20"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column("portfolio_positions", sa.Column("closed_at", sa.Date(), nullable=True))
    op.add_column("portfolio_positions", sa.Column("exit_price", sa.Numeric(20, 6), nullable=True))
    op.add_column("portfolio_positions", sa.Column("created_at", sa.DateTime(timezone=True),
                                                   server_default=sa.text("now()"), nullable=False))
    op.add_column("alerts", sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alerts", sa.Column("state", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "state")
    op.drop_column("alerts", "last_evaluated_at")
    op.drop_column("portfolio_positions", "created_at")
    op.drop_column("portfolio_positions", "exit_price")
    op.drop_column("portfolio_positions", "closed_at")
