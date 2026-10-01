"""phase 4: Shariah engine (manual fundamentals, activities, reviews, user methodology)

Revision ID: 7a1c3e9d4b20
Revises: e492b1269c24
Create Date: 2026-10-01 12:00:00
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7a1c3e9d4b20"
down_revision = "e492b1269c24"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column("users", sa.Column("shariah_methodology_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_users_shariah_methodology", "users", "shariah_methodologies",
                          ["shariah_methodology_id"], ["id"], ondelete="SET NULL")
    op.add_column("stocks", sa.Column("shariah_external", JSON, nullable=True))
    op.add_column("stocks", sa.Column("shariah_review_note", sa.Text(), nullable=True))
    op.add_column("fundamentals", sa.Column("source_ref", sa.String(500), nullable=True))
    op.add_column("fundamentals", sa.Column("note", sa.Text(), nullable=True))
    op.add_column("fundamentals", sa.Column("entered_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_fundamentals_entered_by", "fundamentals", "users",
                          ["entered_by_user_id"], ["id"], ondelete="SET NULL")
    op.add_column("shariah_screens", sa.Column("details", JSON, nullable=True))
    op.add_column("shariah_screens", sa.Column("inputs_digest", sa.String(32), nullable=True))
    op.create_index("ix_shariah_screens_inputs_digest", "shariah_screens", ["inputs_digest"])


def downgrade() -> None:
    op.drop_index("ix_shariah_screens_inputs_digest", table_name="shariah_screens")
    op.drop_column("shariah_screens", "inputs_digest")
    op.drop_column("shariah_screens", "details")
    op.drop_constraint("fk_fundamentals_entered_by", "fundamentals", type_="foreignkey")
    op.drop_column("fundamentals", "entered_by_user_id")
    op.drop_column("fundamentals", "note")
    op.drop_column("fundamentals", "source_ref")
    op.drop_column("stocks", "shariah_review_note")
    op.drop_column("stocks", "shariah_external")
    op.drop_constraint("fk_users_shariah_methodology", "users", type_="foreignkey")
    op.drop_column("users", "shariah_methodology_id")
