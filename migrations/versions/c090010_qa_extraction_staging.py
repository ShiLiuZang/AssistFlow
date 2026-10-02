"""Add AssistFlow dialogue extraction staging for the KB management page."""

from alembic import op
import sqlalchemy as sa


revision = "c090010"
down_revision = "c090009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qa_extraction_staging",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_no", sa.String(64), nullable=False),
        sa.Column("source_ref", sa.String(255), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="extracted"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("qa_extraction_staging")
